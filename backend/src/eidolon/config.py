"""Settings, read from environment variables."""

import base64
import hmac
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Required, TypedDict, get_args


class IceServer(TypedDict, total=False):
    """One entry of WebRTC's `iceServers`; TURN servers also need a username and credential."""

    urls: Required[str | list[str]]
    username: str
    credential: str


DEFAULT_FISH_AUDIO_MODEL = "s2.1-pro-free"
"""Fish Audio's free-tier model: it draws on no API credit, unlike the paid ones."""

DEFAULT_SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_RERANK_MODEL = "Qwen/Qwen3-Reranker-0.6B"
"""On the calibration set it ranks story and character facts better than 4B does."""

DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_GEMINI_EMBEDDING_MODEL = "gemini-embedding-2"
DEFAULT_EMBEDDING_DIMENSIONS = 1536
EMBEDDING_DIMENSIONS_RANGE = (128, 3072)

DEFAULT_AI_GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/v1"

DEFAULT_ICE_SERVERS: list[IceServer] = [{"urls": ["stun:stun.l.google.com:19302"]}]

DEFAULT_TURNS_PER_HOUR = 60
DEFAULT_CALLS_PER_HOUR = 5
"""The reference project's limit on voice connections."""
DEFAULT_CALL_MINUTES = 10
DEFAULT_TURNS_PER_CALL = 40
"""About what ten minutes of talking takes; a cap on typing turns in quickly during a call."""
DEFAULT_HISTORY_TURNS = 20
"""How many of a conversation's latest turns the chat model reads; memories carry the rest."""


LLMProtocol = Literal["chat-completions", "responses", "anthropic"]
"""OpenAI-compatible Chat Completions, OpenAI Responses, or Anthropic Messages."""

LLM_PROTOCOLS: tuple[LLMProtocol, ...] = get_args(LLMProtocol)


@dataclass(frozen=True)
class LLMSettings:
    """One model slot: the protocol its service speaks, where it is, and which model."""

    base_url: str
    api_key: str
    model: str
    protocol: LLMProtocol = "chat-completions"
    max_tokens: int | None = None
    """A cap on each reply's length; the Anthropic protocol needs one and has a default."""

    @classmethod
    def chat_from_env(cls) -> "LLMSettings":
        return cls._from_env("CHAT")

    @classmethod
    def background_from_env(cls) -> "LLMSettings":
        """The background model; each setting left unset is the chat model's."""
        return cls._from_env("BACKGROUND", fallback="CHAT")

    @classmethod
    def _from_env(cls, slot: str, fallback: str | None = None) -> "LLMSettings":
        def value(name: str) -> str | None:
            names = [f"{slot}_LLM_{name}"] + ([f"{fallback}_LLM_{name}"] if fallback else [])
            return next((v for n in names if (v := os.environ.get(n))), None)

        def required(name: str) -> str:
            if found := value(name):
                return found
            alternative = f"（或 {fallback}_LLM_{name}）" if fallback else ""
            raise RuntimeError(f"环境变量 {slot}_LLM_{name}{alternative}未设置")

        protocol = value("PROTOCOL") or "chat-completions"
        if protocol not in LLM_PROTOCOLS:
            raise RuntimeError(
                f"环境变量 {slot}_LLM_PROTOCOL 只能是 {'、'.join(LLM_PROTOCOLS)}，而不是 {protocol}"
            )
        # Each slot's own: a cap that suits the chat could cut a drafted sheet short.
        max_tokens = os.environ.get(f"{slot}_LLM_MAX_TOKENS") or None
        if max_tokens is not None and not (
            max_tokens.isascii() and max_tokens.isdigit() and int(max_tokens) > 0
        ):
            raise RuntimeError(f"环境变量 {slot}_LLM_MAX_TOKENS 需要是正整数，而不是 {max_tokens}")
        return cls(
            base_url=required("BASE_URL"),
            api_key=required("API_KEY"),
            model=required("MODEL"),
            protocol=protocol,  # pyright: ignore[reportArgumentType]  # checked above
            max_tokens=int(max_tokens) if max_tokens else None,
        )


