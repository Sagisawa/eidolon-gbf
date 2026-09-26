"""Test doubles for external services."""

import asyncio
import hashlib
import json
from collections.abc import AsyncGenerator, AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta

import httpx
from pipecat.frames.frames import (
    Frame,
    ProposedUserStartedSpeakingFrame,
    ProposedUserStoppedSpeakingFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
)
from pipecat.services.settings import STTSettings, TTSSettings
from pipecat.services.stt_service import STTService
from pipecat.services.tts_service import TTSService
from pipecat.utils.time import time_now_iso8601

from eidolon.characters import Character
from eidolon.embedding import Document, EmbeddingError
from eidolon.llm import ChatMessage, Tool, ToolCall
from eidolon.mirror import Mirror
from eidolon.retrieval import JudgeError, Need
from eidolon.store import Message

START = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


class FakeClock:
    """A clock the tests move forward themselves."""

    def __init__(self, now: datetime = START) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


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


class FakeBackgroundLLM:
    """Stands in for the background model: answers each request with the next scripted
    reply, and with no memories once the script runs out; a reply that is an exception
    is raised instead. Records every prompt it receives. With a `gate`, it answers only
    once the gate is open, like a slow model."""

    NOTHING = '{"memories": []}'

    def __init__(self, *replies: str | Exception, gate: asyncio.Event | None = None) -> None:
        self._replies = list(replies)
        self._gate = gate
        self.prompts: list[list[ChatMessage]] = []

    async def stream(
        self, messages: Sequence[ChatMessage], tools: Sequence[Tool] = ()
    ) -> AsyncIterator[str | ToolCall]:
        self.prompts.append(list(messages))
        reply = self._replies.pop(0) if self._replies else self.NOTHING
        if self._gate is not None:
            await self._gate.wait()
        if isinstance(reply, Exception):
            raise reply
        for i in range(0, len(reply), 7):  # in chunks, as a streaming model would
            yield reply[i : i + 7]

    async def aclose(self) -> None:
        pass


class FakeSTT(STTService):
    """Stands in for Soniox in one call: ignores the microphone and hears what the test
    says the user said, the way Soniox reports an utterance."""

    def __init__(self) -> None:
        super().__init__(ttfs_p99_latency=0.1, settings=STTSettings(model=None, language=None))

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None, None]:
        yield None

    async def hear(self, text: str) -> None:
        """The user said `text`: an utterance starts, is transcribed, and ends."""
        await self.broadcast_frame(ProposedUserStartedSpeakingFrame)
        await self.push_frame(TranscriptionFrame(text, "user", time_now_iso8601(), finalized=True))
        await self.broadcast_frame(ProposedUserStoppedSpeakingFrame)

    async def break_down(self) -> None:
        """Fail as a rejected API key would: for good."""
        await self.push_error("fake speech recognition is down", force_treat_as_permanent=True)


class FakeTTS(TTSService):
    """Stands in for Fish Audio in one call: records what it is asked to voice, and in which
    voice, and says a moment of silence for each."""

    def __init__(self, voice_id: str, sample_rate: int) -> None:
        super().__init__(
            sample_rate=sample_rate, settings=TTSSettings(model=None, voice=None, language=None)
        )
        self.voice_id = voice_id
        self.voiced: list[str] = []

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        self.voiced.append(text)
        samples = self.sample_rate // 10
        yield TTSAudioRawFrame(b"\0\0" * samples, self.sample_rate, 1, context_id=context_id)


class FakeSpeech:
    """Stands in for Soniox and Fish Audio: the speech services of each call started, in
    order. Set `down` to have the services fail to be made at all."""

    def __init__(self) -> None:
        self.stts: list[FakeSTT] = []
        self.ttss: list[FakeTTS] = []
        self.down = False

    def stt(self) -> FakeSTT:
        if self.down:
            raise RuntimeError("fake speech services are down")
        self.stts.append(FakeSTT())
        return self.stts[-1]

    def tts(self, voice_id: str, sample_rate: int) -> FakeTTS:
        self.ttss.append(FakeTTS(voice_id, sample_rate))
        return self.ttss[-1]


class FakeEmbedder:
    """Embeds text as counts of a few keywords, so the nearest passages are the ones
    sharing the query's keywords. Records every document (its text, and its title in
    `titles`) and query it embeds; set `down` to have it fail as an unreachable service
    would."""

    KEYWORDS = ("鳩", "公園", "優勝", "長崎", "ちゃんぽん", "写真", "負け", "猫", "北海道")

    def __init__(self, model: str = "fake-embedding") -> None:
        self.model = model
        self.documents: list[str] = []
        self.titles: list[str | None] = []
        self.queries: list[str] = []
        self.down = False

    async def embed_documents(self, documents: Sequence[Document]) -> list[list[float]]:
        if self.down:
            raise EmbeddingError("fake embedding service is down")
        self.documents.extend(d.text for d in documents)
        self.titles.extend(d.title for d in documents)
        return [self._vector(d.text) for d in documents]

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


