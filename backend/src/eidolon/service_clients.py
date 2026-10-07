"""Making the deployer's service clients from their configuration, and replacing one while
the backend runs (ADR-0013).

`ServiceClients` is the one place the deployer's clients are made from settings: at
startup by `assembly.build`, and whenever the live configuration changes (see
`live_config`). Tests pass in a fake.

`Swappable` holds the client a service runs on now. Each turn and each call takes a
`Lease` on it as it starts and runs on that client to the end, whatever replaces it
meanwhile; a client replaced is closed once the last lease on it is released.
"""

import asyncio
import threading
from collections.abc import Awaitable, Callable
from typing import Generic, Protocol, TypeVar

from eidolon.config import LLMSettings
from eidolon.llm import ChatLLM
from eidolon.llm.providers import open_llm


class ServiceClients(Protocol):
    """Makes the deployer's clients for the services, each from its settings."""

    def chat_llm(self, settings: LLMSettings) -> ChatLLM:
        """The model `settings` describe, closed by whoever made it through this."""
        ...


class ProviderClients:
    """The clients of the real services."""

    def chat_llm(self, settings: LLMSettings) -> ChatLLM:
        return open_llm(settings)


class Closable(Protocol):
    def aclose(self) -> Awaitable[None]: ...


C = TypeVar("C", bound=Closable)


class Lease(Generic[C]):
    """A turn's or a call's hold on the client it runs on; released once, when it ends."""

    def __init__(self, client: C, release: Callable[[], None]) -> None:
        self.client = client
        self._release: Callable[[], None] | None = release

    def release(self) -> None:
        """Let go of the client; again does nothing."""
        if self._release is not None:
            release, self._release = self._release, None
            release()


class _Held(Generic[C]):
    def __init__(self, client: C, owned: bool) -> None:
        self.client = client
        self.owned = owned
        """Whether it is this holder's to close: one passed in by a test is not."""
        self.leases = 0


class Swappable(Generic[C]):
    """The client a service runs on now, replaced as its configuration changes.

    Leases are taken from any thread (the API's synchronous routes run in a pool), so
    the counts are kept under a lock; a client retired by its last lease is closed on the
    event loop it was replaced on."""

    def __init__(self, client: C, *, owned: bool = True) -> None:
        self._lock = threading.Lock()
        self._current = _Held(client, owned)
        self._retired: set[_Held[C]] = set()
        self._closing: set[asyncio.Task[None]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def current(self) -> C:
        return self._current.client

    def lease(self) -> Lease[C]:
        with self._lock:
            held = self._current
            held.leases += 1
        return Lease(held.client, lambda: self._release(held))

    async def replace(self, client: C) -> None:
        """Run whatever starts from now on on `client`; the client it replaces is closed
        now if nothing is on it, else once the last turn or call on it has ended."""
        self._loop = asyncio.get_running_loop()
        with self._lock:
            old, self._current = self._current, _Held(client, owned=True)
            idle = old.leases == 0
            if not idle:
                self._retired.add(old)
        if idle and old.owned:
            await old.client.aclose()

    async def aclose(self) -> None:
        """Close every client still held, as the backend shuts down, whatever is on it."""
        with self._lock:
            held = [self._current, *self._retired]
            self._retired.clear()
        for h in held:
            if h.owned:
                await h.client.aclose()
        await asyncio.gather(*self._closing, return_exceptions=True)

    def _release(self, held: _Held[C]) -> None:
        with self._lock:
            held.leases -= 1
            done = held in self._retired and held.leases == 0
            if done:
                self._retired.discard(held)
        if done and held.owned:
            self._close_later(held.client)

    def _close_later(self, client: C) -> None:
        """Close `client` on the loop it was replaced on, from whichever thread."""
        loop = self._loop
        if loop is None or loop.is_closed():
            return

        def close() -> None:
            task = loop.create_task(_close(client))
            self._closing.add(task)
            task.add_done_callback(self._closing.discard)

        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            close()
        else:
            loop.call_soon_threadsafe(close)


async def _close(client: Closable) -> None:
    await client.aclose()