@dataclass(frozen=True)
class Settings:
    database_path: Path
    characters_path: Path
    chat_llm: LLMSettings
    background_llm: LLMSettings = None  # pyright: ignore[reportAssignmentType]  # see below
    """Left out, the background model is the chat model."""
    ice_servers: list[IceServer] = field(default_factory=lambda: list(DEFAULT_ICE_SERVERS))
    turn: "TurnSettings | None" = None
    """A TURN server the browser gets short-lived credentials for, besides `ice_servers`."""
    soniox_api_key: str | None = None
    fish_audio_api_key: str | None = None
    fish_audio_model: str = DEFAULT_FISH_AUDIO_MODEL
    embedding: "EmbeddingSettings | None" = None
    rerank: "RerankSettings | None" = None
    jev: "JevSettings | None" = None
    """Retrieval needs the embedding service, the reranker and Jev; without any of them,
    turns go unretrieved."""
    usage_limits: "UsageLimits" = field(default_factory=lambda: UsageLimits())
    history_turns: int | None = DEFAULT_HISTORY_TURNS
    """How many of the conversation's latest turns each prompt carries; None is all of them."""
    domain: str | None = None
    """The public deployment's domain (behind Caddy); None in development."""
    dev_login: bool = False
    """Lets anyone sign in as any user by name, for development and tests only."""
    github: "OAuthSettings | None" = None
    """Signing in with GitHub; not offered unless configured."""
    google: "OAuthSettings | None" = None
    """Signing in with Google; not offered unless configured."""
    secret_key: str | None = None
    """What users' own API keys are encrypted with; without it, they cannot bring any."""

    def __post_init__(self) -> None:
        if self.background_llm is None:
            object.__setattr__(self, "background_llm", self.chat_llm)
        if self.dev_login and self.domain:
            raise RuntimeError(
                "EIDOLON_DEV_LOGIN=1 让任何人都能不经登录冒充任何用户，只能在开发环境打开；"
                "配置了 EIDOLON_DOMAIN 的公开部署不会启动，请去掉 EIDOLON_DEV_LOGIN"
            )

    @property
    def public_origin(self) -> str:
        """Where browsers reach the site: the domain over HTTPS, or the frontend's
        development server."""
        return f"https://{self.domain}" if self.domain else "http://localhost:3000"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_path=database_path_from_env(),
            characters_path=characters_path_from_env(),
            chat_llm=LLMSettings.chat_from_env(),
            background_llm=LLMSettings.background_from_env(),
            ice_servers=_ice_servers(os.environ.get("EIDOLON_ICE_SERVERS")),
            turn=TurnSettings.from_env(),
            soniox_api_key=os.environ.get("SONIOX_API_KEY") or None,
            fish_audio_api_key=os.environ.get("FISH_AUDIO_API_KEY") or None,
            fish_audio_model=os.environ.get("FISH_AUDIO_MODEL") or DEFAULT_FISH_AUDIO_MODEL,
            embedding=EmbeddingSettings.from_env(),
            rerank=RerankSettings.from_env(),
            jev=JevSettings.from_env() if os.environ.get("AI_GATEWAY_API_KEY") else None,
            usage_limits=UsageLimits.from_env(),
            history_turns=history_turns_from_env(),
            domain=os.environ.get("EIDOLON_DOMAIN", "").strip() or None,
            dev_login=os.environ.get("EIDOLON_DEV_LOGIN", "").strip() == "1",
            github=OAuthSettings.from_env("GITHUB"),
            google=OAuthSettings.from_env("GOOGLE"),
            secret_key=os.environ.get("EIDOLON_SECRET_KEY") or None,
        )


def database_path_from_env() -> Path:
    return Path(os.environ.get("EIDOLON_DATABASE_PATH", "data/eidolon.db"))


def characters_path_from_env() -> Path:
    return Path(os.environ.get("EIDOLON_CHARACTERS_PATH", "../characters/characters.toml"))


def story_path_from_env() -> Path:
    """SCTranslationData's story directory, which `eidolon story sync` imports from."""
    return Path(os.environ.get("EIDOLON_STORY_PATH", "../corpus/SCTranslationData/data/story"))


def mirror_cache_path_from_env() -> Path:
    """Where `eidolon story sync` keeps the scripts it downloads from the mirror."""
    return Path(os.environ.get("EIDOLON_MIRROR_CACHE_PATH", "../corpus/mirror"))


def event_names_path_from_env() -> Path:
    """The admin's table of event names, which `eidolon story sync` names events from."""
    return Path(os.environ.get("EIDOLON_EVENT_NAMES_PATH", "../deploy/event-names.toml"))


def history_turns_from_env() -> int | None:
    return _limit("EIDOLON_HISTORY_TURNS", DEFAULT_HISTORY_TURNS)


