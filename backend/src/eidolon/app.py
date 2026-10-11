"""The backend's HTTP API."""

import json
import math
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.types import Receive, Scope, Send
from pydantic import BaseModel, ConfigDict, Field, field_validator

from eidolon.assembly import Backend
from eidolon.call import (
    CallFailed,
    CallNotFound,
    CallOptions,
    IceCandidate,
    Quality,
    SessionDescription,
)
from eidolon.characters import Character
from eidolon.greetings import greeting_path
from eidolon.reply_format import SegmentComplete, SegmentDelta, SpeechDelta
from eidolon.own_keys import BroughtKeys, CallsUnavailable, UnknownService, named_services
from eidolon.producer import MAX_FORM_OF_ADDRESS_LENGTH, Gender, ProducerProfile, is_timezone
from eidolon.account_api import OwnKeysInput, add_account_routes
from eidolon.admin_api import add_admin_routes
from eidolon.dashboard import add_dashboard_routes
from eidolon.admin_users_api import add_admin_user_routes
from eidolon.admin_config_api import add_admin_config_routes
from eidolon.admin_prices_api import add_admin_price_routes
from eidolon.sessions import UserId, session_middleware
from eidolon.stand_outfits import list_path, outfit_path
from eidolon.store import Conversation
from eidolon.turn_outcome import TurnOutcome
from eidolon.usage import OverLimit
from eidolon.world import World


class NewConversation(BaseModel):
    character_id: str


class TurnInput(BaseModel):
    text: str
    own_keys: OwnKeysInput | None = None
    """The user's own keys, which their browser keeps, for the turn to run on; the shape
    calls bring too. A turn uses only the LLM, voice keys brought along go unused."""
    own_llm: object = None
    """Where pages from before brought their own LLM. Transitional, to be deleted once no
    such page is left open: a turn bringing it is refused, asking for a refresh, rather
    than quietly run on the deployer's key and counted."""


class CallRequest(BaseModel):
    conversation_id: str
    muted: bool = False
    quality: Quality = "standard"
    own_keys: OwnKeysInput | None = None
    """The user's own keys, which their browser keeps, for the call to run on."""


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


class IceCandidateInput(BaseModel):
    candidate: str
    sdp_mid: str
    sdp_mline_index: int


class IceCandidates(BaseModel):
    """ICE candidates the browser trickles in for one of its calls."""

    pc_id: str
    candidates: list[IceCandidateInput]


DeviceTimezone = Annotated[str | None, Header(alias="X-Timezone")]
"""The time zone the browser detected; the producer profile's own time zone overrides it."""


def _stand(character: Character, assets_url: str | None) -> dict | None:
    """Her stand on the call screen: where her default outfit's files are, and her outfit
    list (`stand_outfits`). None, and her call background alone, unless her idol, her
    default outfit and the stand assets are all configured."""
    if character.idol_id is None or character.default_outfit is None or assets_url is None:
        return None
    outfit = character.default_outfit
    return {
        "default_outfit": {"id": outfit, "url": f"{assets_url}/{outfit_path(outfit)}"},
        "outfits_url": f"{assets_url}/{list_path(character.idol_id)}",
    }


def _greeting(character: Character, assets_url: str | None) -> dict | None:
    """Her greeting on the landing page: what she says as people see it, its subtitle, and
    where `eidolon greeting upload` puts its audio (`greeting_path`), without asking the
    bucket whether it is there; no audio unless the stand assets and her voice are
    configured. None without a greeting."""
    greeting = character.greeting
    if greeting is None:
        return None
    path = greeting_path(character)
    return {
        "ja": greeting.ja,
        "subtitle": greeting.subtitle,
        "audio_url": f"{assets_url}/{path}" if assets_url and path else None,
    }


def _unit(character: Character, world: World | None) -> dict:
    """Her unit, its reading in hiragana, and where it is in the units' official order
    (`World.unit_of`); all None without the world setting, or if its sources could not
    agree on her unit."""
    unit, order = (world.unit_of(character.name) if world else None) or (None, None)
    reading = world.units[order].reading if world and order is not None else None
    return {"unit": unit, "unit_reading": reading, "unit_order": order}


