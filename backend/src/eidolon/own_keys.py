"""Users' own API keys: an LLM (which plays the characters and writes down memories),
speech synthesis (Fish Audio) and speech recognition (Soniox or Alibaba Cloud Model Studio,
阿里云百炼, whichever the user chose, whatever the deployer did).

A user who brings their own key for a service has their turns and calls use it there,
at their own expense. A call on their key that fails fails the turn, saying which of
their keys it was (`OwnKeyFailed`); it never falls back to the deployer's key. Keys are
kept encrypted with a key derived from `EIDOLON_SECRET_KEY`; without that setting,
users cannot bring any. Only the last 4 characters of a key are ever shown again.

Whose keys a turn or call runs on is answered here, once as it starts (`for_turn`,
`for_call`), from the user's own keys it brings (`BroughtKeys`): theirs where it brought
them, the deployer's otherwise, with whether it counts towards the user's limit. The
deployer's are those of the live configuration as the turn or call starts (see
`live_config`), held until it releases them as it ends. Nothing downstream tells the
user's keys from the deployer's.

What a turn or call brings are the keys the user kept (`kept`); one that can no longer be
decrypted fails it right there, before anything is spent.

Before an own LLM is kept, it is tried once, as the deployer's chat model is at startup:
it must stream and take tools. In a public deployment it must also be on the public
internet, so no one can point the backend at the machines next to it, and read their
answers back in the errors they are shown. That is checked on every connection, not only
when the key is saved: a name that resolved to a public address then can resolve to a
private one later.
"""

import asyncio
import base64
import ipaddress
import logging
import socket
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol, get_args
from urllib.parse import urlsplit

import httpcore
import httpx
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from eidolon.activity import ActivityLog, llm_origin, metered_llm
from eidolon.config import (
    DEFAULT_FISH_AUDIO_MODEL,
    BailianRegion,
    LLMProtocol,
    LLMSettings,
    SttKey,
    SttProvider,
)
from eidolon.emotion import EmotionJudging
from eidolon.llm import ChatLLM, ChatMessage, LLMError, Tool, ToolCall, TurnLLMs
from eidolon.llm.providers import check_chat_llm, open_llm
from eidolon.store import OwnKeyRecord, Store

log = logging.getLogger(__name__)

Service = Literal["llm", "tts", "stt"]
SERVICES: tuple[Service, ...] = get_args(Service)
SERVICE_LABELS: dict[Service, str] = {
    "llm": "LLM",
    "tts": "语音合成（Fish Audio）",
    "stt": "语音识别",
}
STT_PROVIDER_NAMES: dict[SttProvider, str] = {"soniox": "Soniox", "bailian": "阿里云百炼"}

MAX_CAUSE_LENGTH = 300
"""How much of the service's own error message the user is shown."""


class OwnKeyFailed(Exception):
    """A call on the user's own key failed; `message` says which key, for the user: for
    speech recognition, the service it is for (`stt_provider`)."""

    def __init__(
        self, service: Service, cause: str, stt_provider: SttProvider | None = None
    ) -> None:
        self.service: Service = service
        label = SERVICE_LABELS[service]
        if service == "stt" and stt_provider is not None:
            label += f"（{STT_PROVIDER_NAMES[stt_provider]}）"
        self.message = f"你的{label}密钥调用失败：{cause[:MAX_CAUSE_LENGTH]}"
        super().__init__(self.message)


class OwnKeyRejected(Exception):
    """Trying the key before keeping it failed; kept nothing."""


class CallsUnavailable(Exception):
    """Voice calls are not configured: there is no key for speech recognition or
    synthesis, neither the user's own nor the deployer's."""

    def __init__(self) -> None:
        super().__init__("语音通话尚未配置，请联系管理员")


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
        transport = httpx.AsyncHTTPTransport()
        if public_only:
            pool = transport._pool  # httpx takes no network backend of its own
            assert isinstance(pool, httpcore.AsyncConnectionPool)
            pool._network_backend = PublicOnlyBackend(pool._network_backend)
        # Not from the environment: a proxy would connect for us, unchecked.
        self._client = httpx.AsyncClient(
            transport=transport, timeout=httpx.Timeout(60, connect=10), trust_env=False
        )

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