@dataclass(frozen=True)
class OAuthSettings:
    """An OAuth app registered with Google or GitHub, which users sign in through."""

    client_id: str
    client_secret: str

    @classmethod
    def from_env(cls, provider: str) -> "OAuthSettings | None":
        """From `{provider}_CLIENT_ID` and `{provider}_CLIENT_SECRET`; None if neither is set."""
        if not os.environ.get(f"{provider}_CLIENT_ID") and not os.environ.get(
            f"{provider}_CLIENT_SECRET"
        ):
            return None
        return cls(_required(f"{provider}_CLIENT_ID"), _required(f"{provider}_CLIENT_SECRET"))


EmbeddingProvider = Literal["siliconflow", "gemini"]
EMBEDDING_PROVIDERS: tuple[EmbeddingProvider, ...] = get_args(EmbeddingProvider)


@dataclass(frozen=True)
class EmbeddingSettings:
    """The service that builds and searches the vector index, chosen at deploy time
    (ADR-0005): SiliconFlow's Qwen3-Embedding or Google's Gemini Embedding."""

    provider: EmbeddingProvider
    api_key: str
    model: str
    base_url: str
    dimensions: int | None = None
    """How long Gemini's vectors are; SiliconFlow's are as long as the model makes them."""

    @classmethod
    def from_env(cls) -> "EmbeddingSettings | None":
        """None if the chosen service's key is not set; a bad choice raises all the same."""
        provider = _embedding_provider()
        if not os.environ.get(_EMBEDDING_KEYS[provider]):
            return None
        return cls.required_from_env()

    @classmethod
    def required_from_env(cls) -> "EmbeddingSettings":
        """For the commands that cannot do without embedding: a missing key raises."""
        provider = _embedding_provider()
        api_key = _required(_EMBEDDING_KEYS[provider])
        model = os.environ.get("EMBEDDING_MODEL") or None
        if provider == "siliconflow":
            return cls(
                provider,
                api_key,
                model or DEFAULT_EMBEDDING_MODEL,
                os.environ.get("SILICONFLOW_BASE_URL") or DEFAULT_SILICONFLOW_BASE_URL,
            )
        return cls(
            provider,
            api_key,
            model or DEFAULT_GEMINI_EMBEDDING_MODEL,
            os.environ.get("GEMINI_BASE_URL") or DEFAULT_GEMINI_BASE_URL,
            _embedding_dimensions(),
        )


