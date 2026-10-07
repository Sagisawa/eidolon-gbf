"""The price catalogs online (GLOSSARY.md「看板」): models.dev's and OpenRouter's lists of
models and what each costs per million tokens, in dollars, for pricing the deployer's
service calls in place of the presets (`prices`). The way magpie prices its calls
(github.com/yetone/magpie, `internal/catalog`).

The catalogs are fetched in the background as the server starts, again once they are a
day old, and sooner when a model has no price (`refresh_soon`), or when an admin asks
(`refresh`). Kept in the database, they are matched to a call by the host it was at and
the model it named: the providers at that host (models.dev's `api`, or the few without
one written down here, or OpenRouter), then the model's name, as it is and then looser
and looser. A model at a host no catalog knows (a relay, a proxy) is looked for among
the providers that make models, and priced as its maker prices it. OpenRouter's catalog
is its own API's, not models.dev's copy, which goes without the judge models' prices."""

import asyncio
import logging
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from eidolon.clock import Clock
from eidolon.database import connect

MODELS_DEV_URL = "https://models.dev/api.json"
OPENROUTER_URL = "https://openrouter.ai/api/v1/models?output_modalities=all"
"""Every model OpenRouter has: without `output_modalities=all` the judge models, which
answer with decisions, not text, are left out."""

log = logging.getLogger(__name__)

OPENROUTER = "openrouter"
OPENROUTER_HOST = "openrouter.ai"

HOSTS = {
    "openai": "api.openai.com",
    "anthropic": "api.anthropic.com",
    "google": "generativelanguage.googleapis.com",
    "xai": "api.x.ai",
    "mistral": "api.mistral.ai",
    "cohere": "api.cohere.com",
}
"""The hosts of the models.dev providers that do not say where they are served (`api`)."""

MAKERS = [
    "openai", "anthropic", "google", "deepseek", "xai", "mistral", "moonshotai",
    "alibaba-cn", "zhipuai", "minimax",
]
"""The models.dev providers that make the models they serve, in the order a model at a
host no catalog knows (a relay's) is looked for among them."""

STALE_AFTER = timedelta(hours=24)
"""How old the catalogs may be before they are fetched again."""
MISSING_AFTER = timedelta(hours=6)
"""How long since they were last fetched, or tried, before a model without a price has
them fetched again: they may list it by now."""
RETRY_AFTER = timedelta(minutes=10)
"""How long after a failed fetch before stale catalogs are tried again."""
CHECK_EVERY = 3600
"""How often, in seconds, the server looks whether the catalogs are stale."""


@dataclass(frozen=True)
class Listed:
    """A model a catalog prices: dollars per million input and output tokens (output
    None, priced as input, when the catalog does not say)."""

    provider: str
    model: str
    input: float
    output: float | None


@dataclass(frozen=True)
class State:
    """When the catalogs were last fetched, when and why a fetch last failed since, and
    whether they are being fetched now."""

    fetched_at: datetime | None
    failed_at: datetime | None
    error: str | None
    fetching: bool = False


_SCHEMA = """
-- The price catalogs online as last fetched: each model they price, by provider, in
-- dollars per million tokens; the host each provider is at; when they were fetched.
CREATE TABLE IF NOT EXISTS price_catalog (
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input REAL NOT NULL,
    output REAL,
    PRIMARY KEY (provider, model)
);
CREATE TABLE IF NOT EXISTS price_catalog_hosts (
    host TEXT NOT NULL,
    provider TEXT NOT NULL,
    PRIMARY KEY (host, provider)
);
CREATE TABLE IF NOT EXISTS price_catalog_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    fetched_at TEXT,
    failed_at TEXT,
    error TEXT
);
"""


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        return None
    return float(value)


def parse_models_dev(data: object) -> tuple[list[Listed], list[tuple[str, str]]]:
    """The models models.dev prices per token, and the host each provider is at, leaving
    out its copy of OpenRouter's (`parse_openrouter`) and whatever it does not say
    plainly."""
    listed: list[Listed] = []
    hosts: list[tuple[str, str]] = []
    if not isinstance(data, dict):
        raise ValueError("models.dev: not an object")
    for provider, entry in data.items():
        if provider == OPENROUTER or not isinstance(entry, dict):
            continue
        api = entry.get("api")
        host = urlsplit(api).hostname if isinstance(api, str) else HOSTS.get(provider)
        if host:
            hosts.append((host.lower(), provider))
        models = entry.get("models")
        for model, m in (models.items() if isinstance(models, dict) else []):
            cost = m.get("cost") if isinstance(m, dict) else None
            if not isinstance(cost, dict) or (input := _number(cost.get("input"))) is None:
                continue
            listed.append(Listed(provider, model, input, _number(cost.get("output"))))
    return listed, hosts


