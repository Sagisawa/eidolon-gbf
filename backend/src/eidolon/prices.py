"""Prices (GLOSSARY.md「看板」): what the deployer pays each provider for a model's usage,
for the dashboard to estimate what their keys cost.

A price is for a provider (the host the service is at, as service calls are recorded:
`activity.host`), a model and the unit it is billed in (`billing.Unit`): an amount for
each `PER` units of input and, where the service prices output apart (an LLM), of output,
in a currency. The ones in `PRESETS` were gathered from the providers' price pages on the
day each says (see `.scratch/admin-console/research.md`); admins change or add to them in
the admin console, their prices kept in the database (`price_overrides`) and holding over
the presets'; restoring one deletes it, back to the preset, if any.

The cost (`cost`) is each call's usage on the deployer's keys times its price at the time
it is asked for, summed by currency, never converted between them, and without any free
allowance taken off: an estimate, not a bill. A call whose usage is unknown is counted,
not priced; a model without a price shows what it used, and no amount. Usage on users'
own keys is theirs to pay: shown, never priced.
"""

import threading
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from eidolon.activity import SERVICES, CallRow
from eidolon.clock import Clock
from eidolon.database import connect

PER: dict[str, int] = {"tokens": 1_000_000, "bytes": 1_000_000, "seconds": 3600}
"""How many units a price is for: a million tokens, a million bytes (of text spoken, in
UTF-8), an hour (of audio heard)."""

PriceKey = tuple[str, str, str]
"""A provider, a model, a unit."""


@dataclass(frozen=True)
class Price:
    """What `PER` units of input, and of output, cost; output costs as input does when the
    service does not price it apart (`output` None)."""

    input: float
    output: float | None
    currency: str
    as_of: date
    """When it was gathered from the price page, or set in the admin console."""


GATHERED = date(2026, 10, 7)


def _tokens(
    provider: str, prices: dict[str, tuple[float, float | None]], currency: str
) -> dict[PriceKey, Price]:
    return {
        (provider, model, "tokens"): Price(input, output, currency, GATHERED)
        for model, (input, output) in prices.items()
    }


PRESETS: dict[PriceKey, Price] = {
    # LLMs, per million input and output tokens, at the standard (not batch) price for a
    # short context, without cache discounts.
    **_tokens("api.openai.com", {
        "gpt-6-astra": (10, 50),
        "gpt-6.1-sol": (2, 10),
        "gpt-6-sol": (2, 10),
        "gpt-6-luna": (0.1, 0.5),
        "gpt-5.6-sol": (4, 20),  # a promotional price, "at least through November 21, 2026"
        "gpt-5.4-mini": (0.75, 4.5),
    }, "USD"),
    **_tokens("api.anthropic.com", {
        "claude-fable-5-1": (10, 50),
        "claude-opus-5-5": (4, 20),
        "claude-sonnet-5-5": (2, 10),
        "claude-haiku-4-5": (1, 5),
        "claude-haiku-4-5-20251001": (1, 5),
    }, "USD"),
    # DeepSeek's price in yuan at peak hours (off-peak is half); the retired name is
    # served and billed as Flash.
    **_tokens("api.deepseek.com", {
        "deepseek-flash": (2, 8),
        "deepseek-v4-flash": (2, 8),
        "deepseek-v4-pro": (9, 27),
    }, "CNY"),
    # Fish Audio, per million UTF-8 bytes of text spoken.
    **{
        ("api.fish.audio", model, "bytes"): Price(price, None, "USD", GATHERED)
        for model, price in {"s2.1-pro-free": 0, "s2.1-pro": 15, "s2-pro": 15, "s1": 15}.items()
    },
    # Soniox, per hour of audio streamed (its own equivalent of the tokens it bills).
    ("stt-rt.soniox.com", "stt-rt-v5", "seconds"): Price(0.12, None, "USD", GATHERED),
    # The judge model, per million input tokens; output is free.
    **_tokens("openrouter.ai", {
        "typesafe/jev-1.13": (0.042, 0),
        "cloudflare/clef": (0.24, 0),
        "cloudflare/clef-flash": (0.09, 0),
    }, "USD"),
    **_tokens("api.cloudflare.com", {"clef": (0.24, None), "clef-flash": (0.09, None)}, "USD"),
    # Embedding and reranking, per million input tokens.
    **_tokens("api.siliconflow.cn", {
        "Qwen/Qwen3-Embedding-0.6B": (0.07, None),
        "Qwen/Qwen3-Embedding-4B": (0.14, None),
        "Qwen/Qwen3-Embedding-8B": (0.28, None),
        "Qwen/Qwen3-Reranker-0.6B": (0.07, None),
        "Qwen/Qwen3-Reranker-4B": (0.14, None),
        "Qwen/Qwen3-Reranker-8B": (0.28, None),
    }, "CNY"),
    **_tokens("generativelanguage.googleapis.com", {"gemini-embedding-2": (0.2, None)}, "USD"),
}
"""The prices of the models supported, as their providers' price pages had them on
`GATHERED` (`.scratch/admin-console/research.md`). Not here, for want of a price in the
unit its usage is recorded in: Alibaba Cloud Model Studio's speech recognition, billed by
tokens, not seconds."""


