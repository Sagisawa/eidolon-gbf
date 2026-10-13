"""Gifts over HTTP (GLOSSARY.md「礼物」): the catalog for users who agreed to the terms, at
`/api/gifts/catalog`. It never says which gifts a character likes: the gifts page gives
none of that away."""

from fastapi import FastAPI

from eidolon.assembly import Backend
from eidolon.sessions import UserId


def add_gift_routes(app: FastAPI, backend: Backend) -> None:
    gifts = backend.gifts

    @app.get("/api/gifts/catalog")
    def catalog(_: UserId) -> list[dict]:
        """Every gift, retired ones too (whoever has one still sees it), in catalog order."""
        return [g.listed() for g in gifts.values()]
