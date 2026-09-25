"""Settings, read from environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path
    chat_llm_base_url: str
    chat_llm_api_key: str
    chat_llm_model: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_path=Path(os.environ.get("EIDOLON_DATABASE_PATH", "data/eidolon.db")),
            chat_llm_base_url=_required("CHAT_LLM_BASE_URL"),
            chat_llm_api_key=_required("CHAT_LLM_API_KEY"),
            chat_llm_model=_required("CHAT_LLM_MODEL"),
        )


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"环境变量 {name} 未设置")
    return value