def per(unit: str) -> int:
    return PER.get(unit, 1)


_SCHEMA = """
-- The prices admins set in the admin console, each in place of the preset of its provider,
-- model and unit, if any; `output` NULL when output costs as input does.
CREATE TABLE IF NOT EXISTS price_overrides (
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    unit TEXT NOT NULL,
    input REAL NOT NULL,
    output REAL,
    currency TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (provider, model, unit)
);
"""


class Prices:
    """The preset prices, as admins have changed and added to them."""

    def __init__(self, path: Path, clock: Clock) -> None:
        self._db = connect(path)
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.executescript(_SCHEMA)
        self._clock = clock

    def overrides(self) -> dict[PriceKey, Price]:
        with self._lock:
            rows = self._db.execute(
                "SELECT provider, model, unit, input, output, currency, updated_at"
                " FROM price_overrides"
            ).fetchall()
        return {
            (provider, model, unit): Price(
                input, output, currency, datetime.fromisoformat(updated).date()
            )
            for provider, model, unit, input, output, currency, updated in rows
        }

    def effective(self) -> dict[PriceKey, tuple[Price, bool]]:
        """Every price in effect, and whether an admin set it."""
        return {key: (price, False) for key, price in PRESETS.items()} | {
            key: (price, True) for key, price in self.overrides().items()
        }

    def describe(self) -> list[dict]:
        """Every preset and every admin's price, a preset beside the price set in its
        place, by provider, model and unit."""
        overrides = self.overrides()
        return [
            {
                "provider": provider, "model": model, "unit": unit, "per": per(unit),
                "preset": describe_price(key, PRESETS[key], False) if key in PRESETS else None,
                "override": (
                    describe_price(key, overrides[key], True) if key in overrides else None
                ),
            }
            for key in sorted(PRESETS.keys() | overrides.keys())
            for provider, model, unit in [key]
        ]

    def save(self, key: PriceKey, input: float, output: float | None, currency: str) -> None:
        """Price `key` so from now on, in place of its preset, if any."""
        provider, model, unit = key
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO price_overrides"
                " (provider, model, unit, input, output, currency, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (provider, model, unit, input, output, currency, self._clock().isoformat()),
            )

    def restore(self, key: PriceKey) -> bool:
        """Back to the preset of `key`, or unpriced without one; whether an admin had set
        its price."""
        with self._lock, self._db:
            deleted = self._db.execute(
                "DELETE FROM price_overrides WHERE provider = ? AND model = ? AND unit = ?", key
            )
        return deleted.rowcount > 0

    def close(self) -> None:
        self._db.close()


def preset_as_of() -> date | None:
    """When the presets were gathered (the earliest, if on different days)."""
    return min((p.as_of for p in PRESETS.values()), default=None)


def describe_price(key: PriceKey, price: Price, overridden: bool) -> dict:
    return {
        "input": price.input,
        "output": price.output,
        "currency": price.currency,
        "per": per(key[2]),
        "as_of": price.as_of.isoformat(),
        "source": "override" if overridden else "preset",
    }


def amount(price: Price, unit: str, input: float | None, output: float | None) -> float:
    output_price = price.input if price.output is None else price.output
    return ((input or 0) * price.input + (output or 0) * output_price) / per(unit)


def price_of(
    prices: dict[PriceKey, tuple[Price, bool]], provider: str, model: str, unit: str
) -> tuple[Price, bool] | None:
    """The price of a provider's model in `unit`, and whether an admin set it. A model
    recorded with its dimensions (`gemini-embedding-2@1536`, see `embedding`) costs as the
    model does, unless priced apart."""
    found = prices.get((provider, model, unit))
    if found is None and "@" in model:
        found = prices.get((provider, model.split("@", 1)[0], unit))
    return found


def _billed(call: CallRow) -> bool:
    """Whether the service said what the call was billed for."""
    return call.usage_unit is not None and (
        call.usage_input is not None or call.usage_output is not None
    )


def _sum(values: Iterable[float | None]) -> float | None:
    told = [v for v in values if v is not None]
    return sum(told) if told else None


def _order(service: str) -> int:
    return SERVICES.index(service) if service in SERVICES else len(SERVICES)  # pyright: ignore[reportArgumentType]


def _totals(amounts: Iterable[tuple[str, float]]) -> list[dict]:
    summed: dict[str, float] = defaultdict(float)
    for currency, value in amounts:
        summed[currency] += value
    return [{"currency": c, "amount": summed[c]} for c in sorted(summed)]


