"""Settings, read from environment variables."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Required, TypedDict


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


@dataclass(frozen=True)
class Settings:
    database_path: Path
    characters_path: Path
    chat_llm_base_url: str
    chat_llm_api_key: str
    chat_llm_model: str
    background_llm_base_url: str | None = None
    background_llm_api_key: str | None = None
    background_llm_model: str | None = None
    ice_servers: list[IceServer] = field(default_factory=lambda: list(DEFAULT_ICE_SERVERS))
    soniox_api_key: str | None = None
    fish_audio_api_key: str | None = None
    fish_audio_model: str = DEFAULT_FISH_AUDIO_MODEL
    siliconflow: "SiliconFlowSettings | None" = None
    jev: "JevSettings | None" = None
    """Retrieval needs both SiliconFlow and Jev; without either, turns go unretrieved."""

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_path=database_path_from_env(),
            characters_path=characters_path_from_env(),
            chat_llm_base_url=_required("CHAT_LLM_BASE_URL"),
            chat_llm_api_key=_required("CHAT_LLM_API_KEY"),
            chat_llm_model=_required("CHAT_LLM_MODEL"),
            background_llm_base_url=os.environ.get("BACKGROUND_LLM_BASE_URL") or None,
            background_llm_api_key=os.environ.get("BACKGROUND_LLM_API_KEY") or None,
            background_llm_model=os.environ.get("BACKGROUND_LLM_MODEL") or None,
            ice_servers=_ice_servers(os.environ.get("EIDOLON_ICE_SERVERS")),
            soniox_api_key=os.environ.get("SONIOX_API_KEY") or None,
            fish_audio_api_key=os.environ.get("FISH_AUDIO_API_KEY") or None,
            fish_audio_model=os.environ.get("FISH_AUDIO_MODEL") or DEFAULT_FISH_AUDIO_MODEL,
            siliconflow=(
                SiliconFlowSettings.from_env() if os.environ.get("SILICONFLOW_API_KEY") else None
            ),
            jev=JevSettings.from_env() if os.environ.get("AI_GATEWAY_API_KEY") else None,
        )


    def background_llm(self) -> tuple[str, str, str]:
        """The background model's base URL, API key and model name. It writes memories down;
        each setting left unset is the chat model's."""
        return (
            self.background_llm_base_url or self.chat_llm_base_url,
            self.background_llm_api_key or self.chat_llm_api_key,
            self.background_llm_model or self.chat_llm_model,
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