_EMBEDDING_KEYS: dict[EmbeddingProvider, str] = {
    "siliconflow": "SILICONFLOW_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


def _embedding_provider() -> EmbeddingProvider:
    provider = os.environ.get("EMBEDDING_PROVIDER") or "siliconflow"
    if provider not in EMBEDDING_PROVIDERS:
        raise RuntimeError(
            f"环境变量 EMBEDDING_PROVIDER 只能是 {'、'.join(EMBEDDING_PROVIDERS)}，而不是 {provider}"
        )
    return provider  # pyright: ignore[reportReturnType]  # checked above


def _embedding_dimensions() -> int:
    value = (os.environ.get("EMBEDDING_DIMENSIONS") or "").strip()
    if not value:
        return DEFAULT_EMBEDDING_DIMENSIONS
    low, high = EMBEDDING_DIMENSIONS_RANGE
    if not (value.isascii() and value.isdigit() and low <= int(value) <= high):
        raise RuntimeError(f"环境变量 EMBEDDING_DIMENSIONS 需要是 {low}–{high} 之间的整数，而不是 {value}")
    return int(value)


@dataclass(frozen=True)
class RerankSettings:
    """SiliconFlow's Qwen3-Reranker, which reranks what the vector search finds, whichever
    service embeds. The thresholds, unless set here, are the model's (see `rerank`)."""

    api_key: str
    model: str = DEFAULT_RERANK_MODEL
    base_url: str = DEFAULT_SILICONFLOW_BASE_URL
    min_relevance: float | None = None
    """Overrides the model's threshold for story passages and character facts."""
    memory_min_relevance: float | None = None
    """Overrides the model's threshold for memories."""

    @classmethod
    def from_env(cls) -> "RerankSettings | None":
        """None if SiliconFlow's key is not set."""
        if not os.environ.get("SILICONFLOW_API_KEY"):
            return None
        return cls(
            api_key=_required("SILICONFLOW_API_KEY"),
            model=os.environ.get("RERANK_MODEL") or DEFAULT_RERANK_MODEL,
            base_url=os.environ.get("SILICONFLOW_BASE_URL") or DEFAULT_SILICONFLOW_BASE_URL,
            min_relevance=_relevance("RERANK_MIN_RELEVANCE"),
            memory_min_relevance=_relevance("RERANK_MEMORY_MIN_RELEVANCE"),
        )


def _relevance(name: str) -> float | None:
    value = (os.environ.get(name) or "").strip()
    if not value:
        return None
    try:
        relevance = float(value)
    except ValueError:
        relevance = -1.0
    if not 0 <= relevance <= 1:
        raise RuntimeError(f"环境变量 {name} 需要是 0 到 1 之间的数，而不是 {value}")
    return relevance


@dataclass(frozen=True)
class JevSettings:
    """Jev, reached through Vercel AI Gateway, decides whether a turn needs retrieval."""

    api_key: str
    model: str
    base_url: str = DEFAULT_AI_GATEWAY_BASE_URL

    @classmethod
    def from_env(cls) -> "JevSettings":
        return cls(
            api_key=_required("AI_GATEWAY_API_KEY"),
            model=_required("JEV_MODEL"),
            base_url=os.environ.get("AI_GATEWAY_BASE_URL") or DEFAULT_AI_GATEWAY_BASE_URL,
        )


@dataclass(frozen=True)
class TurnSettings:
    """A TURN server that shares a secret with the backend (coturn's `use-auth-secret`): the
    backend mints each browser credentials that expire, so the secret never leaves it."""

    urls: list[str]
    secret: str

    @classmethod
    def from_env(cls) -> "TurnSettings | None":
        urls = _comma_list(os.environ.get("EIDOLON_TURN_URLS", ""))
        if not urls:
            return None
        return cls(urls, _required("EIDOLON_TURN_SECRET"))

    def credentials(self, user_id: str, now: datetime) -> IceServer:
        """The username carries when the credentials expire; the password is the username
        signed with the secret."""
        expires = int((now + TURN_CREDENTIAL_LIFETIME).timestamp())
        username = f"{expires}:{user_id}"
        signature = hmac.new(self.secret.encode(), username.encode(), "sha1").digest()
        return {
            "urls": list(self.urls),
            "username": username,
            "credential": base64.b64encode(signature).decode(),
        }


TURN_CREDENTIAL_LIFETIME = timedelta(hours=24)
"""How long minted TURN credentials last. The TURN server checks them again each time a
call refreshes its relay, so they must outlast the longest call, and calls may have no
time limit (`EIDOLON_CALL_MINUTES=0`)."""


@dataclass(frozen=True)
class UsageLimits:
    """How many text turns and voice calls each user may start in any hour, counted
    across all their devices and sign-in methods, and how long and how many turns one
    call may last; None is no limit."""

    turns_per_hour: int | None = DEFAULT_TURNS_PER_HOUR
    calls_per_hour: int | None = DEFAULT_CALLS_PER_HOUR
    call_minutes: int | None = DEFAULT_CALL_MINUTES
    turns_per_call: int | None = DEFAULT_TURNS_PER_CALL

    @classmethod
    def from_env(cls) -> "UsageLimits":
        return cls(
            turns_per_hour=_limit("EIDOLON_TURNS_PER_HOUR", DEFAULT_TURNS_PER_HOUR),
            calls_per_hour=_limit("EIDOLON_CALLS_PER_HOUR", DEFAULT_CALLS_PER_HOUR),
            call_minutes=_limit("EIDOLON_CALL_MINUTES", DEFAULT_CALL_MINUTES),
            turns_per_call=_limit("EIDOLON_TURNS_PER_CALL", DEFAULT_TURNS_PER_CALL),
        )


def _limit(name: str, default: int) -> int | None:
    """A limit from the environment: unset is the default, 0 is no limit."""
    value = (os.environ.get(name) or "").strip()
    if not value:
        return default
    if not (value.isascii() and value.isdigit()):
        raise RuntimeError(f"环境变量 {name} 需要是非负整数（0 表示不限制），而不是 {value}")
    return int(value) or None


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"环境变量 {name} 未设置")
    return value


def _ice_servers(value: str | None) -> list[IceServer]:
    """Either a JSON list of ICE servers, or comma-separated STUN/TURN URLs."""
    if not value or not value.strip():
        return list(DEFAULT_ICE_SERVERS)
    if value.lstrip().startswith("["):
        try:
            servers = json.loads(value)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"环境变量 EIDOLON_ICE_SERVERS 不是有效的 JSON：{e}") from None
        if not isinstance(servers, list) or not all(
            isinstance(s, dict) and "urls" in s for s in servers
        ):
            raise RuntimeError("环境变量 EIDOLON_ICE_SERVERS 的每一项都需要有 urls")
        return servers
    return [{"urls": _comma_list(value)}]


def _comma_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
