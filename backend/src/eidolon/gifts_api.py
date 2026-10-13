"""Gifts over HTTP (GLOSSARY.md「礼物」「抽奖」), for users who agreed to the terms: the
catalog at `/api/gifts/catalog`, what the user has at `/api/gifts`, and drawing at
`/api/gifts/draws`, the latter two as the producer's own day is where they are
(`X-Timezone`). None says which gifts a character likes: the gifts page gives none of that
away. Gifts not open, drawing is refused with 409 and `gifts_closed`, told apart from a
cooldown's 409, so the page shows them closed."""

from typing import Annotated

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from eidolon.assembly import Backend
from eidolon.gifts import GiftsClosed, NoDraws
from eidolon.producer import effective_timezone
from eidolon.sessions import UserId


class DrawInput(BaseModel):
    all: bool = False
    """Draw every chance the user has, not just one."""


def add_gift_routes(app: FastAPI, backend: Backend) -> None:
    catalog, gifts, store = backend.gift_catalog, backend.gifts, backend.store

    @app.exception_handler(GiftsClosed)
    async def gifts_closed(_: Request, e: GiftsClosed) -> JSONResponse:
        return JSONResponse({"detail": str(e), "gifts_closed": True}, status_code=409)

    @app.exception_handler(NoDraws)
    async def no_draws(_: Request, e: NoDraws) -> JSONResponse:
        return JSONResponse({"detail": str(e)}, status_code=409)

    @app.get("/api/gifts/catalog")
    def read_catalog(_: UserId) -> list[dict]:
        """Every gift, retired ones too (whoever has one still sees it), in catalog order."""
        return [g.described() for g in catalog.values()]

    @app.get("/api/gifts")
    def read_state(
        user_id: UserId,
        device_timezone: Annotated[str | None, Header(alias="X-Timezone")] = None,
    ) -> dict:
        """What the user has, having been given the draw chances due today; whether gifts
        are open, and if so each character's affinity, for choosing whom to give to."""
        timezone = effective_timezone(store.get_profile(user_id), device_timezone)
        return gifts.state(user_id, timezone).shown()

    @app.post("/api/gifts/draws")
    def draw(
        body: DrawInput,
        user_id: UserId,
        device_timezone: Annotated[str | None, Header(alias="X-Timezone")] = None,
    ) -> dict:
        """Draw once or every chance, having been given those due today: what each draw
        gave, in order, and how many chances are left."""
        timezone = effective_timezone(store.get_profile(user_id), device_timezone)
        return gifts.draw(user_id, timezone, all=body.all).shown()
