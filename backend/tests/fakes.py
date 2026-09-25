"""Test doubles for external services."""

import asyncio
from collections.abc import AsyncIterator, Sequence

from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection

from eidolon.call import Call
from eidolon.characters import Character
from eidolon.embedding import EmbeddingError
from eidolon.llm import ChatMessage, Tool, ToolCall
from eidolon.retrieval import JudgeError, Need
from eidolon.store import Message


class FakeLLM:
    """Records every prompt it receives, and the tools offered with it, and replies from a
    script.

    Each scripted reply is a list of text chunks and tool calls, streamed in order, so
    tests can split the structured reply at awkward boundaries or have the model call a
    tool. With a `delay`, it waits that many seconds before each chunk after the first,
    as a slow model would.
    """

    def __init__(self, *replies: Sequence[str | ToolCall], delay: float = 0) -> None:
        self._replies = [list(r) for r in replies]
        self._delay = delay
        self.prompts: list[list[ChatMessage]] = []
        self.tools: list[list[Tool]] = []

    async def stream(
        self, messages: Sequence[ChatMessage], tools: Sequence[Tool] = ()
    ) -> AsyncIterator[str | ToolCall]:
        self.prompts.append(list(messages))
        self.tools.append(list(tools))
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

    def __init__(self, answer: Need | None = "references") -> None:
        self.answer: Need | None = answer
        self.asked: list[tuple[str, str]] = []  # (character id, text)

    async def judge(self, character: Character, history: Sequence[Message], text: str) -> Need:
        self.asked.append((character.id, text))
        if self.answer is None:
            raise JudgeError("fake Jev is down")
        return self.answer


class FakeReranker:
    """Ranks documents containing `prefer` first (scoring them 0.9), otherwise keeping the
    order it was given (scoring the rest `others`). Records every call."""

    def __init__(self, prefer: str = "", others: float = 0.5) -> None:
        self.prefer = prefer
        self.others = others
        self.calls: list[tuple[str, list[str]]] = []

    async def rerank(
        self, query: str, documents: Sequence[str], top_n: int
    ) -> list[tuple[int, float]]:
        self.calls.append((query, list(documents)))
        order = sorted(range(len(documents)), key=lambda i: self.prefer not in documents[i])
        return [(i, 0.9 if self.prefer in documents[i] else self.others) for i in order[:top_n]]
