"""The API for signing in and out, and for the user's account.

Signing in with Google or GitHub goes through the browser:

    /api/auth/{provider}/start     → the provider's sign-in page
    /api/auth/{provider}/callback  ← back from it, with a code and the state sent there

The state is kept in a short-lived cookie of its own, so a callback can only finish a
sign-in this browser started. The callback sends the browser on: home when signed in,
the sign-in page with `?error=<reason>` when not (see `accounts.Refusal`, plus `state`
for a callback this browser did not start or that expired, `cancelled` when the user
turned the provider down, and `provider` when the provider could not be reached).

A signed-in user links another identity the same way, starting with `?link=1`; the
callback then sends the browser back to the settings page, with `?linked=<provider>` or
`?error=<reason>`.
"""

import logging
import secrets

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, model_validator

from eidolon.accounts import SignInRefused
from eidolon.admin_api import is_admin
from eidolon.assembly import Backend
from eidolon.config import LLM_PROTOCOLS, LLMProtocol, SttProvider
from eidolon.identity import PROVIDER_NAMES, IdentityError
from eidolon.own_keys import (
    SERVICES,
    OwnKeyRejected,
    OwnKeysUnavailable,
    OwnLLMSettings,
)
from eidolon.store import LastSignInMethod
from eidolon.sessions import (
    SESSION_COOKIE,
    SignedIn,
    UserId,
    clear_session_cookie,
    session_user,
    set_session_cookie,
)

log = logging.getLogger(__name__)

STATE_COOKIE = "eidolon_oauth_state"
STATE_LIFETIME = 600
"""How long, in seconds, the browser has to sign in at the provider and come back."""


