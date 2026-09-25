"""The backend's HTTP API."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from eidolon.characters import CHARACTERS
from eidolon.config import Settings
from eidolon.engine import ConversationEngine, TurnDone
from eidolon.llm import ChatLLM
from eidolon.llm.openai_compat import OpenAICompatLLM
from eidolon.store import DEFAULT_USER_ID, Conversation, Store


class NewConversation(BaseModel):
    character_id: str


class TurnInput(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


def create_app(settings: Settings, chat_llm: ChatLLM | None = None) -> FastAPI:
    store = Store(settings.database_path)
    llm = chat_llm or OpenAICompatLLM(
        settings.chat_llm_base_url, settings.chat_llm_api_key, settings.chat_llm_model
    )
    engine = ConversationEngine(store, llm)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if isinstance(llm, OpenAICompatLLM):
            await llm.aclose()
        store.close()

    app = FastAPI(title="Eidolon-SC", lifespan=lifespan)

    def conversation_or_404(conversation_id: str) -> Conversation:
        conversation = store.get_conversation(conversation_id)
        if conversation is None or conversation.user_id != DEFAULT_USER_ID:
            raise HTTPException(404, "对话不存在")
        return conversation

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    @app.post("/api/conversations", status_code=201)
    def create_conversation(body: NewConversation) -> dict:
        if body.character_id not in CHARACTERS:
            raise HTTPException(404, "角色不存在")
        return asdict(store.create_conversation(DEFAULT_USER_ID, body.character_id))

    @app.get("/api/conversations")
    def list_conversations(character_id: str) -> list[dict]:
        return [asdict(c) for c in store.list_conversations(DEFAULT_USER_ID, character_id)]

    @app.get("/api/conversations/{conversation_id}/messages")
    def list_messages(conversation_id: str) -> list[dict]:
        conversation = conversation_or_404(conversation_id)
        return [asdict(m) for m in store.list_messages(conversation.id)]

    @app.post("/api/conversations/{conversation_id}/turns")
    def text_turn(conversation_id: str, body: TurnInput) -> StreamingResponse:
        conversation = conversation_or_404(conversation_id)

        async def events() -> AsyncIterator[str]:
            try:
                async for event in engine.turn(conversation, body.text):
                    if isinstance(event, TurnDone):
                        payload = {"type": "done", "message": asdict(event.message)}
                    else:
                        payload = {"type": "delta", **asdict(event)}
                    yield _sse(payload)
            except Exception as exc:  # the stream has started; report instead of dropping it
                yield _sse({"type": "error", "message": f"角色暂时无法回复：{exc}"})

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
