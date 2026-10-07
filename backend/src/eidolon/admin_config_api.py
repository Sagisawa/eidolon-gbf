"""The admin console's configuration, under `/api/admin/config`, for admins only: the live
configuration (`live_config`) as `.env` has it and as it is in effect, changing an item
and restoring it to `.env`'s (ADR-0013). Of a key, only its last 4 characters are ever
shown."""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from eidolon.admin_api import Admin
from eidolon.assembly import Backend
from eidolon.config import LLMProtocol
from eidolon.live_config import CHAT_LLM, ConfigRejected, KeysReadOnly, LLMChange


class LLMInput(BaseModel):
    """A model slot as the admin saves it; without `api_key`, its key stays as it is."""

    protocol: LLMProtocol
    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=200)
    max_tokens: int | None = Field(None, gt=0)
    api_key: str | None = Field(None, min_length=8, max_length=500, pattern=r"^[\x21-\x7e]+$")

    @field_validator("base_url", "model")
    @classmethod
    def _trimmed(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value


def add_admin_config_routes(app: FastAPI, backend: Backend) -> None:
    config = backend.config

    @app.get("/api/admin/config")
    def get_config(_: Admin) -> dict:
        return config.describe()

    @app.put("/api/admin/config/chat_llm")
    async def save_chat_llm(body: LLMInput, _: Admin) -> dict:
        """Try the chat model and, if it works, play every turn and call from now on on it."""
        change = LLMChange(body.protocol, body.base_url, body.model, body.max_tokens, body.api_key)
        try:
            await config.save_chat_llm(change)
        except KeysReadOnly as e:
            raise HTTPException(409, str(e)) from None
        except ConfigRejected as e:
            raise HTTPException(422, f"试调失败，没有保存：{e}") from None
        return config.describe()

    @app.delete("/api/admin/config/{item}")
    async def restore(item: str, _: Admin) -> dict:
        """Back to `.env`'s, from the next turn and call on."""
        if item != CHAT_LLM:
            raise HTTPException(404, "没有这项配置")
        await config.restore(item)
        return config.describe()
