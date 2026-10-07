"""The live configuration: the settings the server started with (`.env`), overridden by
what admins change in the admin console (ADR-0013). It is the admin console's one way to
read and change the configuration.

Overrides are kept in the database, one row per setting, a key encrypted with a key
derived from `EIDOLON_SECRET_KEY` (without it, keys cannot be changed here, only seen).
A change is tried before it is kept, as the chat model is when the server starts; it
then holds for every turn and call that starts after it, while those under way keep
what they started with (see `service_clients.Swappable`). Restoring a setting deletes
its override.

As the server starts (`start`), every override is tried again. One that fails falls
back to `.env`, kept but marked as failed, so a revoked key cannot keep the server, or
the admin console it is fixed in, from starting. Each item is reported in one of three
states: as `.env` has it, overridden, or overridden but failed and back on `.env`.

For now only the chat model (`chat_llm`) is live.
"""

import asyncio
import base64
import json
import logging
import threading
from dataclasses import dataclass, replace
from typing import Any, Literal

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from eidolon.clock import Clock
from eidolon.config import LLMProtocol, LLMSettings, Settings
from eidolon.database import connect
from eidolon.llm import ChatLLM, LLMError
from eidolon.llm.providers import check_chat_llm
from eidolon.own_keys import DeployerKeys, DeployerLease
from eidolon.service_clients import ServiceClients, Swappable

log = logging.getLogger(__name__)

Status = Literal["env", "overridden", "failed"]
"""As `.env` has it; overridden in the admin console; or overridden, but the override
failed its try as the server started, so `.env`'s is used."""

CHAT_LLM = "chat_llm"
LLM_FIELDS = ("protocol", "base_url", "api_key", "model", "max_tokens")
SECRET_FIELDS = frozenset({"api_key"})

MAX_REASON_LENGTH = 300
"""How much of the service's own error message the admin is shown."""

_SCHEMA = """
-- One row per setting the admin console overrides, named `<item>.<field>`. `value` is
-- JSON, or for a key its Fernet token, of which `last4` is what is ever shown again.
CREATE TABLE IF NOT EXISTS config_overrides (
    name TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    last4 TEXT,
    updated_at TEXT NOT NULL
);
"""


class ConfigRejected(Exception):
    """Trying the change failed, saying why; nothing was saved."""


class KeysReadOnly(Exception):
    """The deployment has no `EIDOLON_SECRET_KEY` to encrypt keys with."""

    def __init__(self) -> None:
        super().__init__("这个部署没有设置 EIDOLON_SECRET_KEY，key 只能在 .env 里修改")


@dataclass(frozen=True)
class LLMChange:
    """A model slot as the admin saves it; without `api_key`, the key stays as it is."""

    protocol: LLMProtocol
    base_url: str
    model: str
    max_tokens: int | None
    api_key: str | None = None


@dataclass(frozen=True)
class _Row:
    value: str
    last4: str | None


class _Unreadable(Exception):
    """An override that can no longer be read back."""


