"""Settings, read from environment variables."""

import json
import os
from dataclasses import dataclass, field
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

DEFAULT_AI_GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/v1"

DEFAULT_ICE_SERVERS: list[IceServer] = [{"urls": ["stun:stun.l.google.com:19302"]}]

DEFAULT_TURNS_PER_HOUR = 60
DEFAULT_CALLS_PER_HOUR = 5
"""The reference project's limit on voice connections."""


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
    background_llm: LLMSettings | None = None
    """None: the background model is the chat model."""
    ice_servers: list[IceServer] = field(default_factory=lambda: list(DEFAULT_ICE_SERVERS))
    soniox_api_key: str | None = None
    fish_audio_api_key: str | None = None
    fish_audio_model: str = DEFAULT_FISH_AUDIO_MODEL
    siliconflow: "SiliconFlowSettings | None" = None
    jev: "JevSettings | None" = None
    """Retrieval needs both SiliconFlow and Jev; without either, turns go unretrieved."""
    usage_limits: "UsageLimits" = field(default_factory=lambda: UsageLimits())

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_path=database_path_from_env(),
            characters_path=characters_path_from_env(),
            chat_llm=LLMSettings.chat_from_env(),
            background_llm=LLMSettings.background_from_env(),
            ice_servers=_ice_servers(os.environ.get("EIDOLON_ICE_SERVERS")),
            soniox_api_key=os.environ.get("SONIOX_API_KEY") or None,
            fish_audio_api_key=os.environ.get("FISH_AUDIO_API_KEY") or None,
            fish_audio_model=os.environ.get("FISH_AUDIO_MODEL") or DEFAULT_FISH_AUDIO_MODEL,
            siliconflow=(
                SiliconFlowSettings.from_env() if os.environ.get("SILICONFLOW_API_KEY") else None
            ),
            jev=JevSettings.from_env() if os.environ.get("AI_GATEWAY_API_KEY") else None,
            usage_limits=UsageLimits.from_env(),
        )


def database_path_from_env() -> Path:
    return Path(os.environ.get("EIDOLON_DATABASE_PATH", "data/eidolon.db"))


def characters_path_from_env() -> Path:
    return Path(os.environ.get("EIDOLON_CHARACTERS_PATH", "../characters/characters.toml"))


@dataclass(frozen=True)
class SiliconFlowSettings:
    """SiliconFlow's Qwen3-Embedding, which builds and searches the vector index, and
    Qwen3-Reranker, which reranks what the search finds."""

    api_key: str
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    rerank_model: str = DEFAULT_RERANK_MODEL
    base_url: str = DEFAULT_SILICONFLOW_BASE_URL

    @classmethod
    def from_env(cls) -> "SiliconFlowSettings":
        return cls(
            api_key=_required("SILICONFLOW_API_KEY"),
            embedding_model=os.environ.get("EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL,
            rerank_model=os.environ.get("RERANK_MODEL") or DEFAULT_RERANK_MODEL,
            base_url=os.environ.get("SILICONFLOW_BASE_URL") or DEFAULT_SILICONFLOW_BASE_URL,
        )


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
class UsageLimits:
    """How many text turns and voice calls each user may start in any hour, counted
    across all their access keys; None is no limit."""

    turns_per_hour: int | None = DEFAULT_TURNS_PER_HOUR
    calls_per_hour: int | None = DEFAULT_CALLS_PER_HOUR

    @classmethod
    def from_env(cls) -> "UsageLimits":
        return cls(
            turns_per_hour=_limit("EIDOLON_TURNS_PER_HOUR", DEFAULT_TURNS_PER_HOUR),
            calls_per_hour=_limit("EIDOLON_CALLS_PER_HOUR", DEFAULT_CALLS_PER_HOUR),
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
    return [{"urls": [url.strip() for url in value.split(",") if url.strip()]}]