class FakeShinyColorsDB:
    """Stands in for the ShinyColorsDB API, the viewer that mirrors the game's scripts and
    the idols' albums, answering as they do: idols and their cards, each card's episodes,
    albums, and scripts; scripts and albums with an ETag, 304 to a request for a copy that
    is still current and 404 for one it does not have. Records every request, and which
    scripts (and albums, as `album/NN`) it sent in full. Set `down`
    to have it unreachable, or `down_after` to have it go down after that many requests."""

    def __init__(self) -> None:
        self.idols: dict[int, list[dict]] = {}
        self.events: dict[str, list[dict]] = {}
        self.scripts: dict[str, bytes] = {}
        self.albums: dict[int, dict] = {}
        self.requests: list[httpx.Request] = []
        self.sent: list[str] = []
        self.down = False
        self.down_after: int | None = None

    def add_card(
        self, idol: int, uuid: str, name: str, type: str, episodes: Sequence[tuple[int, str]] = ()
    ) -> None:
        self.idols.setdefault(idol, []).append(
            {"cardUuid": uuid, "cardName": name, "cardType": type, "cardHash": "v1", "lastModified": "2026-09-01"}
        )
        title = "eventTitle" if type.startswith("P_") else "eventName"
        self.events[uuid] = [{"eventId": event_id, title: t} for event_id, t in episodes]

    def update_card(self, uuid: str) -> None:
        """The card's data changes, as when the game revises it."""
        for card in (c for cards in self.idols.values() for c in cards if c["cardUuid"] == uuid):
            card["cardHash"] += "+"

    def add_album(
        self, idol: int, sections: dict[str, str], entries: Sequence[tuple[str, str, str, str]]
    ) -> None:
        """The idol's album: its sections (album type → title), and its entries, each
        `(category, communication id, title, album type)`."""
        self.albums[idol] = {
            "id": str(idol),
            "albumCommunicationTitles": [
                {"albumType": album_type, "id": str(1000 + n), "title": title}
                for n, (album_type, title) in enumerate(sections.items(), 1)
            ],
            "communications": [
                {"albumType": album_type, "communicationCategory": category,
                 "communicationId": number, "title": title, "isReleased": True}
                for category, number, title, album_type in entries
            ],
        }

    def add_script(self, script: str, frames: object) -> None:
        self.scripts[script] = json.dumps(frames, ensure_ascii=False).encode()

    def mirror(self) -> Mirror:
        return Mirror(httpx.AsyncClient(transport=httpx.MockTransport(self._handle)), interval=0)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.down or (self.down_after is not None and len(self.requests) > self.down_after):
            raise httpx.ConnectError("connection refused")
        path, params = request.url.path, request.url.params
        if request.url.host == "api.shinycolors.moe":
            if path == "/info/idolList":
                return httpx.Response(200, json=[{"idolId": i} for i in self.idols])
            if path == "/info/idolInfo":
                return httpx.Response(200, json={"cardLists": self.idols.get(int(params["idolId"]), [])})
            if path in ("/info/pCardInfo", "/info/sCardInfo"):
                key = "cardIdolEvents" if path == "/info/pCardInfo" else "cardSupportEvents"
                return httpx.Response(200, json={key: self.events[params["cardId"]]})
            return httpx.Response(404)
        if request.url.host == "cf-static.shinycolors.moe":
            idol = int(path.removeprefix("/albums/album/").removesuffix(".json"))
            album = self.albums.get(idol)
            body = None if album is None else json.dumps(album, ensure_ascii=False).encode()
            return self._send(request, f"album/{idol:02d}", body)
        script = path.removeprefix("/json/").removesuffix(".json")
        return self._send(request, script, self.scripts.get(script))

    def _send(self, request: httpx.Request, name: str, body: bytes | None) -> httpx.Response:
        if body is None:
            return httpx.Response(404, text="<html>Not Found</html>")
        etag = f'"{hashlib.md5(body).hexdigest()}"'
        if request.headers.get("If-None-Match") == etag:
            return httpx.Response(304)
        self.sent.append(name)
        return httpx.Response(200, content=body, headers={"ETag": etag})
