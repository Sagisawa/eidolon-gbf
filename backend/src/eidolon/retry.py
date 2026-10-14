"""Asking an outside service again, once, when a request a turn waits on fails in passing.

A turn's query embedding and its reranking hold up her reply, so each request is given
only a few seconds (`TURN_TIMEOUT`), and one that times out, cannot connect or is
answered 429 or 5xx is made again at once (`retry_once`): a hiccup goes unnoticed, a
service that is down costs the turn a few seconds, not half a minute. One refused
otherwise (another 4xx) or answered with what cannot be read would only fail again.

Each attempt is a service call of its own on the dashboard: whoever times the request
(`activity.timed`) is told of a failed one (`telling_retries`) as it is made again.
"""

import logging
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TypeVar

log = logging.getLogger(__name__)

TURN_TIMEOUT = 3.0
"""Seconds a request a turn waits on, a query embedded or candidates reranked, is given.
Of those in production (2026-10-14), 99 in 100 query embeddings took 0.82 s or less and
99 in 100 rerankings 0.83 s or less."""

T = TypeVar("T")


class ServiceError(RuntimeError):
    """A request to an outside service failed; `transient` if it failed in passing (it
    timed out, could not connect, or was answered 429 or 5xx), so asking again may not."""

    def __init__(self, message: str, *, transient: bool = False) -> None:
        super().__init__(message)
        self.transient = transient


def transient_status(status: int) -> bool:
    """Whether a service answering `status` may answer otherwise if asked again."""
    return status == 429 or status >= 500


async def retry_once(attempt: Callable[[], Awaitable[T]]) -> T:
    """What `attempt` comes to, made again at once if it fails in passing. Raises the
    ServiceError of the attempt failing last."""
    try:
        return await attempt()
    except ServiceError as e:
        if not e.transient:
            raise
        log.info("a request failed in passing; asking again: %s", e)
        if (told := _told.get()) is not None:
            told(e)
    return await attempt()


_told: ContextVar[Callable[[ServiceError], None] | None] = ContextVar("retries", default=None)


@contextmanager
def telling_retries(to: Callable[[ServiceError], None]) -> Iterator[None]:
    """Tell `to` of each attempt made meanwhile, in this context, that failed and is being
    made again, with what it failed with."""
    token = _told.set(to)
    try:
        yield
    finally:
        _told.reset(token)
