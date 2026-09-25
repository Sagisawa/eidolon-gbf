"""The backend's HTTP API."""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from aiortc import RTCIceServer
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.request_handler import (
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator

from eidolon.call import Call, CallStarter, Quality, serve_calls
from eidolon.characters import load_characters
from eidolon.config import Settings
from eidolon.engine import MAX_INPUT_LENGTH, Clock, ConversationEngine, TurnDone
from eidolon.llm import ChatLLM
from eidolon.llm.openai_compat import OpenAICompatLLM
from eidolon.producer import MAX_FORM_OF_ADDRESS_LENGTH, Gender, ProducerProfile, is_timezone
from eidolon.store import Conversation, KeyRevoked, Store

log = logging.getLogger(__name__)

_INVALID_KEY = "访问密钥无效，请在设置页检查"


class NewConversation(BaseModel):
    character_id: str


class TurnInput(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_INPUT_LENGTH)


class CallRequest(BaseModel):
    conversation_id: str
    muted: bool = False
    quality: Quality = "standard"


class ProfileInput(BaseModel):
    """The whole producer profile; a field left out or empty returns to its default."""

    form_of_address: str | None = None
    gender: Gender | None = None
    timezone: str | None = None

    @field_validator("form_of_address")
    @classmethod
    def _address(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        if len(value) > MAX_FORM_OF_ADDRESS_LENGTH:
            raise ValueError(f"称呼最多 {MAX_FORM_OF_ADDRESS_LENGTH} 个字")
        return value or None

    @field_validator("timezone")
    @classmethod
    def _timezone(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        if value and not is_timezone(value):
            raise ValueError(f"不认识的时区 {value}")
        return value or None


class Offer(BaseModel):
    """A WebRTC offer as the Pipecat client sends it; `requestData` carries our CallRequest."""

    model_config = ConfigDict(populate_by_name=True)

    sdp: str
    type: str
    pc_id: str | None = None
    restart_pc: bool | None = None
    call: CallRequest | None = Field(None, alias="requestData")


def current_user(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> str:
    """Resolve the request's access key (`Authorization: Bearer <key>`) to its user."""
    if not authorization:
        raise _unauthorized("请先在设置页填入访问密钥")
    scheme, _, secret = authorization.partition(" ")
    if scheme.lower() != "bearer" or not secret.strip():
        raise _unauthorized(_INVALID_KEY)
    store: Store = request.app.state.store
    try:
        user_id = store.user_for_key(secret.strip())
    except KeyRevoked:
        raise _unauthorized("这把访问密钥已被吊销，请向管理员索取新的密钥") from None
    if user_id is None:
        raise _unauthorized(_INVALID_KEY)
    return user_id


UserId = Annotated[str, Depends(current_user)]

DeviceTimezone = Annotated[str | None, Header(alias="X-Timezone")]
"""The time zone the browser detected; the producer profile's own time zone overrides it."""


def create_app(
    settings: Settings,
    chat_llm: ChatLLM | None = None,
    call_starter: CallStarter | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    characters = load_characters(settings.characters_path)
    store = Store(settings.database_path)
    llm = chat_llm or OpenAICompatLLM(
        settings.chat_llm_base_url, settings.chat_llm_api_key, settings.chat_llm_model
    )
    engine = ConversationEngine(store, llm, characters, clock)
    call_starter = call_starter or serve_calls(settings, engine)
    webrtc = SmallWebRTCRequestHandler(
        ice_servers=[RTCIceServer(**server) for server in settings.ice_servers]
    )
    calls: dict[str, tuple[str, Call]] = {}  # peer connection id → its user and call

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await webrtc.close()
        await llm.aclose()
        store.close()

    app = FastAPI(title="Eidolon-SC", lifespan=lifespan)
    app.state.store = store

    def conversation_or_404(conversation_id: str, user_id: str) -> Conversation:
        conversation = store.get_conversation(conversation_id)
        if conversation is None or conversation.user_id != user_id:
            raise HTTPException(404, "对话不存在")
        if conversation.character_id not in characters:  # removed from the configuration
            raise HTTPException(404, "角色不存在")
        return conversation

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    def require_voice() -> CallStarter:
        if call_starter is None:
            raise HTTPException(503, "语音通话尚未配置，请联系管理员")
        return call_starter

    @app.get("/api/ice-servers")
    def ice_servers(_: UserId) -> dict:
        """What the browser needs before calling; also tells it when calls are unavailable."""
        require_voice()
        return {"iceServers": settings.ice_servers}

    @app.post("/api/offer")
    async def offer(
        body: Offer, user_id: UserId, device_timezone: DeviceTimezone = None
    ) -> dict:
        """WebRTC signalling: a new call into one of the user's conversations, or a renegotiation."""
        starter = require_voice()
        if body.pc_id is not None:  # renegotiating, possibly on a fresh peer connection
            owner, call = calls.get(body.pc_id, (None, None))
            if owner != user_id or call is None:
                raise HTTPException(404, "通话不存在")
        elif body.call is None:
            raise HTTPException(422, "缺少要通话的对话")
        else:
            conversation = conversation_or_404(body.call.conversation_id, user_id)
            call = Call(
                conversation,
                characters[conversation.character_id],
                body.call.muted,
                body.call.quality,
                device_timezone,
            )

        async def start(connection: SmallWebRTCConnection) -> None:
            @connection.event_handler("closed")
            async def forget(connection: SmallWebRTCConnection) -> None:
                calls.pop(connection.pc_id, None)

            await starter(connection, call)

        request = SmallWebRTCRequest(body.sdp, body.type, body.pc_id, body.restart_pc)
        answer = await webrtc.handle_web_request(request, start)
        if answer is None:
            raise HTTPException(500, "无法建立通话")
        calls[answer["pc_id"]] = (user_id, call)
        return answer

    @app.patch("/api/offer")
    async def ice_candidates(body: SmallWebRTCPatchRequest, user_id: UserId) -> dict:
        if calls.get(body.pc_id, (None,))[0] != user_id:
            raise HTTPException(404, "通话不存在")
        await webrtc.handle_patch_request(body)
        return {"ok": True}

    @app.get("/api/profile")
    def get_profile(user_id: UserId) -> dict:
        return asdict(store.get_profile(user_id))

    @app.put("/api/profile")
    def update_profile(body: ProfileInput, user_id: UserId) -> dict:
        profile = ProducerProfile(body.form_of_address, body.gender, body.timezone)
        store.save_profile(user_id, profile)
        return asdict(profile)

    @app.get("/api/characters")
    def list_characters(_: UserId) -> list[dict]:
        return [
            {
                "id": c.id,
                "name": c.name,
                "intro": c.intro,
                "avatar_url": f"/api/characters/{c.id}/avatar" if c.avatar else None,
            }
            for c in characters.values()
        ]

    @app.get("/api/characters/{character_id}/avatar")
    def character_avatar(character_id: str) -> FileResponse:
        character = characters.get(character_id)
        if character is None or character.avatar is None:
            raise HTTPException(404, "没有这位角色的头像")
        return FileResponse(character.avatar)

    @app.post("/api/conversations", status_code=201)
    def create_conversation(body: NewConversation, user_id: UserId) -> dict:
        if body.character_id not in characters:
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
    def text_turn(
        conversation_id: str,
        body: TurnInput,
        user_id: UserId,
        device_timezone: DeviceTimezone = None,
    ) -> StreamingResponse:
        conversation = conversation_or_404(conversation_id, user_id)

        async def events() -> AsyncIterator[str]:
            try:
                async for event in engine.turn(conversation, body.text, device_timezone):
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
