"""Test doubles for external services."""

import asyncio
from collections.abc import AsyncIterator, Sequence

from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection

from eidolon.call import Call
from eidolon.characters import Character
from eidolon.embedding import EmbeddingError
from eidolon.llm import ChatMessage
from eidolon.retrieval import JudgeError
from eidolon.store import Message


class FakeLLM:
    """Records every prompt it receives and replies from a script.

    Each scripted reply is a list of text chunks, streamed in order, so tests can
    split the structured reply at awkward boundaries. With a `delay`, it waits that
    many seconds before each chunk after the first, as a slow model would.
    """

    def __init__(self, *replies: Sequence[str], delay: float = 0) -> None:
        self._replies = [list(r) for r in replies]
        self._delay = delay
        self.prompts: list[list[ChatMessage]] = []

    async def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        self.prompts.append(list(messages))
        if not self._replies:
            raise AssertionError("FakeLLM ran out of scripted replies")
        for i, chunk in enumerate(self._replies.pop(0)):
            if i and self._delay:
                await asyncio.sleep(self._delay)
            yield chunk

    async def aclose(self) -> None:
        pass


class FakeCalls:
    """Stands in for the voice pipeline: records each call the backend starts."""

    def __init__(self) -> None:
        self.started: list[Call] = []
        self._connections: list[SmallWebRTCConnection] = []

    async def __call__(self, connection: SmallWebRTCConnection, call: Call) -> None:
        self._connections.append(connection)
        self.started.append(call)

    async def hang_up_all(self) -> None:
        for connection in self._connections:
            await connection.disconnect()


class FakeEmbedder:
    """Embeds text as counts of a few keywords, so the nearest passages are the ones
    sharing the query's keywords. Records every text and query it embeds; set `down` to
    have it fail as an unreachable service would."""

    KEYWORDS = ("鳩", "公園", "優勝", "長崎", "ちゃんぽん", "写真", "負け")

    def __init__(self, model: str = "fake-embedding") -> None:
        self.model = model
        self.documents: list[str] = []
        self.queries: list[str] = []
        self.down = False

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if self.down:
            raise EmbeddingError("fake embedding service is down")
        self.documents.extend(texts)
        return [self._vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        if self.down:
            raise EmbeddingError("fake embedding service is down")
        self.queries.append(text)
        return self._vector(text)

    def _vector(self, text: str) -> list[float]:
        return [0.01] + [float(text.count(k)) for k in self.KEYWORDS]


class FakeJudge:
    """Stands in for Jev: answers every turn the same way, or fails if `answer` is None.
    Records what it was asked."""

    def __init__(self, answer: bool | None = True) -> None:
        self.answer = answer
        self.asked: list[tuple[str, str]] = []  # (character id, text)

    async def needs_retrieval(
        self, character: Character, history: Sequence[Message], text: str
    ) -> bool:
        self.asked.append((character.id, text))
        if self.answer is None:
            raise JudgeError("fake Jev is down")
        return self.answer


class FakeReranker:
    """Ranks documents containing `prefer` first, otherwise keeping the order it was given.
    Records every call."""

    def __init__(self, prefer: str = "") -> None:
        self.prefer = prefer
        self.calls: list[tuple[str, list[str]]] = []

    async def rerank(self, query: str, documents: Sequence[str], top_n: int) -> list[int]:
        self.calls.append((query, list(documents)))
        order = sorted(range(len(documents)), key=lambda i: self.prefer not in documents[i])
        return order[:top_n]
