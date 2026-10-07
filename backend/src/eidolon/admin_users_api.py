"""The users page of the admin console: listing and searching users, looking one up, and
banning or unbanning them (ADR-0013).

What an admin sees of a user is who they are and how they use the deployment: their
sign-in methods (email included), when they joined and were last active, whether they
are banned and why, whether they are an admin, and for which services they brought their
own keys, only whether they did. Never what they said, what was remembered of them or
their producer profile.

Banning here is the same as `eidolon user ban`, both through `Store.set_banned`: the
user is signed out everywhere, their calls are hung up within seconds by the calls'
polling (`call.USER_CHECK_INTERVAL`), and they cannot sign in until unbanned. No admin
can be banned here, oneself included, so that no admin locks the others, or themselves,
out; the deployer can still on the command line.
"""

from datetime import datetime
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from eidolon.admin_api import Admin, is_admin
from eidolon.assembly import Backend
from eidolon.own_keys import SERVICES
from eidolon.store import NotFound, User

PAGE_SIZE = 50
"""How many users a page of the list has unless asked for another number."""


class BanInput(BaseModel):
    note: str | None = Field(None, max_length=500)
    """Why, for the admins only; the banned user never sees it."""


def add_admin_user_routes(app: FastAPI, backend: Backend) -> None:
    store, settings, clock = backend.store, backend.settings, backend.clock

    def described(users: list[User]) -> list[dict]:
        """What the list shows of each user."""
        active = store.last_active([u.id for u in users]) if users else {}
        return [summary(user, active.get(user.id)) for user in users]

    def summary(user: User, last_active: datetime | None) -> dict:
        own_keys = store.own_keys(user.id)
        return {
            "id": user.id,
            "name": user.name,
            "sign_in_methods": [
                {"provider": m.provider, "subject": m.subject,
                 "display_name": m.display_name, "email": m.email}
                for m in store.sign_in_methods(user.id)
            ],
            "created_at": user.created_at,
            "last_active_at": last_active.isoformat() if last_active else None,
            "banned": user.banned_at is not None,
            "is_admin": is_admin(store, settings, user.id),
            "own_keys": {service: service in own_keys for service in SERVICES},
        }

    def details(user_id: str) -> dict:
        """What a user's own page shows of them; 404 for no such user."""
        try:
            user = store.get_user(user_id)
        except NotFound:
            raise HTTPException(404, "没有这位用户") from None
        [shown] = described([user])
        return shown | {"banned_at": user.banned_at, "ban_note": user.ban_note}

    @app.get("/api/admin/users")
    def list_users(
        _: Admin,
        q: str = "",
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = PAGE_SIZE,
    ) -> dict:
        """A page of the users, newest first, or of those `q` finds by name, email or user
        id; with how many there are in all."""
        users, total = store.find_users(q, offset, limit)
        return {"users": described(users), "total": total}

    @app.get("/api/admin/users/{user_id}")
    def user_details(user_id: str, _: Admin) -> dict:
        """A user, with when and why they were banned."""
        return details(user_id)

    @app.post("/api/admin/users/{user_id}/ban")
    def ban(user_id: str, body: BanInput, _: Admin) -> dict:
        """Ban the user, with a note for the admins; 409 for an admin."""
        found = details(user_id)
        if found["is_admin"]:
            raise HTTPException(409, "不能在后台封禁管理者")
        store.set_banned(user_id, clock(), (body.note or "").strip() or None)
        return details(user_id)

    @app.delete("/api/admin/users/{user_id}/ban")
    def unban(user_id: str, _: Admin) -> dict:
        """Lift the user's ban, and its note; they may sign in again."""
        details(user_id)
        store.set_banned(user_id, None)
        return details(user_id)
