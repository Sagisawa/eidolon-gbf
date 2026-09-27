"""The API for signing in and out.

Signing in with Google or GitHub goes through the browser:

    /api/auth/{provider}/start     → the provider's sign-in page
    /api/auth/{provider}/callback  ← back from it, with a code and the state sent there

The state is kept in a short-lived cookie of its own, so a callback can only finish a
sign-in this browser started. The callback sends the browser on: home when signed in,
the sign-in page with `?error=<reason>` when not (see `accounts.Refusal`, plus `state`
for a callback this browser did not start or that expired, `cancelled` when the user
turned the provider down, and `provider` when the provider could not be reached).
"""

import logging
import secrets

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from eidolon.accounts import SignInRefused
from eidolon.assembly import Backend
from eidolon.identity import PROVIDER_NAMES, IdentityError
from eidolon.sessions import (
    SESSION_COOKIE,
    clear_session_cookie,
    set_session_cookie,
)

log = logging.getLogger(__name__)

STATE_COOKIE = "eidolon_oauth_state"
STATE_LIFETIME = 600
"""How long, in seconds, the browser has to sign in at the provider and come back."""


class DevLogin(BaseModel):
    name: str = Field(min_length=1, max_length=40)


def add_account_routes(app: FastAPI, backend: Backend) -> None:
    store, settings, clock = backend.store, backend.settings, backend.clock
    accounts, providers = backend.accounts, backend.identity_providers

    def callback_url(provider: str) -> str:
        return f"{settings.public_origin}/api/auth/{provider}/callback"

    def signed_in(user_id: str, response: Response, request: Request) -> None:
        """Start a session for the user in this browser, ending the one it had."""
        if old := request.cookies.get(SESSION_COOKIE):
            store.end_session(old)
        set_session_cookie(response, store.create_session(user_id, clock()), settings)

    @app.get("/api/auth/providers")
    def sign_in_providers() -> dict:
        """The ways to sign in on offer, in the order to show them."""
        return {
            "providers": [p for p in PROVIDER_NAMES if p in providers],
            "dev_login": settings.dev_login,
        }

    @app.get("/api/auth/{provider}/start")
    def start_sign_in(provider: str) -> RedirectResponse:
        identity_provider = providers.get(provider)  # pyright: ignore[reportArgumentType]
        if identity_provider is None:
            raise HTTPException(404, "没有这种登录方式")
        state = secrets.token_urlsafe(24)
        response = RedirectResponse(
            identity_provider.authorize_url(state, callback_url(provider)), status_code=302
        )
        response.set_cookie(
            STATE_COOKIE,
            f"{provider}:{state}",
            max_age=STATE_LIFETIME,
            path="/api/auth",
            httponly=True,
            samesite="lax",
            secure=settings.domain is not None,
        )
        return response

    @app.get("/api/auth/{provider}/callback")
    async def finish_sign_in(
        provider: str,
        request: Request,
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
    ) -> RedirectResponse:
        expected_provider, _, expected_state = request.cookies.get(STATE_COOKIE, "").partition(":")

        def go(to: str) -> RedirectResponse:
            response = RedirectResponse(to, status_code=302)
            response.delete_cookie(STATE_COOKIE, path="/api/auth")
            return response

        identity_provider = providers.get(provider)  # pyright: ignore[reportArgumentType]
        if (
            identity_provider is None
            or not state
            or not expected_state
            or expected_provider != provider
            or not secrets.compare_digest(state, expected_state)
        ):
            return go("/login?error=state")
        if error or not code:
            return go("/login?error=cancelled")
        try:
            identity = await identity_provider.identify(code, callback_url(provider))
        except IdentityError:
            log.warning("signing in with %s failed", provider, exc_info=True)
            return go("/login?error=provider")
        try:
            user = accounts.sign_in(identity)
        except SignInRefused as e:
            return go(f"/login?error={e.reason}")
        response = go("/")
        signed_in(user.id, response, request)
        return response

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request, response: Response) -> None:
        """Sign this browser out; its session ends even if it has already expired."""
        if token := request.cookies.get(SESSION_COOKIE):
            store.end_session(token)
        clear_session_cookie(response, settings)

    if settings.dev_login:

        @app.post("/api/auth/dev-login", status_code=204)
        def dev_login(body: DevLogin, request: Request, response: Response) -> None:
            """Sign in as the user with this name, made if there is none (development only)."""
            user = store.first_user_named(body.name) or store.create_user(body.name)
            signed_in(user.id, response, request)
