"""Users' own API keys: an LLM (which plays the characters and writes down memories),
speech synthesis (Fish Audio) and speech recognition (Soniox or Alibaba Cloud Model Studio,
阿里云百炼, whichever the user chose, whatever the deployer did).

A user who brings their own key for a service has their turns and calls use it there,
at their own expense. A call on their key that fails fails the turn, saying which of
their keys it was (`OwnKeyFailed`); it never falls back to the deployer's key. Their keys
are kept in their browser, which brings them with each text turn and call (ADR-0017);
none is kept here, and a turn or call holds the ones it brings only until it ends.

Whose keys a turn or call runs on is answered here, once as it starts (`for_turn`,
`for_call`), from the user's own keys it brings (`BroughtKeys`): theirs where it brought
them, the deployer's otherwise, with whether it counts towards the user's limit. The
deployer's are those of the live configuration as the turn or call starts (see
`live_config`), held until it releases them as it ends. Nothing downstream tells the
user's keys from the deployer's. Before a call is placed, whether it would count is
answered from the services it is to bring keys for, touching no key (`call_exempt`).

Before the browser keeps an own key, it is tried once, keeping nothing (`check_llm`,
`check_tts`, `check_stt`). Whether a key fails its try or a turn, what the service said is
shown to the user with the key masked (`_masked`), and logged no other way; a call's
speech service on the user's key has it masked in its errors before Pipecat logs them
(`call._masking`). An LLM is
tried as the deployer's chat model is at startup: it must stream and take tools. In a
public deployment it must also be on the public internet, so no one can point the backend
at the machines next to it, and read their answers back in the errors they are shown. That is checked on every
connection, not only when the key is tried: a name that resolved to a public address then
can resolve to a private one later.
"""

import asyncio
import ipaddress
import logging
import socket
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Literal, Protocol, get_args
from urllib.parse import urlsplit

import httpcore
import httpx

from eidolon.activity import ActivityLog, llm_origin, metered_llm
from eidolon.config import (
    DEFAULT_FISH_AUDIO_MODEL,
    LLMProtocol,
    LLMSettings,
    SttKey,
    SttProvider,
)
from eidolon.emotion import EmotionJudging
from eidolon.llm import ChatLLM, ChatMessage, LLMError, Tool, ToolCall, TurnLLMs
from eidolon.llm.providers import check_chat_llm, open_llm

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
    """Trying the key before keeping it failed."""


