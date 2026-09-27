"""Users' own API keys: an LLM (which plays the characters and writes down memories),
speech synthesis (Fish Audio) and speech recognition (Soniox).

A user who brings their own key for a service has their turns and calls use it there,
at their own expense. A call on their key that fails fails the turn, saying which of
their keys it was (`OwnKeyFailed`); it never falls back to the deployer's key. Keys are
kept encrypted with a key derived from `EIDOLON_SECRET_KEY`; without that setting,
users cannot bring any. Only the last 4 characters of a key are ever shown again.

Before an own LLM is kept, it is tried once, as the deployer's chat model is at startup:
it must stream and take tools. In a public deployment it must also be on the public
internet, so no one can point the backend at the machines next to it.
"""

import asyncio
import base64
import ipaddress
import logging
import socket
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, get_args
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from eidolon.config import LLMProtocol, LLMSettings
from eidolon.llm import ChatLLM, ChatMessage, LLMError, Tool, ToolCall
from eidolon.llm.providers import check_chat_llm, open_llm
from eidolon.store import OwnKeyRecord, Store

log = logging.getLogger(__name__)

Service = Literal["llm", "tts", "stt"]
SERVICES: tuple[Service, ...] = get_args(Service)
SERVICE_LABELS: dict[Service, str] = {
    "llm": "LLM",
    "tts": "语音合成（Fish Audio）",
    "stt": "语音识别（Soniox）",
}

MAX_CAUSE_LENGTH = 300
"""How much of the service's own error message the user is shown."""


class OwnKeyFailed(Exception):
    """A call on the user's own key failed; `message` says which key, for the user."""

    def __init__(self, service: Service, cause: str) -> None:
        self.service: Service = service
        self.message = f"你的{SERVICE_LABELS[service]}密钥调用失败：{cause[:MAX_CAUSE_LENGTH]}"
        super().__init__(self.message)


class OwnKeyRejected(Exception):
    """Trying the key before keeping it failed; kept nothing."""


class OwnKeysUnavailable(Exception):
    """The deployment has no `EIDOLON_SECRET_KEY`, so users cannot bring their own keys."""

    def __init__(self) -> None:
        super().__init__("这个部署没有开放自带密钥")


class LLMService(Protocol):
    """The LLM services users bring their own keys to."""

    def open(self, settings: LLMSettings) -> ChatLLM:
        """The model `settings` describe, cheap to open for each turn and never closed."""
        ...

    async def check(self, settings: LLMSettings) -> None:
        """Raise LLMError saying why, unless the model can play the characters."""
        ...

    async def aclose(self) -> None: ...


class ProviderLLMService:
    """Whichever service the user names, over one HTTP client shared by all of them."""

    def __init__(self, *, public_only: bool) -> None:
        """With `public_only`, a service must be on the public internet over HTTPS."""
        self._public_only = public_only
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10))

    def open(self, settings: LLMSettings) -> ChatLLM:
        return open_llm(settings, client=self._client)

    async def check(self, settings: LLMSettings) -> None:
        if self._public_only:
            await _check_public(settings.base_url)
        await check_chat_llm(self.open(settings))

    async def aclose(self) -> None:
        await self._client.aclose()


@dataclass(frozen=True)
class OwnLLMSettings:
    base_url: str
    api_key: str
    model: str
    protocol: LLMProtocol = "chat-completions"