def parse_openrouter(data: object) -> list[Listed]:
    """The models OpenRouter prices, its prices per token made per million tokens; a
    price it gives as -1 (one that varies, its router's) is left out."""
    models = data.get("data") if isinstance(data, dict) else None
    if not isinstance(models, list):
        raise ValueError("OpenRouter: no list of models")
    listed = []
    for m in models:
        pricing = m.get("pricing") if isinstance(m, dict) else None
        if not isinstance(pricing, dict) or not isinstance(m.get("id"), str):
            continue
        try:
            input = float(pricing["prompt"])
            output = float(pricing["completion"]) if "completion" in pricing else None
        except (KeyError, TypeError, ValueError):
            continue
        if input < 0 or (output is not None and output < 0):
            continue
        listed.append(Listed(
            OPENROUTER, m["id"], round(input * 1_000_000, 9),
            None if output is None else round(output * 1_000_000, 9),
        ))
    return listed


def _bare(model: str) -> str:
    """A model's name without a path (a vendor's, a relay's), in lower case."""
    return model.lower().rsplit("/", 1)[-1]


def _cut(name: str, at: str) -> str:
    return name.split(at, 1)[0].strip()


def _dashed(model: str) -> str:
    """A model's bare name with its dots as dashes: how two vendors writing a version
    4.6 and 4-6 are compared."""
    return _bare(model).replace(".", "-")


