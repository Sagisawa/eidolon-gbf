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

An admin may also set a user's own limits on turns and calls an hour, each apart, or take
them off; the length of a call is the same for everyone.
"""

from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from eidolon.admin_api import Admin, is_admin
from eidolon.assembly import Backend
from eidolon.own_keys import SERVICES
from eidolon.store import NotFound, User
from eidolon.usage import UserLimits

PAGE_SIZE = 50
"""How many users a page of the list has unless asked for another number."""


class BanInput(BaseModel):
    note: str | None = Field(None, max_length=500)
    """Why, for the admins only; the banned user never sees it."""


Limit = Annotated[int, Field(ge=0, le=100_000)] | Literal["unlimited"] | None


class LimitsInput(BaseModel):
    """A user's own limits an hour: a number (0: on their own keys only), "unlimited", or
    None, the deployment's; at least one of the two set."""

    turns_per_hour: Limit = None
    calls_per_hour: Limit = None
    note: str | None = Field(None, max_length=500)
    """Why, for the admins only."""

    @model_validator(mode="after")
    def _any(self) -> "LimitsInput":
        if self.turns_per_hour is None and self.calls_per_hour is None:
            raise ValueError("至少要单独设定回合数或通话次数中的一项")
        return self


def add_admin_user_routes(app: FastAPI, backend: Backend) -> None:
    store, settings, clock, usage = backend.store, backend.settings, backend.clock, backend.usage

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
            "limits": limits(user.id),
        }

    def limits(user_id: str) -> dict | None:
        """The user's own limits, if an admin set any; a limit not set (None) follows the
        deployment's."""
        own = usage.user_limits(user_id)
        return asdict(own) if own else None

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

    @app.delete("/api/admin/users/{user_id}", status_code=204)
    async def delete_user(user_id: str, _: Admin) -> None:
        """Delete the user and all their data, as they would themselves; 409 for an admin."""
        if details(user_id)["is_admin"]:
            raise HTTPException(409, "不能在后台删除管理者")
        await backend.accounts.delete(user_id)

    @app.delete("/api/admin/users/{user_id}/ban")
    def unban(user_id: str, _: Admin) -> dict:
        """Lift the user's ban, and its note; they may sign in again."""
        details(user_id)
        store.set_banned(user_id, None)
        return details(user_id)

    @app.put("/api/admin/users/{user_id}/limits")
    def set_limits(user_id: str, body: LimitsInput, _: Admin) -> dict:
        """Set the user's own limits, replacing those they had; from their next turn or
        call on."""
        details(user_id)
        usage.set_user_limits(user_id, UserLimits(
            body.turns_per_hour, body.calls_per_hour, (body.note or "").strip() or None,
        ))
        return details(user_id)

    @app.delete("/api/admin/users/{user_id}/limits")
    def take_off_limits(user_id: str, _: Admin) -> dict:
        """Take off the user's own limits; the deployment's hold for them again."""
        details(user_id)
        usage.set_user_limits(user_id, None)
        return details(user_id)