class LiveConfig:
    """The configuration the backend runs on now, and the deployer's clients made from it."""

    def __init__(
        self,
        settings: Settings,
        clients: ServiceClients,
        clock: Clock,
        *,
        background_llm: ChatLLM,
        chat_llm: ChatLLM | None = None,
    ) -> None:
        """With `chat_llm`, the chat model `.env` describes is that one, not made here
        nor closed."""
        self._settings = settings
        self._clients = clients
        self._clock = clock
        self._background = background_llm
        self._cipher = _cipher(settings.secret_key) if settings.secret_key else None
        self._db = connect(settings.database_path)
        self._db_lock = threading.Lock()
        self._changing = asyncio.Lock()
        with self._db_lock, self._db:
            self._db.executescript(_SCHEMA)
            self._rows = {
                name: _Row(value, last4)
                for name, value, last4 in self._db.execute(
                    "SELECT name, value, last4 FROM config_overrides"
                )
            }
        self._chat_failure: str | None = None
        self._chat_settings = settings.chat_llm
        if self._overridden(CHAT_LLM):
            try:
                self._chat_settings = self._chat_overridden()
            except _Unreadable as e:
                self._chat_failure = str(e)
        if self._chat_settings != settings.chat_llm:
            self._chat = Swappable(clients.chat_llm(self._chat_settings))
        elif chat_llm is not None:
            self._chat = Swappable(chat_llm, owned=False)
        else:
            self._chat = Swappable(clients.chat_llm(settings.chat_llm))

    @property
    def chat_llm(self) -> LLMSettings:
        """The deployer's chat model in effect now."""
        return self._chat_settings

    @property
    def keys_editable(self) -> bool:
        return self._cipher is not None

    def lease(self) -> DeployerLease:
        """The deployer's keys for a turn or call starting now, held until it releases
        them."""
        chat = self._chat.lease()
        settings = self._settings
        keys = DeployerKeys(
            chat.client, self._background, settings.stt_key, settings.fish_audio_api_key
        )
        return DeployerLease(keys, chat.release)

    async def start(self) -> None:
        """Try every override as the server starts: one that fails falls back to `.env`,
        with a warning. Logs those in effect."""
        if self._chat_failure is None and self._chat_settings != self._settings.chat_llm:
            try:
                await check_chat_llm(self._chat.current)
            except LLMError as e:
                self._chat_failure = str(e)[:MAX_REASON_LENGTH]
                self._chat_settings = self._settings.chat_llm
                await self._chat.replace(self._clients.chat_llm(self._chat_settings))
        if self._chat_failure is not None:
            log.warning(
                "the admin console's override of %s failed, so .env's is used until an admin"
                " fixes or restores it: %s",
                CHAT_LLM, self._chat_failure,
            )
        in_effect = [
            name for name in sorted(self._rows)
            if not (name.startswith(f"{CHAT_LLM}.") and self._chat_failure is not None)
        ]
        if in_effect:
            log.info(
                "config overrides in effect, set in the admin console over .env: %s",
                ", ".join(in_effect),
            )

    def describe(self) -> dict[str, Any]:
        """What the admin console shows: for each item, `.env`'s value, the one in effect,
        the override if any and its status. Of a key, only its last 4 characters."""
        env = self._settings.chat_llm
        override: dict[str, Any] = {}
        for field in LLM_FIELDS:
            row = self._rows.get(f"{CHAT_LLM}.{field}")
            if row is None:
                continue
            if field in SECRET_FIELDS:
                override[f"{field}_last4"] = row.last4
            else:
                override[field] = json.loads(row.value)
        status: Status = (
            "failed" if self._chat_failure is not None else "overridden" if override else "env"
        )
        return {
            "keys_editable": self.keys_editable,
            CHAT_LLM: {
                "status": status,
                "env": _shown(env),
                "effective": _shown(self._chat_settings),
                "override": override or None,
                "failure": self._chat_failure,
            },
        }

    async def save_chat_llm(self, change: LLMChange) -> None:
        """Try the chat model `change` describes and, if it works, keep it and play every
        turn and call from now on on it. Raises KeysReadOnly for a key without
        `EIDOLON_SECRET_KEY`, ConfigRejected saying why the try failed."""
        if change.api_key is not None and self._cipher is None:
            raise KeysReadOnly()
        async with self._changing:
            candidate = LLMSettings(
                change.base_url,
                change.api_key or self._chat_settings.api_key,
                change.model,
                change.protocol,
                change.max_tokens,
            )
            client = self._clients.chat_llm(candidate)
            try:
                await check_chat_llm(client)
            except LLMError as e:
                await client.aclose()
                raise ConfigRejected(str(e)[:MAX_REASON_LENGTH]) from None
            self._write(CHAT_LLM, candidate, self._settings.chat_llm, keep_key=change.api_key is None)
            self._chat_settings, self._chat_failure = candidate, None
            await self._chat.replace(client)

    async def restore(self, item: str) -> None:
        """Delete the item's override, so that `.env`'s holds from now on."""
        assert item == CHAT_LLM
        async with self._changing:
            with self._db_lock, self._db:
                self._db.execute(
                    "DELETE FROM config_overrides WHERE name LIKE ?", (f"{item}.%",)
                )
            self._rows = {n: r for n, r in self._rows.items() if not n.startswith(f"{item}.")}
            self._chat_failure = None
            if self._chat_settings != self._settings.chat_llm:
                self._chat_settings = self._settings.chat_llm
                await self._chat.replace(self._clients.chat_llm(self._chat_settings))

    async def aclose(self) -> None:
        await self._chat.aclose()
        with self._db_lock:
            self._db.close()

    def _overridden(self, item: str) -> bool:
        return any(name.startswith(f"{item}.") for name in self._rows)

    def _chat_overridden(self) -> LLMSettings:
        """`.env`'s chat model with the overrides; raises _Unreadable if its key can no
        longer be decrypted."""
        values: dict[str, Any] = {}
        for field in LLM_FIELDS:
            row = self._rows.get(f"{CHAT_LLM}.{field}")
            if row is None:
                continue
            if field in SECRET_FIELDS:
                if self._cipher is None:
                    raise _Unreadable("没有设置 EIDOLON_SECRET_KEY，后台保存的 key 无法解密")
                try:
                    values[field] = self._cipher.decrypt(row.value.encode()).decode()
                except InvalidToken:
                    raise _Unreadable(
                        "后台保存的 key 无法解密（EIDOLON_SECRET_KEY 改过），请重新填写"
                    ) from None
            else:
                values[field] = json.loads(row.value)
        return replace(self._settings.chat_llm, **values)

    def _write(self, item: str, settings: LLMSettings, env: LLMSettings, *, keep_key: bool) -> None:
        """Keep as the item's overrides every field of `settings` that differs from
        `env`'s; a key kept as it was (`keep_key`) is not encrypted again."""
        now = self._clock().isoformat()
        rows: dict[str, _Row | None] = {}
        for field in LLM_FIELDS:
            name, value = f"{item}.{field}", getattr(settings, field)
            if value == getattr(env, field):
                rows[name] = None
            elif field in SECRET_FIELDS:
                if keep_key and name in self._rows:
                    continue
                assert self._cipher is not None
                rows[name] = _Row(self._cipher.encrypt(value.encode()).decode(), value[-4:])
            else:
                rows[name] = _Row(json.dumps(value), None)
        with self._db_lock, self._db:
            for name, row in rows.items():
                if row is None:
                    self._db.execute("DELETE FROM config_overrides WHERE name = ?", (name,))
                else:
                    self._db.execute(
                        "INSERT INTO config_overrides (name, value, last4, updated_at)"
                        " VALUES (?, ?, ?, ?) ON CONFLICT (name) DO UPDATE SET"
                        " value = excluded.value, last4 = excluded.last4,"
                        " updated_at = excluded.updated_at",
                        (name, row.value, row.last4, now),
                    )
        for name, row in rows.items():
            if row is None:
                self._rows.pop(name, None)
            else:
                self._rows[name] = row


def _shown(settings: LLMSettings) -> dict[str, Any]:
    """A model slot as the admin console shows it: of its key, the last 4 characters."""
    return {
        "protocol": settings.protocol,
        "base_url": settings.base_url,
        "model": settings.model,
        "max_tokens": settings.max_tokens,
        "api_key_last4": settings.api_key[-4:],
    }


def _cipher(secret_key: str) -> Fernet:
    """The cipher for the deployer's keys kept as overrides, derived from the deployment's
    secret key apart from the one for users' own keys."""
    derived = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=b"eidolon config overrides"
    ).derive(secret_key.encode())
    return Fernet(base64.urlsafe_b64encode(derived))