@dataclass(frozen=True)
class BroughtKeys:
    """The user's own keys a turn or call brings, by service; None for one it does not
    bring, which it runs on the deployer's key for."""

    llm: OwnLLMSettings | None = None
    tts: str | None = None
    """For Fish Audio."""
    stt: SttKey | None = None
    """For the speech recognition the user chose, with the region of a DashScope key."""

    @property
    def services(self) -> frozenset[Service]:
        """The services it brings a key for."""
        return frozenset(s for s in SERVICES if getattr(self, s) is not None)


class KeyCheck(Protocol):
    """Trying a speech service's key before keeping it (see `call.Speech`)."""

    async def check_stt(self, provider: SttProvider, api_key: str) -> SttKey:
        """The key as calls are to use it, with the region a DashScope key works in. Raises
        OwnKeyRejected saying why, unless `api_key` works for `provider`."""
        ...

    async def check_tts(self, api_key: str) -> None:
        """Raise OwnKeyRejected saying why, unless `api_key` works for Fish Audio."""
        ...


def _no_hold() -> Callable[[], None]:
    return _nothing


@dataclass(frozen=True)
class DeployerKeys:
    """What the deployer pays for wherever a user brought nothing of their own; None for
    a speech service the deployer has no key for."""

    chat_llm: ChatLLM
    memory_llm: ChatLLM
    stt: SttKey | None = None
    """For whichever speech recognition the deployer chose (`STT_PROVIDER`)."""
    tts: str | None = None
    tts_model: str = DEFAULT_FISH_AUDIO_MODEL
    """What Fish Audio speaks with, on whoever's key."""
    emotions: EmotionJudging | None = None
    """Judging her emotion during a call, on the deployer's judge model, whoever's keys
    the call is on; None if it is not judged here (see `call.Calls`)."""
    hold_memory: Callable[[], Callable[[], None]] = field(default=_no_hold, compare=False)
    """See `TurnLLMs.hold_memory`."""

    def lease(self) -> "DeployerLease":
        """These keys, which never change, for a turn or call."""
        return DeployerLease(self, _nothing)


@dataclass(frozen=True)
class DeployerLease:
    """The deployer's keys a turn or call runs on, held until it calls `release`."""

    keys: DeployerKeys
    release: Callable[[], None]


class Deployer(Protocol):
    """Where the deployer's keys come from as each turn or call starts."""

    def lease(self) -> DeployerLease: ...


def _nothing() -> None:
    pass


@dataclass(frozen=True)
class TurnKeys:
    """Whose keys a text turn runs on, and whether it counts towards the user's limit."""

    llms: TurnLLMs
    exempt: bool
    release: Callable[[], None] = field(default=_nothing, compare=False)
    """Called once the turn has ended, to let go of the deployer's keys it ran on."""
    own_llm: bool = False
    """Whether `llms` are the user's own LLM."""


@dataclass(frozen=True)
class CallKeys:
    """Whose keys a call runs on: its turns' models, the keys it hears (`stt`) and speaks
    (`tts`) with and which of those are the user's own, and whether it counts towards the
    user's limit."""

    llms: TurnLLMs
    stt: SttKey
    tts: str
    own: frozenset[Service]
    exempt: bool
    release: Callable[[], None] = field(default=_nothing, compare=False)
    """Called once the call has ended, to let go of the deployer's keys it ran on."""
    tts_model: str = DEFAULT_FISH_AUDIO_MODEL
    emotions: EmotionJudging | None = None
    """The deployer's, as the call connected (see `DeployerKeys.emotions`)."""
    own_llm: bool = False
    """Whether `llms` are the user's own LLM."""


