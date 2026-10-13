"""Gifts over HTTP (GLOSSARY.md「礼物」「抽奖」), for users who agreed to the terms: the
catalog at `/api/gifts/catalog`, and what the user has at `/api/gifts`, read as the
producer's own day is where they are (`X-Timezone`). Neither says which gifts a character
likes: the gifts page gives none of that away."""

from typing import Annotated

from fastapi import FastAPI, Header

from eidolon.assembly import Backend
from eidolon.producer import effective_timezone
from eidolon.sessions import UserId


def add_gift_routes(app: FastAPI, backend: Backend) -> None:
    catalog, gifts, store = backend.gift_catalog, backend.gifts, backend.store

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
