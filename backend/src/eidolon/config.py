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


DEFAULT_ICE_SERVERS: list[IceServer] = [{"urls": ["stun:stun.l.google.com:19302"]}]


@dataclass(frozen=True)
class Settings:
    database_path: Path
    characters_path: Path
    chat_llm_base_url: str
    chat_llm_api_key: str
    chat_llm_model: str
    ice_servers: list[IceServer] = field(default_factory=lambda: list(DEFAULT_ICE_SERVERS))
    soniox_api_key: str | None = None
    fish_audio_api_key: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_path=database_path_from_env(),
            characters_path=Path(
                os.environ.get("EIDOLON_CHARACTERS_PATH", "../characters/characters.toml")
            ),
            chat_llm_base_url=_required("CHAT_LLM_BASE_URL"),
            chat_llm_api_key=_required("CHAT_LLM_API_KEY"),
            chat_llm_model=_required("CHAT_LLM_MODEL"),
            ice_servers=_ice_servers(os.environ.get("EIDOLON_ICE_SERVERS")),
            soniox_api_key=os.environ.get("SONIOX_API_KEY") or None,
            fish_audio_api_key=os.environ.get("FISH_AUDIO_API_KEY") or None,
        )


def database_path_from_env() -> Path:
    return Path(os.environ.get("EIDOLON_DATABASE_PATH", "data/eidolon.db"))


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