def create_app(backend: Backend) -> FastAPI:
    """The API over `backend`, which the app closes when it shuts down."""
    store, characters, engine = backend.store, backend.characters, backend.engine
    memory, calls, admissions = backend.memories, backend.calls, backend.admissions

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await backend.start()
        yield
        await backend.aclose()

    app = FastAPI(title="Eidolon-SC", lifespan=lifespan)
    app.state.backend = backend
    app.middleware("http")(session_middleware(backend.settings))

    @app.exception_handler(OverLimit)
    async def over_limit(_: Request, e: OverLimit) -> JSONResponse:
        """Refused for now, with when the user can go on (also as `Retry-After`); or, set
        to their own keys only, with no time to wait for."""
        if e.retry_at is None:
            return JSONResponse({"detail": str(e), "retry_at": None}, status_code=429)
        wait = max(1, math.ceil((e.retry_at - e.now).total_seconds()))
        return JSONResponse(
            {"detail": str(e), "retry_at": e.retry_at.isoformat()},
            status_code=429,
            headers={"Retry-After": str(wait)},
        )

    @app.exception_handler(CallsUnavailable)
    async def calls_unavailable(_: Request, e: CallsUnavailable) -> JSONResponse:
        return JSONResponse({"detail": str(e)}, status_code=503)

    @app.exception_handler(UnknownService)
    async def unknown_service(_: Request, e: UnknownService) -> JSONResponse:
        return JSONResponse({"detail": str(e)}, status_code=422)

    @app.exception_handler(CallNotFound)
    async def call_not_found(_: Request, e: CallNotFound) -> JSONResponse:
        return JSONResponse({"detail": str(e)}, status_code=404)

    @app.exception_handler(CallFailed)
    async def call_failed(_: Request, e: CallFailed) -> JSONResponse:
        return JSONResponse({"detail": str(e)}, status_code=500)

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

    add_account_routes(app, backend)
    add_admin_routes(app, backend)
    add_dashboard_routes(app, backend)
    add_admin_user_routes(app, backend)
    add_admin_config_routes(app, backend)
    add_admin_price_routes(app, backend)

    @app.get("/api/ice-servers")
    def ice_servers(user_id: UserId, own: str = "") -> dict:
        """What the browser needs before calling, if the call is to bring the user's own
        keys for the services `own` names (as `llm,tts,stt`), but none of the keys; also
        tells it when calls are unavailable."""
        return calls.ice_servers(user_id, named_services(own))

    @app.post("/api/offer")
    async def offer(
        body: Offer, user_id: UserId, device_timezone: DeviceTimezone = None
    ) -> dict:
        """WebRTC signalling: a new call into one of the user's conversations, on the user's
        own keys it brings, or a renegotiation, which brings none."""
        description = SessionDescription(body.sdp, body.type)
        if body.pc_id is not None:  # renegotiating, possibly on a fresh peer connection
            return await calls.renegotiate(
                user_id, body.pc_id, description, bool(body.restart_pc)
            )
        if body.call is None:
            raise HTTPException(422, "缺少要通话的对话")
        conversation = conversation_or_404(body.call.conversation_id, user_id)
        return await calls.start(
            user_id,
            conversation,
            characters[conversation.character_id],
            CallOptions(body.call.muted, body.call.quality, device_timezone),
            description,
            body.call.own_keys.brought() if body.call.own_keys else BroughtKeys(),
        )

    @app.patch("/api/offer")
    async def ice_candidates(body: IceCandidates, user_id: UserId) -> dict:
        candidates = [
            IceCandidate(c.candidate, c.sdp_mid, c.sdp_mline_index) for c in body.candidates
        ]
        await calls.add_candidates(user_id, body.pc_id, candidates)
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
    def list_characters() -> list[dict]:
        """Who there is to talk to; shown before signing in too, and on the landing page.
        In the order of their idol numbers, those without one after them as configured."""
        listed = sorted(characters.values(), key=lambda c: (c.idol_id is None, c.idol_id or 0))
        return [
            {
                "id": c.id,
                "name": c.name,
                "intro": c.intro,
                "avatar_url": f"/api/characters/{c.id}/avatar" if c.avatar else None,
                "color": c.color,
                "background_url": f"/api/characters/{c.id}/background" if c.background else None,
                "stand": _stand(c, backend.settings.stand_assets_url),
                "idol_id": c.idol_id,
                "name_zh": c.name_zh,
                "name_kana": c.name_kana,
                "name_romaji": c.name_romaji,
                **_unit(c, backend.world),
                "greeting": _greeting(c, backend.settings.stand_assets_url),
            }
            for c in listed
        ]

    @app.get("/api/characters/{character_id}/avatar")
    def character_avatar(character_id: str) -> FileResponse:
        character = characters.get(character_id)
        if character is None or character.avatar is None:
            raise HTTPException(404, "没有这位角色的头像")
        return FileResponse(character.avatar)

    @app.get("/api/characters/{character_id}/background")
    def character_background(character_id: str) -> FileResponse:
        """The picture behind her call screen, served like her avatar."""
        character = characters.get(character_id)
        if character is None or character.background is None:
            raise HTTPException(404, "没有这位角色的通话背景图")
        return FileResponse(character.background)

    @app.get("/api/memories")
    async def list_memories(user_id: UserId) -> list[dict]:
        """Newest first, each with the name of the character it was told to and whether
        it has been superseded (ADR-0014)."""
        return [
            {
                "id": m.id,
                "text": m.text,
                "source_character_id": m.source_character_id,
                "source_character_name": m.source_character_name,
                "created_at": m.created_at,
                "superseded": m.superseded_by is not None,
            }
            for m in await memory.entries(user_id)
        ]

    @app.delete("/api/memories/{memory_id}", status_code=204)
    async def delete_memory(memory_id: int, user_id: UserId) -> None:
        if not await memory.delete(user_id, memory_id):
            raise HTTPException(404, "记忆不存在")

    @app.delete("/api/memories", status_code=204)
    async def clear_memories(user_id: UserId) -> None:
        await memory.clear(user_id)

    @app.post("/api/conversations", status_code=201)
    def create_conversation(body: NewConversation, user_id: UserId) -> dict:
        if body.character_id not in characters:
            raise HTTPException(404, "角色不存在")
        return asdict(store.create_conversation(user_id, body.character_id))

    @app.get("/api/conversations")
    def list_conversations(character_id: str, user_id: UserId) -> list[dict]:
        return [asdict(c) for c in store.list_conversations(user_id, character_id)]

    @app.get("/api/conversations/latest")
    def latest_conversations(user_id: UserId) -> list[dict]:
        """For the conversation list: each character's newest conversation with the user and
        its last message (null while it has none), in one request."""
        return [
            {
                "character_id": c.character_id,
                "conversation_id": c.id,
                "created_at": c.created_at,
                "last_message": None
                if last is None
                else {
                    "role": last.role,
                    "text": last.text,
                    "ja": last.without_cues().ja,
                    "zh": last.without_cues().zh,
                    "created_at": last.created_at,
                },
            }
            for c, last in store.latest_conversations(user_id)
        ]

    @app.get("/api/conversations/{conversation_id}/messages")
    def list_messages(conversation_id: str, user_id: UserId) -> list[dict]:
        conversation = conversation_or_404(conversation_id, user_id)
        return [asdict(m.without_cues()) for m in store.list_messages(conversation.id)]

    @app.post("/api/conversations/{conversation_id}/turns")
    def text_turn(
        conversation_id: str,
        body: TurnInput,
        user_id: UserId,
        device_timezone: DeviceTimezone = None,
    ) -> StreamingResponse:
        conversation = conversation_or_404(conversation_id, user_id)
        if body.own_llm is not None:  # transitional: see `TurnInput.own_llm`
            raise HTTPException(422, "页面已经更新，请刷新后再发")
        brought = body.own_keys.brought() if body.own_keys else BroughtKeys()
        admission = admissions.turn(user_id, conversation.character_id, brought)
        outcome = TurnOutcome(admission.recording, admission.settle)

        async def events() -> AsyncIterator[str]:
            with outcome.running():
                turn = engine.turn(conversation, body.text, admission.llms, device_timezone)
                async for event in turn:
                    outcome.see(event)
                    if isinstance(event, SegmentDelta):
                        outcome.began_speaking()  # the reply's first words have appeared
                    if isinstance(event, SegmentComplete | SpeechDelta):
                        continue
                    yield _sse(asdict(event))

        return _TurnResponse(events(), lambda: outcome.over(cut_short_by_failure=False))

    return app


class _TurnResponse(StreamingResponse):
    """A text turn's events, `end` called once they are sent or the page is gone, even
    gone before they began, when the stream of them never runs."""

    def __init__(self, events: AsyncIterator[str], end: Callable[[], None]) -> None:
        super().__init__(
            events,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
        self._end = end

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self._end()


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