class DevLogin(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class Deletion(BaseModel):
    """Deleting the user's data needs saying so, not just a request that might be a slip."""

    confirm: bool

    @model_validator(mode="after")
    def _confirmed(self) -> "Deletion":
        if not self.confirm:
            raise ValueError("需要确认才能删除全部数据")
        return self


class OwnLLMInput(BaseModel):
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str = Field(min_length=8, max_length=500, pattern=r"^[\x21-\x7e]+$")
    model: str = Field(min_length=1, max_length=200)
    protocol: LLMProtocol = "chat-completions"


class OwnSpeechKeyInput(BaseModel):
    api_key: str = Field(min_length=8, max_length=500, pattern=r"^[\x21-\x7e]+$")
    provider: SttProvider = "soniox"
    """For speech recognition, the service the key is for."""


class Consent(BaseModel):
    """Agreeing to the privacy policy and terms of use, and saying they are 13 or older."""

    agree_to_terms: bool
    at_least_13: bool

    @model_validator(mode="after")
    def _both(self) -> "Consent":
        if not self.agree_to_terms:
            raise ValueError("需要同意隐私政策和使用条款")
        if not self.at_least_13:
            raise ValueError("需要年满 13 岁才能使用")
        return self


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
    def start_sign_in(provider: str, request: Request, link: bool = False) -> RedirectResponse:
        """Off to the provider to sign in, or with `link`, to link another identity to the
        signed-in user."""
        identity_provider = providers.get(provider)  # pyright: ignore[reportArgumentType]
        if identity_provider is None:
            raise HTTPException(404, "没有这种登录方式")
        if link:
            user = session_user(request)
            if user is None or user.consented_at is None:
                return RedirectResponse("/login", status_code=302)
        state = secrets.token_urlsafe(24)
        response = RedirectResponse(
            identity_provider.authorize_url(state, callback_url(provider)), status_code=302
        )
        response.set_cookie(
            STATE_COOKIE,
            f"{'link' if link else 'login'}:{provider}:{state}",
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
        purpose, expected_provider, expected_state = (
            request.cookies.get(STATE_COOKIE, "").split(":", 2) + ["", ""]
        )[:3]
        linking = purpose == "link"
        back = "/settings" if linking else "/login"

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
            return go(f"{back}?error=state")
        if error or not code:
            return go(f"{back}?error=cancelled")
        try:
            identity = await identity_provider.identify(code, callback_url(provider))
        except IdentityError:
            log.warning("signing in with %s failed", provider, exc_info=True)
            return go(f"{back}?error=provider")
        try:
            if linking:
                user = session_user(request)
                if user is None or user.consented_at is None:
                    return go("/login?error=state")
                accounts.link(user.id, identity)
                return go(f"/settings?linked={provider}")
            user = accounts.sign_in(identity)
        except SignInRefused as e:
            return go(f"{back}?error={e.reason}")
        response = go("/")
        signed_in(user.id, response, request)
        return response

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request, response: Response) -> None:
        """Sign this browser out; its session ends even if it has already expired."""
        if token := request.cookies.get(SESSION_COOKIE):
            store.end_session(token)
        clear_session_cookie(response, settings)

    @app.get("/api/account")
    def account(user_id: UserId) -> dict:
        """The signed-in user, the identities they sign in with, and whether they are an
        admin, who may enter the admin console."""
        return {
            "name": store.get_user(user_id).name,
            "sign_in_methods": [
                {"provider": m.provider, "display_name": m.display_name, "email": m.email}
                for m in store.sign_in_methods(user_id)
            ],
            "is_admin": is_admin(store, settings, user_id),
        }

    @app.delete("/api/account/sign-in-methods/{provider}", status_code=204)
    def unlink(provider: str, user_id: UserId) -> None:
        """Stop signing in with the identity at `provider`; never the last one."""
        try:
            found = store.remove_sign_in_method(user_id, provider)
        except LastSignInMethod:
            raise HTTPException(409, "这是你唯一的登录方式，解绑后就无法再登录了") from None
        if not found:
            raise HTTPException(404, "没有绑定这种登录方式")

    @app.post("/api/account/logout-everywhere", status_code=204)
    def logout_everywhere(user_id: UserId, response: Response) -> None:
        """Sign the user out on every device, this one included."""
        store.end_sessions(user_id)
        clear_session_cookie(response, settings)

    @app.post("/api/account/delete", status_code=204)
    async def delete_account(body: Deletion, user: SignedIn, response: Response) -> None:
        """Delete the user and all their data for good, signing them out everywhere; allowed
        before they agree to the terms too."""
        await accounts.delete(user.id)
        clear_session_cookie(response, settings)

    own_keys = backend.own_keys

    @app.exception_handler(OwnKeysUnavailable)
    async def own_keys_unavailable(_: Request, e: OwnKeysUnavailable) -> JSONResponse:
        return JSONResponse({"detail": str(e)}, status_code=404)

    @app.get("/api/account/keys")
    def list_own_keys(user_id: UserId) -> dict:
        """The keys the user brought, showing only their last 4 characters."""
        return {
            "available": own_keys.available,
            "keys": own_keys.describe(user_id) if own_keys.available else {},
            "exempt": own_keys.exemptions(user_id),
            "protocols": list(LLM_PROTOCOLS),
        }

    @app.put("/api/account/keys/llm")
    async def save_own_llm(body: OwnLLMInput, user_id: UserId) -> dict:
        """Try the user's own LLM, then keep it; 422 with what the service said if the
        try failed."""
        try:
            await own_keys.save_llm(
                user_id,
                OwnLLMSettings(body.base_url.strip(), body.api_key, body.model.strip(),
                               body.protocol),
            )
        except OwnKeyRejected as e:
            raise HTTPException(422, f"试调失败，没有保存：{e}") from None
        return own_keys.describe(user_id)["llm"]

    @app.put("/api/account/keys/{service}")
    async def save_own_speech_key(service: str, body: OwnSpeechKeyInput, user_id: UserId) -> dict:
        """Try the user's own key for speech synthesis ("tts") or recognition ("stt", by
        the service it is for), then keep it; 422 with what the service said if the try
        failed."""
        if service not in ("tts", "stt"):
            raise HTTPException(404, "没有这项服务")
        try:
            await own_keys.save_speech(user_id, service, body.api_key, body.provider)  # pyright: ignore[reportArgumentType]
        except OwnKeyRejected as e:
            raise HTTPException(422, f"试调失败，没有保存：{e}") from None
        return own_keys.describe(user_id)[service]  # pyright: ignore[reportArgumentType]

    @app.delete("/api/account/keys/{service}", status_code=204)
    def delete_own_key(service: str, user_id: UserId) -> None:
        """Forget the user's own key for `service`; the deployer's is used again."""
        if service not in SERVICES or not own_keys.delete(user_id, service):  # pyright: ignore[reportArgumentType]
            raise HTTPException(404, "没有填过这项密钥")

    @app.post("/api/account/consent", status_code=204)
    def consent(body: Consent, user: SignedIn) -> None:
        """Agree to the privacy policy and terms of use, which the rest of the API waits for."""
        store.consent(user.id, clock())

    if settings.dev_login:

        @app.post("/api/auth/dev-login", status_code=204)
        def dev_login(body: DevLogin, request: Request, response: Response) -> None:
            """Sign in as the user with this name, made if there is none (development only)."""
            user = store.first_user_named(body.name) or store.create_user(body.name)
            signed_in(user.id, response, request)