class OwnKeys:
    """Every user's own keys, and whose keys each of their turns and calls runs on."""

    def __init__(
        self,
        store: Store,
        secret_key: str | None,
        llm_service: LLMService,
        deployer: Deployer,
        activity: ActivityLog,
        speech_check: KeyCheck | None = None,
    ) -> None:
        """Each request to a user's own LLM is recorded in `activity` as a service call
        on their own key; the deployer's models are recorded as `deployer` leases them."""
        self._store = store
        self._cipher = _cipher(secret_key) if secret_key else None
        self._llm_service = llm_service
        self._deployer = deployer
        self._activity = activity
        self._speech_check = speech_check

    @property
    def available(self) -> bool:
        return self._cipher is not None

    def for_turn(self, brought: BroughtKeys) -> TurnKeys:
        """Whose keys a text turn bringing `brought` runs on: the user's own LLM, if it
        brings one, both plays the character and writes down their memories."""
        exempt = _exempt(brought.services)["turns"]
        if brought.llm is not None:
            return TurnKeys(self._llms(brought.llm, None), exempt, own_llm=True)
        lease = self._deployer.lease()
        return TurnKeys(self._llms(None, lease.keys), exempt, lease.release)

    def for_call(self, brought: BroughtKeys) -> CallKeys:
        """Whose keys a call bringing `brought` runs on: each of speech recognition and
        synthesis on the user's own key if it brings one, else the deployer's; raises
        CallsUnavailable if there is neither for either. A user's own key for speech
        recognition is for the service they chose, whichever the deployer did."""
        lease = self._deployer.lease()
        try:
            deployer = lease.keys
            stt = brought.stt if brought.stt is not None else deployer.stt
            tts = brought.tts if brought.tts is not None else deployer.tts
            if not stt or not tts:
                raise CallsUnavailable()
            own = brought.services - {"llm"}
            llms = self._llms(brought.llm, deployer)
        except BaseException:
            lease.release()
            raise
        return CallKeys(
            llms, stt, tts, own, _exempt(brought.services)["calls"], lease.release,
            deployer.tts_model, deployer.emotions, own_llm=brought.llm is not None,
        )

    def kept(self, user_id: str, services: Iterable[Service] = SERVICES) -> BroughtKeys:
        """The keys the user kept for `services`, decrypted, as their turn or call brings
        them; none without `EIDOLON_SECRET_KEY`. Raises OwnKeyFailed for one that can no
        longer be decrypted, as after `EIDOLON_SECRET_KEY` has changed."""
        records = self._records(user_id)
        wanted = set(services)
        llm, tts, stt = None, None, None
        if "stt" in wanted and "stt" in records:
            record = records["stt"]
            region: BailianRegion | None = record.region  # pyright: ignore[reportAssignmentType]
            stt = SttKey(_stt_provider(record), self._decrypt(record), region)
        if "tts" in wanted and "tts" in records:
            tts = self._decrypt(records["tts"])
        if "llm" in wanted and "llm" in records:
            record = records["llm"]
            assert record.base_url and record.model
            protocol: LLMProtocol = record.protocol or "chat-completions"  # pyright: ignore[reportAssignmentType]
            llm = OwnLLMSettings(record.base_url, self._decrypt(record), record.model, protocol)
        return BroughtKeys(llm, tts, stt)

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
                elif service == "stt":
                    shown |= {"provider": _stt_provider(record)}
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

    async def save_speech(
        self,
        user_id: str,
        service: Service,
        api_key: str,
        stt_provider: SttProvider = "soniox",
    ) -> None:
        """Try the user's key for speech synthesis ("tts") or recognition ("stt", by
        `stt_provider`), and keep it if it works, a DashScope key with the region it works
        in. Raises OwnKeyRejected saying why it did not, OwnKeysUnavailable without
        `EIDOLON_SECRET_KEY`."""
        assert service in ("tts", "stt")
        cipher = self._require_cipher()
        if self._speech_check is None:
            raise OwnKeyRejected("这个部署没有语音服务")
        provider: SttProvider | None = None
        region: BailianRegion | None = None
        if service == "stt":
            key = await self._speech_check.check_stt(stt_provider, api_key)
            provider, region = key.provider, key.region
        else:
            await self._speech_check.check_tts(api_key)
        self._store.save_own_key(
            user_id,
            OwnKeyRecord(
                service, cipher.encrypt(api_key.encode()), api_key[-4:],
                provider=provider, region=region,
            ),
        )

    def exemptions(self, user_id: str) -> dict[str, bool]:
        """What of the user's use does not count towards their limits (see `_exempt`)."""
        return _exempt(self._records(user_id))

    def delete(self, user_id: str, service: Service) -> bool:
        """Forget the user's key for `service`; False if they had none."""
        self._require_cipher()
        return self._store.delete_own_key(user_id, service)

    def _records(self, user_id: str) -> dict[str, OwnKeyRecord]:
        """The user's own keys, by service; none without `EIDOLON_SECRET_KEY`, which
        they could not be decrypted without."""
        return self._store.own_keys(user_id) if self._cipher else {}

    def _llms(self, own_llm: OwnLLMSettings | None, deployer: DeployerKeys | None) -> TurnLLMs:
        if own_llm is None:
            assert deployer is not None
            return TurnLLMs(deployer.chat_llm, deployer.memory_llm, deployer.hold_memory)
        settings = LLMSettings(own_llm.base_url, own_llm.api_key, own_llm.model, own_llm.protocol)
        own = _OwnLLM(self._llm_service.open(settings))
        return TurnLLMs(
            metered_llm(own, self._activity, llm_origin("chat_llm", settings, own_key=True)),
            metered_llm(own, self._activity, llm_origin("memory_llm", settings, own_key=True)),
        )

    def _decrypt(self, record: OwnKeyRecord) -> str:
        """The key, decrypted; raises OwnKeyFailed if it can no longer be, as after
        `EIDOLON_SECRET_KEY` has changed."""
        assert self._cipher is not None
        try:
            return self._cipher.decrypt(record.secret).decode()
        except InvalidToken:
            raise OwnKeyFailed(
                record.service,  # pyright: ignore[reportArgumentType]
                "保存的密钥无法解密，请重新填写",
                _stt_provider(record) if record.service == "stt" else None,
            ) from None

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