class Catalog:
    """The price catalogs as last fetched, fetching them again on asking (`refresh`)."""

    def __init__(
        self, path: Path, clock: Clock, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._db = connect(path)
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.executescript(_SCHEMA)
        self._clock = clock
        self._fetching = threading.Lock()
        self._background: threading.Thread | None = None
        self._starting = threading.Lock()
        self._closed = False
        self._http = httpx.Client(
            transport=transport, timeout=60, headers={"User-Agent": "eidolon-sc"},
            follow_redirects=True,
        )
        self._load()

    def _load(self) -> None:
        with self._lock:
            listed = self._db.execute(
                "SELECT provider, model, input, output FROM price_catalog"
            ).fetchall()
            hosts = self._db.execute("SELECT host, provider FROM price_catalog_hosts").fetchall()
            state = self._db.execute(
                "SELECT fetched_at, failed_at, error FROM price_catalog_state"
            ).fetchone()
        models: dict[str, dict[str, Listed]] = {}
        for provider, model, input, output in listed:
            models.setdefault(provider, {})[model] = Listed(provider, model, input, output)
        at: dict[str, list[str]] = {OPENROUTER_HOST: [OPENROUTER]}
        for host, provider in hosts:
            at.setdefault(host, []).append(provider)
        self._models = models
        self._hosts = {host: sorted(set(providers)) for host, providers in at.items()}
        when = lambda s: datetime.fromisoformat(s) if s else None  # noqa: E731
        self._state = (
            State(when(state[0]), when(state[1]), state[2]) if state else State(None, None, None)
        )

    def state(self) -> State:
        return replace(self._state, fetching=self._busy())

    def _busy(self) -> bool:
        return self._fetching.locked() or (
            self._background is not None and self._background.is_alive()
        )

    def refresh_soon(self, missing: bool = False) -> None:
        """Fetch the catalogs again in the background if they are stale (`STALE_AFTER`),
        or if a model is `missing` a price and they were last tried `MISSING_AFTER` ago;
        a failed fetch is not tried again for `RETRY_AFTER`. Returns at once."""
        state, now = self._state, self._clock()
        tried = max((d for d in [state.fetched_at, state.failed_at] if d), default=None)
        stale = state.fetched_at is None or now - state.fetched_at >= STALE_AFTER
        due = (
            tried is None
            or (stale and now - tried >= RETRY_AFTER)
            or (missing and now - tried >= MISSING_AFTER)
        )
        with self._starting:
            if not due or self._closed or self._busy():
                return
            self._background = threading.Thread(
                target=self.refresh, name="price-catalog", daemon=True
            )
            self._background.start()

    async def keep_fresh(self) -> None:
        """Look whether the catalogs are stale now and every `CHECK_EVERY` seconds after,
        until cancelled."""
        while True:
            self.refresh_soon()
            await asyncio.sleep(CHECK_EVERY)

    def find(self, host: str, model: str) -> tuple[Listed, bool] | None:
        """The catalogs' price of `model` at `host`, if they have one, and whether it is
        its maker's, for a host no catalog knows (a relay, a proxy): what it is likely
        to cost there, not what it does."""
        providers = self._hosts.get(host.lower())
        if providers:
            found = self._match(providers, model)
            return (found, False) if found else None
        # its maker first, where its name says (`deepseek/deepseek-v4-pro`)
        named = model.lower().split("/", 1)[0] if "/" in model else None
        found = self._match(sorted(MAKERS, key=lambda m: m != named), model)
        return (found, True) if found else None

    def _match(self, providers: list[str], model: str) -> Listed | None:
        """The price the first of `providers` listing `model` gives it: by its name as
        it is, then without a path or case (`openai/GPT-6-Sol` is `gpt-6-sol`), then
        without a `:tag` or a `(variant)` too, then with a dot taken for a dash
        (`claude-opus-4.6` is `claude-opus-4-6`). Of two a provider lists under names
        the same once loosened, the first by name."""
        for provider in providers:
            if (found := self._models.get(provider, {}).get(model)) is not None:
                return found
        bare = _bare(model)
        untagged = _cut(_cut(bare, ":"), "(")
        loosened = [(_bare, bare), (_bare, untagged), (_dashed, untagged.replace(".", "-"))]
        for loosen, want in loosened:
            for provider in providers:
                listed = self._models.get(provider, {})
                names = sorted(name for name in listed if loosen(name) == want)
                if names:
                    return listed[names[0]]
        return None

    def refresh(self) -> None:
        """Fetch the catalogs again, keeping the ones last fetched if either fails; when
        they are being fetched already, wait for that instead. Blocks: call it from a
        thread of its own, not the event loop."""
        if not self._fetching.acquire(blocking=False):
            with self._fetching:
                return
        try:
            now = self._clock()
            try:
                listed, hosts = parse_models_dev(self._get(MODELS_DEV_URL))
                listed += parse_openrouter(self._get(OPENROUTER_URL))
            except (httpx.HTTPError, ValueError) as e:
                log.warning("could not fetch the price catalogs: %s", e)
                self._save_failure(now, f"{type(e).__name__}: {e}"[:500])
            else:
                self._save(now, listed, hosts)
            self._load()
        finally:
            self._fetching.release()

    def _get(self, url: str) -> object:
        response = self._http.get(url)
        response.raise_for_status()
        return response.json()

    def _save(
        self, now: datetime, listed: Iterable[Listed], hosts: Iterable[tuple[str, str]]
    ) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM price_catalog")
            self._db.executemany(
                "INSERT OR REPLACE INTO price_catalog (provider, model, input, output)"
                " VALUES (?, ?, ?, ?)",
                ((m.provider, m.model, m.input, m.output) for m in listed),
            )
            self._db.execute("DELETE FROM price_catalog_hosts")
            self._db.executemany(
                "INSERT OR IGNORE INTO price_catalog_hosts (host, provider) VALUES (?, ?)", hosts
            )
            self._db.execute(
                "INSERT OR REPLACE INTO price_catalog_state (id, fetched_at, failed_at, error)"
                " VALUES (1, ?, NULL, NULL)",
                (now.isoformat(),),
            )

    def _save_failure(self, now: datetime, error: str) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO price_catalog_state (id, failed_at, error) VALUES (1, ?, ?)"
                " ON CONFLICT (id) DO UPDATE SET failed_at = excluded.failed_at,"
                " error = excluded.error",
                (now.isoformat(), error),
            )

    def close(self) -> None:
        with self._starting:
            self._closed = True
        if self._background is not None:  # let a fetch under way finish
            self._background.join()
        with self._fetching:
            self._http.close()
            self._db.close()


def describe_state(state: State) -> dict:
    iso: Callable[[datetime | None], str | None] = lambda d: d.isoformat() if d else None  # noqa: E731
    return {
        "fetched_at": iso(state.fetched_at),
        "failed_at": iso(state.failed_at),
        "error": state.error,
        "fetching": state.fetching,
    }