def cost(
    calls: Sequence[CallRow],
    prices: dict[PriceKey, tuple[Price, bool]],
    starts: Sequence[datetime],
) -> dict:
    """What the deployer's `calls` cost at `prices`: in all, by service, by provider, model
    and unit (`rows`), and in each stretch of the range beginning at `starts`; with what
    users' own keys were billed for, unpriced."""
    deployers = [c for c in calls if not c.own_key]
    known: dict[tuple[str, str, str, str], list[CallRow]] = defaultdict(list)
    unknown: dict[tuple[str, str, str], int] = defaultdict(int)
    for call in deployers:
        if _billed(call):
            assert call.usage_unit is not None
            known[(call.service, call.provider, call.model, call.usage_unit)].append(call)
        else:
            unknown[(call.service, call.provider, call.model)] += 1

    rows: list[dict] = []
    for (service, provider, model, unit), group in known.items():
        input, output = _sum(c.usage_input for c in group), _sum(c.usage_output for c in group)
        found = price_of(prices, provider, model, unit)
        rows.append({
            "service": service, "provider": provider, "model": model, "unit": unit,
            "calls": len(group), "usage_unknown": 0, "input": input, "output": output,
            "price": describe_price((provider, model, unit), *found) if found else None,
            "currency": found[0].currency if found else None,
            "amount": amount(found[0], unit, input, output) if found else None,
        })
    for (service, provider, model), count in unknown.items():
        same = next(
            (r for r in rows if (r["service"], r["provider"], r["model"]) == (service, provider, model)),
            None,
        )
        if same is None:
            same = {
                "service": service, "provider": provider, "model": model, "unit": None,
                "calls": 0, "usage_unknown": 0, "input": None, "output": None,
                "price": None, "currency": None, "amount": None,
            }
            rows.append(same)
        same["calls"] += count
        same["usage_unknown"] += count
    rows.sort(key=lambda r: (_order(r["service"]), r["provider"], r["model"], r["unit"] or ""))

    services = []
    for service in sorted({r["service"] for r in rows}, key=_order):
        mine = [r for r in rows if r["service"] == service]
        services.append({
            "service": service,
            "totals": _totals((r["currency"], r["amount"]) for r in mine if r["amount"] is not None),
            "unpriced": sum(r["unit"] is not None and r["price"] is None for r in mine),
            "usage_unknown": sum(r["usage_unknown"] for r in mine),
        })

    return {
        "totals": _totals(
            (r["currency"], r["amount"]) for r in rows if r["amount"] is not None
        ),
        "services": services,
        "rows": rows,
        "usage_unknown": sum(unknown.values()),
        "trend": _trend(deployers, prices, starts),
        "own_keys": _own_keys([c for c in calls if c.own_key]),
        "preset_as_of": (d.isoformat() if (d := preset_as_of()) else None),
    }


def unpriced(calls: Iterable[CallRow], prices: dict[PriceKey, tuple[Price, bool]]) -> list[dict]:
    """The models the deployer's `calls` used without a price, under the names the calls
    were recorded with, for an admin to price."""
    seen = {
        (c.service, c.provider, c.model, c.usage_unit)
        for c in calls
        if not c.own_key and _billed(c) and c.usage_unit is not None
        and price_of(prices, c.provider, c.model, c.usage_unit) is None
    }
    return [
        {"service": service, "provider": provider, "model": model, "unit": unit}
        for service, provider, model, unit in sorted(seen, key=lambda s: (_order(s[0]), s[1:]))
    ]


def _trend(
    calls: Sequence[CallRow],
    prices: dict[PriceKey, tuple[Price, bool]],
    starts: Sequence[datetime],
) -> list[dict]:
    """What the calls in each stretch beginning at `starts` cost, by currency; the first
    takes in whatever of the range comes before it."""
    amounts: list[dict[str, float]] = [defaultdict(float) for _ in starts]
    if not starts:
        return []
    stretch = (starts[1] - starts[0]) if len(starts) > 1 else None
    for call in calls:
        if not _billed(call) or call.usage_unit is None:
            continue
        found = price_of(prices, call.provider, call.model, call.usage_unit)
        if found is None:
            continue
        i = 0 if stretch is None else int((call.at - starts[0]) / stretch)
        i = max(0, min(len(starts) - 1, i))
        price = found[0]
        amounts[i][price.currency] += amount(
            price, call.usage_unit, call.usage_input, call.usage_output
        )
    return [
        {"start": start.isoformat(), "amounts": dict(sorted(a.items()))}
        for start, a in zip(starts, amounts, strict=True)
    ]


def _own_keys(calls: Sequence[CallRow]) -> list[dict]:
    """What users' own keys were billed for, by service and unit, with how many calls did
    not say."""
    groups: dict[tuple[str, str | None], list[CallRow]] = defaultdict(list)
    for call in calls:
        groups[(call.service, call.usage_unit if _billed(call) else None)].append(call)
    return [
        {
            "service": service,
            "unit": unit,
            "calls": len(group),
            "input": _sum(c.usage_input for c in group) if unit else None,
            "output": _sum(c.usage_output for c in group) if unit else None,
        }
        for (service, unit), group in sorted(
            groups.items(), key=lambda g: (_order(g[0][0]), g[0][1] or "")
        )
    ]

