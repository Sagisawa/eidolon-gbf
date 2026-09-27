"""Signing browsers in: sessions kept in the store, held by the browser in a cookie.

The cookie is httpOnly, so no script on the page can read it, and SameSite=Lax, so other
sites' pages cannot make the browser send it with their forms; over HTTPS in production
it is Secure as well. On top of that every request that changes something must come
from the site's own origin (`check_origin`). A session lasts `SESSION_LIFETIME` after it
was last used; each renewal renews the cookie too.
"""

from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from eidolon.config import Settings
from eidolon.store import SESSION_LIFETIME

SESSION_COOKIE = "eidolon_session"

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.domain is not None,
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        SESSION_COOKIE, path="/", httponly=True, samesite="lax", secure=settings.domain is not None
    )


def origin_allowed(origin: str | None, settings: Settings) -> bool:
    """Whether a request that changes something may come from `origin`. Browsers always
    say where such a request comes from; a request without an Origin is not a browser's,
    so it cannot be riding on a signed-in browser's cookie. In development any page on
    this machine is the site."""
    if origin is None:
        return True
    if settings.domain is not None:
        return origin == settings.public_origin
    parts = urlsplit(origin)
    return parts.scheme == "http" and parts.hostname in _LOCAL_HOSTS


def session_middleware(
    settings: Settings,
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    """Refuses requests that change something from other origins, and renews the cookie
    of a session that was renewed while answering the request."""

    async def middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method not in _SAFE_METHODS and not origin_allowed(
            request.headers.get("origin"), settings
        ):
            return JSONResponse({"detail": "请求来自其他网站，已拒绝"}, status_code=403)
        response = await call_next(request)
        if (token := getattr(request.state, "renewed_session", None)) is not None:
            set_session_cookie(response, token, settings)
        return response

    return middleware