def _stt_provider(record: OwnKeyRecord) -> SttProvider:
    """The service a kept speech recognition key is for: Soniox, if it was kept before
    there was a choice."""
    return record.provider or "soniox"  # pyright: ignore[reportReturnType]


def _exempt(own: Iterable[str]) -> dict[str, bool]:
    """What of a user's use does not count towards their limits, by the services they
    brought their own keys for: text turns on their own LLM, calls on their own LLM,
    speech synthesis and recognition alike."""
    own = set(own)
    return {"turns": "llm" in own, "calls": {"llm", "tts", "stt"} <= own}


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
        await public_address(parts.hostname, parts.port or 443)
    except NotPublic as e:
        raise LLMError(str(e)) from None


class NotPublic(OSError):
    """The host is not found, or not only on the public internet."""


Resolver = Callable[[str, int], Awaitable[list[str]]]


async def resolve(host: str, port: int) -> list[str]:
    """Every address `host` resolves to."""
    found = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(address[0]).split("%")[0] for *_, address in found]


async def public_address(host: str, port: int, resolver: Resolver = resolve) -> str:
    """The address to connect to `host` at; raises NotPublic unless every address it
    resolves to is on the public internet."""
    try:
        addresses = await resolver(host, port)
    except OSError:
        raise NotPublic(f"找不到 {host}") from None
    if not addresses or not all(ipaddress.ip_address(a).is_global for a in addresses):
        raise NotPublic(f"{host} 不是公网地址")
    return addresses[0]


class PublicOnlyBackend(httpcore.AsyncNetworkBackend):
    """Connects only to hosts on the public internet, at the very address it checked, so
    the name cannot resolve elsewhere in between. TLS still checks the certificate
    against the host's name."""

    def __init__(
        self, inner: httpcore.AsyncNetworkBackend, resolver: Resolver = resolve
    ) -> None:
        self._inner = inner
        self._resolver = resolver

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            address = await public_address(host, port, self._resolver)
        except NotPublic as e:
            raise httpcore.ConnectError(str(e)) from None
        return await self._inner.connect_tcp(
            address, port, timeout, local_address, socket_options
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise httpcore.ConnectError("不能连接本机的套接字")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)