class OwnKeys:
    """Every user's own keys."""

    def __init__(self, store: Store, secret_key: str | None, llm_service: LLMService) -> None:
        self._store = store
        self._cipher = _cipher(secret_key) if secret_key else None
        self._llm_service = llm_service

    @property
    def available(self) -> bool:
        return self._cipher is not None

    def describe(self, user_id: str) -> dict[Service, dict]:
        """What the user may see of their keys, by service: never more of a key than its
        last 4 characters."""
        described: dict[Service, dict] = {}
        for service, record in self._store.own_keys(user_id).items():
            if service in SERVICES:
                shown = {"last4": record.last4}
                if service == "llm":
                    shown |= {"base_url": record.base_url, "model": record.model,
                              "protocol": record.protocol}
                described[service] = shown  # pyright: ignore[reportArgumentType]
        return described

    async def save_llm(self, user_id: str, own: OwnLLMSettings) -> None:
        """Try the user's LLM, and keep it if it works. Raises OwnKeyRejected saying why
        it did not, OwnKeysUnavailable without `EIDOLON_SECRET_KEY`."""
        cipher = self._require_cipher()
        settings = LLMSettings(own.base_url, own.api_key, own.model, own.protocol)
        try:
            await self._llm_service.check(settings)
        except LLMError as e:
            raise OwnKeyRejected(str(e)[:MAX_CAUSE_LENGTH]) from None
        self._store.save_own_key(
            user_id,
            OwnKeyRecord(
                "llm", cipher.encrypt(own.api_key.encode()), own.api_key[-4:],
                own.base_url, own.model, own.protocol,
            ),
        )

    def delete(self, user_id: str, service: Service) -> bool:
        """Forget the user's key for `service`; False if they had none."""
        self._require_cipher()
        return self._store.delete_own_key(user_id, service)

    def chat_llm(self, user_id: str) -> ChatLLM | None:
        """The user's own LLM, for a turn or a call, if they brought one: whatever goes
        wrong calling it raises OwnKeyFailed."""
        record = self._store.own_keys(user_id).get("llm") if self._cipher else None
        if record is None:
            return None
        try:
            api_key = self._decrypt(record)
        except InvalidToken:
            return _Broken(OwnKeyFailed("llm", "保存的密钥无法解密，请重新填写"))
        assert record.base_url and record.model
        protocol: LLMProtocol = record.protocol or "chat-completions"  # pyright: ignore[reportAssignmentType]
        return _OwnLLM(
            self._llm_service.open(LLMSettings(record.base_url, api_key, record.model, protocol))
        )

    def _decrypt(self, record: OwnKeyRecord) -> str:
        assert self._cipher is not None
        return self._cipher.decrypt(record.secret).decode()

    def _require_cipher(self) -> Fernet:
        if self._cipher is None:
            raise OwnKeysUnavailable()
        return self._cipher


class _OwnLLM:
    """The user's LLM, whose every failure is theirs to fix."""

    def __init__(self, llm: ChatLLM) -> None:
        self._llm = llm

    async def stream(
        self, messages: Sequence[ChatMessage], tools: Sequence[Tool] = ()
    ) -> AsyncIterator[str | ToolCall]:
        try:
            async for item in self._llm.stream(messages, tools):
                yield item
        except Exception as e:
            raise OwnKeyFailed("llm", str(e) or type(e).__name__) from e

    async def aclose(self) -> None:
        pass  # the service's client is shared; see ProviderLLMService


class _Broken:
    """An own LLM that cannot be called at all."""

    def __init__(self, failure: OwnKeyFailed) -> None:
        self._failure = failure

    async def stream(
        self, messages: Sequence[ChatMessage], tools: Sequence[Tool] = ()
    ) -> AsyncIterator[str | ToolCall]:
        raise self._failure
        yield ""  # a generator all the same

    async def aclose(self) -> None:
        pass


def _cipher(secret_key: str) -> Fernet:
    """The cipher for users' keys, derived from the deployment's secret key."""
    derived = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=b"eidolon own api keys"
    ).derive(secret_key.encode())
    return Fernet(base64.urlsafe_b64encode(derived))


async def _check_public(base_url: str) -> None:
    """Raise LLMError unless `base_url` is HTTPS to a host on the public internet."""
    parts = urlsplit(base_url)
    if parts.scheme != "https" or not parts.hostname:
        raise LLMError("接口地址需要以 https:// 开头")
    try:
        found = await asyncio.get_running_loop().getaddrinfo(
            parts.hostname, parts.port or 443, type=socket.SOCK_STREAM
        )
    except OSError:
        raise LLMError(f"找不到 {parts.hostname}") from None
    for *_, address in found:
        if not ipaddress.ip_address(str(address[0]).split("%")[0]).is_global:
            raise LLMError(f"{parts.hostname} 不是公网地址")