class CallsUnavailable(Exception):
    """Voice calls are not configured: there is no key for speech recognition or
    synthesis, neither the user's own nor the deployer's."""

    def __init__(self) -> None:
        super().__init__("语音通话尚未配置，请联系管理员")


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
    """Whose keys each turn and call runs on, and trying a user's own key before their
    browser keeps it."""

    def __init__(
        self,
        llm_service: LLMService,
        deployer: Deployer,
        activity: ActivityLog,
        speech_check: KeyCheck | None = None,
    ) -> None:
        """Each request to a user's own LLM is recorded in `activity` as a service call
        on their own key; the deployer's models are recorded as `deployer` leases them."""
        self._llm_service = llm_service
        self._deployer = deployer
        self._activity = activity
        self._speech_check = speech_check

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
            _require_speech(brought.services, deployer)
            stt = brought.stt if brought.stt is not None else deployer.stt
            tts = brought.tts if brought.tts is not None else deployer.tts
            assert stt and tts
            own = brought.services - {"llm"}
            llms = self._llms(brought.llm, deployer)
        except BaseException:
            lease.release()
            raise
        return CallKeys(
            llms, stt, tts, own, _exempt(brought.services)["calls"], lease.release,
            deployer.tts_model, deployer.emotions, own_llm=brought.llm is not None,
        )

    def call_exempt(self, services: Iterable[Service]) -> bool:
        """Whether a call bringing the user's own keys for `services` would count towards
        nothing, touching no key. Raises CallsUnavailable as `for_call` would."""
        services = frozenset(services)
        lease = self._deployer.lease()
        try:
            _require_speech(services, lease.keys)
        finally:
            lease.release()
        return _exempt(services)["calls"]

    async def check_llm(self, own: OwnLLMSettings) -> None:
        """Try the user's LLM, keeping nothing. Raises OwnKeyRejected saying why it does
        not work."""
        settings = LLMSettings(own.base_url, own.api_key, own.model, own.protocol)
        with _rejecting(own.api_key):
            await self._llm_service.check(settings)

    async def check_tts(self, api_key: str) -> None:
        """Try the user's key for speech synthesis, keeping nothing. Raises OwnKeyRejected
        saying why it does not work."""
        with _rejecting(api_key):
            await self._require_speech_check().check_tts(api_key)

    async def check_stt(self, provider: SttProvider, api_key: str) -> SttKey:
        """Try the user's key for speech recognition by `provider`, keeping nothing: the key
        as calls are to bring it, a DashScope key with the region it works in. Raises
        OwnKeyRejected saying why it does not work."""
        with _rejecting(api_key):
            return await self._require_speech_check().check_stt(provider, api_key)

    def _llms(self, own_llm: OwnLLMSettings | None, deployer: DeployerKeys | None) -> TurnLLMs:
        if own_llm is None:
            assert deployer is not None
            return TurnLLMs(deployer.chat_llm, deployer.memory_llm, deployer.hold_memory)
        settings = LLMSettings(own_llm.base_url, own_llm.api_key, own_llm.model, own_llm.protocol)
        own = _OwnLLM(self._llm_service, settings)
        return TurnLLMs(
            metered_llm(own, self._activity, llm_origin("chat_llm", settings, own_key=True)),
            metered_llm(own, self._activity, llm_origin("memory_llm", settings, own_key=True)),
        )

    def _require_speech_check(self) -> KeyCheck:
        if self._speech_check is None:
            raise OwnKeyRejected("这个部署没有语音服务")
        return self._speech_check

class _OwnLLM:
    """The user's LLM, whose every failure is theirs to fix."""

    def __init__(self, service: LLMService, settings: LLMSettings) -> None:
        self._llm = service.open(settings)
        self._api_key = settings.api_key

    async def stream(
        self, messages: Sequence[ChatMessage], tools: Sequence[Tool] = ()
    ) -> AsyncIterator[str | ToolCall]:
        try:
            async for item in self._llm.stream(messages, tools):
                yield item
        except Exception as e:
            # Not from `e`, whose message may repeat the key, so no traceback logged shows
            # it; what kind of failure it was is still found in its context.
            raise OwnKeyFailed("llm", _masked(str(e) or type(e).__name__, self._api_key)) from None

    async def aclose(self) -> None:
        pass  # the service's client is shared; see ProviderLLMService


def _masked(message: str, api_key: str) -> str:
    """What a service said about the user's `api_key`, as they are shown it: the key masked
    wherever it says it, then cut short, so that no part of the key is left."""
    return message.replace(api_key, "***")[:MAX_CAUSE_LENGTH]


@contextmanager
def _rejecting(api_key: str) -> Iterator[None]:
    """Raise OwnKeyRejected, saying why with `api_key` masked, if trying it fails."""
    try:
        yield
    except (LLMError, OwnKeyRejected) as e:
        raise OwnKeyRejected(_masked(str(e), api_key)) from None


def _require_speech(own: frozenset[Service], deployer: DeployerKeys) -> None:
    """Raise CallsUnavailable unless a call bringing the user's own keys for `own` has a
    key for each of speech recognition and synthesis, theirs or the deployer's."""
    if not ("stt" in own or deployer.stt) or not ("tts" in own or deployer.tts):
        raise CallsUnavailable()


def _exempt(own: Iterable[str]) -> dict[str, bool]:
    """What of a user's use does not count towards their limits, by the services they
    brought their own keys for: text turns on their own LLM, calls on their own LLM,
    speech synthesis and recognition alike."""
    own = set(own)
    return {"turns": "llm" in own, "calls": {"llm", "tts", "stt"} <= own}


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
