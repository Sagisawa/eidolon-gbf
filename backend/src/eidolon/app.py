"""The backend's HTTP API."""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from eidolon.characters import CHARACTERS
from eidolon.config import Settings
from eidolon.engine import ConversationEngine, TurnDone
from eidolon.llm import ChatLLM
from eidolon.llm.openai_compat import OpenAICompatLLM
from eidolon.store import Conversation, KeyRevoked, Store

log = logging.getLogger(__name__)


class NewConversation(BaseModel):
    character_id: str


class TurnInput(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


def current_user(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> str:
    """Resolve the request's access key (`Authorization: Bearer <key>`) to its user."""
    if not authorization:
        raise _unauthorized("请先在设置页填入访问密钥")
    scheme, _, secret = authorization.partition(" ")
    if scheme.lower() != "bearer" or not secret.strip():
        raise _unauthorized("访问密钥无效，请在设置页检查")
    store: Store = request.app.state.store
    try:
        user_id = store.user_for_key(secret.strip())
    except KeyRevoked:
        raise _unauthorized("这把访问密钥已被吊销，请向管理员索取新的密钥") from None
    if user_id is None:
        raise _unauthorized("访问密钥无效，请在设置页检查")
    return user_id


UserId = Annotated[str, Depends(current_user)]


def create_app(settings: Settings, chat_llm: ChatLLM | None = None) -> FastAPI:
    store = Store(settings.database_path)
    llm = chat_llm or OpenAICompatLLM(
        settings.chat_llm_base_url, settings.chat_llm_api_key, settings.chat_llm_model
    )
    engine = ConversationEngine(store, llm)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await llm.aclose()
        store.close()

    app = FastAPI(title="Eidolon-SC", lifespan=lifespan)
    app.state.store = store

    def conversation_or_404(conversation_id: str, user_id: str) -> Conversation:
        conversation = store.get_conversation(conversation_id)
        if conversation is None or conversation.user_id != user_id:
            raise HTTPException(404, "对话不存在")
        return conversation

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    @app.post("/api/conversations", status_code=201)
    def create_conversation(body: NewConversation, user_id: UserId) -> dict:
        if body.character_id not in CHARACTERS:
            raise HTTPException(404, "角色不存在")
        return asdict(store.create_conversation(user_id, body.character_id))

    @app.get("/api/conversations")
    def list_conversations(character_id: str, user_id: UserId) -> list[dict]:
        return [asdict(c) for c in store.list_conversations(user_id, character_id)]

    @app.get("/api/conversations/{conversation_id}/messages")
    def list_messages(conversation_id: str, user_id: UserId) -> list[dict]:
        conversation = conversation_or_404(conversation_id, user_id)
        return [asdict(m) for m in store.list_messages(conversation.id)]

    @app.post("/api/conversations/{conversation_id}/turns")
    def text_turn(conversation_id: str, body: TurnInput, user_id: UserId) -> StreamingResponse:
        conversation = conversation_or_404(conversation_id, user_id)

        async def events() -> AsyncIterator[str]:
            try:
                async for event in engine.turn(conversation, body.text):
                    if isinstance(event, TurnDone):
                        payload = {"type": "done", "message": asdict(event.message)}
                    else:
                        payload = {"type": "delta", **asdict(event)}
                    yield _sse(payload)
            except Exception:  # the stream has started; report instead of dropping it
                log.exception("text turn failed in conversation %s", conversation.id)
                yield _sse({"type": "error", "message": "角色暂时无法回复，请稍后再试。"})

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(401, detail, headers={"WWW-Authenticate": "Bearer"})


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
