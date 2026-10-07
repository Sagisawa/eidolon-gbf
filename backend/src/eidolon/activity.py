"""Activity records (GLOSSARY.md「运行记录」): one for each text turn (and, in time, each
call), saying how it turned out, and one for each call to an outside service, saying which
service, whose key, whether it failed and how, how long it took and what it was billed
for. They hold nothing anyone said. Only the admin's dashboard reads them (`dashboard`).

A turn's record is open while the turn runs (`ActivityLog.begin`, then `current`), and the
service calls made meanwhile, in the turn's context, are recorded under it; its outcome
is told it as the turn's use of the limit is (`turn_outcome`), and it is written once it
has one. A service call made outside any turn, as writing down memories after one is
(`detached`), is recorded on its own.

The services are timed by thin wrappers around their clients (`metered_llm`,
`MeteredJudge`, `MeteredEmbedder`, `MeteredReranker`), which also open a `Billing` for
the client to tell what the request is billed for. A call abandoned part-way, as when the
user leaves, is not a failure.

Records are kept for 90 days (`KEPT`); older ones are deleted whenever a turn begins, as
uses of the limit are. A deleted user's records stay, for the numbers not to change, but
no longer say whose they were (`database.ANONYMIZED_USER_DATA`).
"""

import asyncio
import logging
import re
import sqlite3
import threading
from collections.abc import AsyncIterator, Awaitable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import Context, ContextVar, copy_context
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Any, Literal, TypeVar
from urllib.parse import urlsplit

import httpx

from eidolon.billing import Billing, billing
from eidolon.characters import Character
from eidolon.clock import Clock
from eidolon.config import CloudflareJudgeSettings, JudgeSettings, LLMSettings, Settings
from eidolon.database import connect
from eidolon.embedding import Document, Embedder
from eidolon.judge import CLOUDFLARE_API_URL
from eidolon.llm import ChatLLM, ChatMessage, Tool, ToolCall, TurnLLMs
from eidolon.rerank import Reranker
if TYPE_CHECKING:  # retrieval finds memories, which write down detached from turns
    from eidolon.retrieval import Need, RetrievalJudge
from eidolon.store import Message

log = logging.getLogger(__name__)

ServiceName = Literal[
    "chat_llm", "memory_llm", "tts", "stt", "judge", "embedding", "rerank"
]
"""The outside services: the LLM playing the characters and the one writing down memories,
speech synthesis and recognition, the judge model, embedding and reranking."""
SERVICES: tuple[ServiceName, ...] = (
    "chat_llm", "memory_llm", "tts", "stt", "judge", "embedding", "rerank"
)

RecordKind = Literal["turn", "call"]
Result = Literal["success", "failed", "rejected", "left", "not_connected"]
"""How a turn or call turned out (GLOSSARY.md「回合」「接通」): a turn succeeded, failed on
a service, was rejected (over the limit, or its input), or the user left before it was
done; a call also may never have connected."""
RESULTS: tuple[Result, ...] = ("success", "failed", "rejected", "left", "not_connected")

ErrorKind = Literal[
    "timeout", "connection", "rate_limited", "unauthorized", "refused", "server_error",
    "unreadable", "other",
]
"""What kind of failure a service call was, never what the service said: that may quote
what it was sent."""

KEPT = timedelta(days=90)
"""How long activity records are kept."""

_SCHEMA = """
-- Times are epoch seconds, so that a range is a plain range query. A record's user is
-- NULL once the user is deleted, and `anonymous_id` then tells their records apart from
-- other users' without saying whose they were. `call_id`, `duration_s` and `end_reason`
-- are for calls and the turns in them.
CREATE TABLE IF NOT EXISTS activity_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    user_id TEXT REFERENCES users(id),
    anonymous_id TEXT,
    character_id TEXT NOT NULL,
    started_at REAL NOT NULL,
    result TEXT NOT NULL,
    own_keys INTEGER NOT NULL DEFAULT 0,
    time_to_speak_ms REAL,
    call_id INTEGER,
    duration_s REAL,
    end_reason TEXT
);
CREATE INDEX IF NOT EXISTS activity_records_by_time ON activity_records(started_at);
CREATE INDEX IF NOT EXISTS activity_records_by_user ON activity_records(user_id, started_at);
-- Each call to an outside service; `record_id` is the turn or call it was made in, NULL
-- for one made outside any. `error` is NULL when it succeeded; the usage columns are NULL
-- when the service did not say.
CREATE TABLE IF NOT EXISTS service_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER,
    at REAL NOT NULL,
    service TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    own_key INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    latency_ms REAL NOT NULL,
    usage_unit TEXT,
    usage_input REAL,
    usage_output REAL
);
CREATE INDEX IF NOT EXISTS service_calls_by_time ON service_calls(at);
CREATE INDEX IF NOT EXISTS service_calls_by_record ON service_calls(record_id);
"""


@dataclass(frozen=True)
class Origin:
    """Which service a call is to: the host it is at (`provider`), the model, and whether
    on the user's own key."""

    service: ServiceName
    provider: str
    model: str
    own_key: bool = False


def host(url: str | None) -> str:
    """The provider a service at `url` is: its host."""
    return (urlsplit(url).hostname or "unknown") if url else "unknown"


def llm_origin(service: ServiceName, settings: LLMSettings, own_key: bool = False) -> Origin:
    return Origin(service, host(settings.base_url), settings.model, own_key)


@dataclass(frozen=True)
class ServiceCall:
    origin: Origin
    at: datetime
    error: ErrorKind | None
    latency_ms: float
    billed: Billing


@dataclass(frozen=True)
class RecordRow:
    """An activity record as the dashboard reads it: whose (any stable id; the same for
    one user's records, deleted or not), which character, when, how it turned out."""

    kind: RecordKind
    who: str | None
    character_id: str
    started_at: datetime
    result: Result
    own_keys: bool
    time_to_speak_ms: float | None


@dataclass(frozen=True)
class CallRow:
    """A service call as the dashboard reads it."""

    service: ServiceName
    provider: str
    model: str
    own_key: bool
    at: datetime
    error: ErrorKind | None
    latency_ms: float
    usage_unit: str | None
    usage_input: float | None
    usage_output: float | None


_current: ContextVar["Recording | None"] = ContextVar("activity_record", default=None)


def detached() -> Context:
    """A context for work started in a turn that is not part of it, as writing down
    memories: its service calls are recorded on their own."""
    context = copy_context()
    context.run(_current.set, None)
    return context


class Recording:
    """One turn's activity record while the turn runs: the service calls made in it, and
    when the character began to speak (GLOSSARY.md「开口」). Written once finished."""

    def __init__(
        self,
        log: "ActivityLog",
        kind: RecordKind,
        user_id: str,
        character_id: str,
        started_at: datetime,
        own_keys: bool,
    ) -> None:
        self._log = log
        self.kind: RecordKind = kind
        self.user_id = user_id
        self.character_id = character_id
        self.started_at = started_at
        self.own_keys = own_keys
        self.time_to_speak_ms: float | None = None
        self.calls: list[ServiceCall] = []
        self.finished = False
        self._started = perf_counter()

    @contextmanager
    def current(self) -> Iterator[None]:
        """Record the service calls made meanwhile, in this context, under this record."""
        previous = _current.get()
        _current.set(self)
        try:
            yield
        finally:
            _current.set(previous)

    def spoke(self) -> None:
        """The character began to speak (only the first time counts)."""
        if self.time_to_speak_ms is None:
            self.time_to_speak_ms = (perf_counter() - self._started) * 1000

    def finish(self, result: Result) -> None:
        """Write the record, as `result`, with its service calls; only the first time."""
        if self.finished:
            return
        self.finished = True
        self._log._write(self, result)


class ActivityLog:
    """Every turn's activity record and every service call's, kept in the database."""

    def __init__(self, path: Path, clock: Clock) -> None:
        self._db = connect(path)
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.executescript(_SCHEMA)
        self._clock = clock

    def begin(
        self, kind: RecordKind, user_id: str, character_id: str, own_keys: bool
    ) -> Recording:
        """Open the record of a turn the user begins with `character_id`, on their own
        keys alone or not; forgets every record older than `KEPT`."""
        now = self._clock()
        self._forget_before(now - KEPT)
        return Recording(self, kind, user_id, character_id, now, own_keys)

    def call(self, origin: Origin, started: float, error: ErrorKind | None, billed: Billing) -> None:
        """A service call, begun at `started` (`perf_counter`), has ended: recorded under
        the turn it was made in, if it is still open, or on its own."""
        call = ServiceCall(
            origin, self._clock(), error, (perf_counter() - started) * 1000, billed
        )
        recording = _current.get()
        if recording is not None and not recording.finished:
            recording.calls.append(call)
        else:
            with self._lock, self._db:
                self._insert_call(call, None)

    def since(self, moment: datetime) -> tuple[list[RecordRow], list[CallRow]]:
        """Every record and service call after `moment`, oldest first."""
        at = moment.timestamp()
        with self._lock:
            records = self._db.execute(
                "SELECT kind, COALESCE(user_id, anonymous_id), character_id, started_at, result,"
                " own_keys, time_to_speak_ms FROM activity_records WHERE started_at > ?"
                " ORDER BY started_at",
                (at,),
            ).fetchall()
            calls = self._db.execute(
                "SELECT service, provider, model, own_key, at, error, latency_ms, usage_unit,"
                " usage_input, usage_output FROM service_calls WHERE at > ? ORDER BY at",
                (at,),
            ).fetchall()
        return (
            [
                RecordRow(kind, who, character, _time(started), result, bool(own), speak)
                for kind, who, character, started, result, own, speak in records
            ],
            [
                CallRow(service, provider, model, bool(own), _time(at), error, latency,
                        unit, used_in, used_out)
                for service, provider, model, own, at, error, latency, unit, used_in, used_out
                in calls
            ],
        )

    def close(self) -> None:
        self._db.close()

    def _write(self, recording: Recording, result: Result) -> None:
        row = (
            recording.kind, recording.character_id, recording.started_at.timestamp(), result,
            int(recording.own_keys), recording.time_to_speak_ms,
        )
        with self._lock, self._db:
            try:
                cursor = self._db.execute(
                    "INSERT INTO activity_records (user_id, kind, character_id, started_at,"
                    " result, own_keys, time_to_speak_ms) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (recording.user_id, *row),
                )
            except sqlite3.IntegrityError:  # the user was deleted meanwhile
                cursor = self._db.execute(
                    "INSERT INTO activity_records (user_id, kind, character_id, started_at,"
                    " result, own_keys, time_to_speak_ms) VALUES (NULL, ?, ?, ?, ?, ?, ?)",
                    row,
                )
            for call in recording.calls:
                self._insert_call(call, cursor.lastrowid)

    def _insert_call(self, call: ServiceCall, record_id: int | None) -> None:
        origin, billed = call.origin, call.billed
        self._db.execute(
            "INSERT INTO service_calls (record_id, at, service, provider, model, own_key,"
            " error, latency_ms, usage_unit, usage_input, usage_output)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record_id, call.at.timestamp(), origin.service, origin.provider, origin.model,
                int(origin.own_key), call.error, call.latency_ms, billed.unit, billed.input,
                billed.output,
            ),
        )

    def _forget_before(self, moment: datetime) -> None:
        at = moment.timestamp()
        with self._lock, self._db:
            self._db.execute("DELETE FROM service_calls WHERE at <= ?", (at,))
            self._db.execute("DELETE FROM activity_records WHERE started_at <= ?", (at,))


def _time(epoch: float) -> datetime:
    return datetime.fromtimestamp(epoch, UTC)


def error_kind(error: BaseException) -> ErrorKind:
    """What kind of failure `error`, or what it was raised from, is."""
    seen: set[int] = set()
    cause: BaseException | None = error
    statuses: list[int] = []
    while cause is not None and id(cause) not in seen:
        seen.add(id(cause))
        if isinstance(cause, httpx.TimeoutException | TimeoutError):
            return "timeout"
        if isinstance(cause, httpx.TransportError):
            return "connection"
        statuses += _statuses(str(cause))
        cause = cause.__cause__ or cause.__context__
    for status in statuses:
        if status == 429:
            return "rate_limited"
        if status in (401, 402, 403):
            return "unauthorized"
        if 400 <= status < 500:
            return "refused"
        if status >= 500:
            return "server_error"
    if "无法解析" in str(error):
        return "unreadable"
    return "other"


def _statuses(message: str) -> list[int]:
    """The HTTP statuses a service's error message names: "返回 503", or "402 Payment
    Required" at its start."""
    found = [int(s) for s in re.findall(r"返回 (\d{3})\b", message)]
    if (lead := re.search(r"(?:^|：)(\d{3}) [A-Z]", message)) is not None:
        found.append(int(lead.group(1)))
    return found


T = TypeVar("T")


async def timed(log: ActivityLog, origin: Origin, work: Awaitable[T]) -> T:
    """What `work`, a request to the service `origin` names, comes to, recorded as a
    service call."""
    started = perf_counter()
    billed = Billing()
    error: ErrorKind | None = None
    try:
        with billing(billed):
            return await work
    except asyncio.CancelledError:
        raise  # abandoned, not failed
    except Exception as e:
        error = error_kind(e)
        raise
    finally:
        log.call(origin, started, error, billed)


class _MeteredLLM:
    """An LLM whose every request is recorded as a service call."""

    def __init__(self, llm: ChatLLM, log: ActivityLog, origin: Origin) -> None:
        self._llm = llm
        self._log = log
        self._origin = origin

    async def stream(
        self, messages: Sequence[ChatMessage], tools: Sequence[Tool] = ()
    ) -> AsyncIterator[str | ToolCall]:
        started = perf_counter()
        billed = Billing()
        error: ErrorKind | None = None
        stream = aiter(self._llm.stream(messages, tools))
        try:
            while True:
                # Opened and closed around each step alone: a step may be taken in a task
                # of its own (see `engine._unless_stopped`).
                with billing(billed):
                    try:
                        item = await anext(stream)
                    except StopAsyncIteration:
                        break
                yield item
        except (GeneratorExit, asyncio.CancelledError):
            raise  # abandoned, not failed
        except Exception as e:
            error = error_kind(e)
            raise
        finally:
            if (close := getattr(stream, "aclose", None)) is not None:
                await close()
            self._log.call(self._origin, started, error, billed)

    async def aclose(self) -> None:
        pass  # whoever opened the model closes it


def metered_llm(llm: ChatLLM, log: ActivityLog, origin: Origin) -> ChatLLM:
    return _MeteredLLM(llm, log, origin)


def turn_llms(
    log: ActivityLog,
    llms: TurnLLMs,
    own: dict[str, Any] | None,
    chat: LLMSettings,
    memory: LLMSettings,
) -> TurnLLMs:
    """A turn's models, each request recorded as a service call: the user's `own` LLM (as
    `OwnKeys.describe` shows it) both, if they brought one; else the deployer's `chat` and
    `memory` models."""
    if own is not None:
        origin = Origin("chat_llm", host(own.get("base_url")), own.get("model") or "", True)
        return TurnLLMs(
            metered_llm(llms.chat, log, origin),
            metered_llm(llms.memory, log, Origin("memory_llm", origin.provider, origin.model, True)),
            llms.hold_memory,
        )
    return TurnLLMs(
        metered_llm(llms.chat, log, llm_origin("chat_llm", chat)),
        metered_llm(llms.memory, log, llm_origin("memory_llm", memory)),
        llms.hold_memory,
    )


def metered_retrieval(
    log: ActivityLog,
    settings: Settings,
    judge: "RetrievalJudge | None",
    embedder: Embedder | None,
    reranker: Reranker | None,
) -> "tuple[RetrievalJudge | None, Embedder | None, Reranker | None]":
    """The judge model, the embedder and the reranker turns retrieve with, whichever are
    at hand, each request recorded as a service call to the service `settings` name."""
    if judge is not None:
        judge = MeteredJudge(judge, log, judge_origin(settings.judge))
    if embedder is not None:
        e = settings.embedding
        origin = Origin("embedding", host(e and e.base_url), embedder.model)
        embedder = MeteredEmbedder(embedder, log, origin)
    if reranker is not None:
        r = settings.rerank
        reranker = MeteredReranker(
            reranker, log, Origin("rerank", host(r and r.base_url), r.model if r else "unknown")
        )
    return judge, embedder, reranker


def judge_origin(settings: JudgeSettings | None) -> Origin:
    """The judge model `settings` choose, as its service calls are recorded."""
    if isinstance(settings, CloudflareJudgeSettings):
        return Origin("judge", host(CLOUDFLARE_API_URL), settings.model)
    return Origin(
        "judge", host(settings and settings.base_url), settings.model if settings else "unknown"
    )


class MeteredJudge:
    """The judge model as retrieval asks it, each question recorded as a service call."""

    def __init__(self, judge: "RetrievalJudge", log: ActivityLog, origin: Origin) -> None:
        self._judge = judge
        self._log = log
        self._origin = origin

    async def judge(self, character: Character, history: Sequence[Message], text: str) -> "Need":
        return await timed(self._log, self._origin, self._judge.judge(character, history, text))


class MeteredEmbedder:
    """An embedder whose every request is recorded as a service call."""

    def __init__(self, embedder: Embedder, log: ActivityLog, origin: Origin) -> None:
        self.model = embedder.model
        self._embedder = embedder
        self._log = log
        self._origin = origin

    async def embed_documents(self, documents: Sequence[Document]) -> list[list[float]]:
        return await timed(self._log, self._origin, self._embedder.embed_documents(documents))

    async def embed_query(self, text: str) -> list[float]:
        return await timed(self._log, self._origin, self._embedder.embed_query(text))


class MeteredReranker:
    """A reranker whose every request is recorded as a service call."""

    def __init__(self, reranker: Reranker, log: ActivityLog, origin: Origin) -> None:
        self._reranker = reranker
        self._log = log
        self._origin = origin

    async def rerank(
        self, query: str, documents: Sequence[str], top_n: int
    ) -> list[tuple[int, float]]:
        return await timed(
            self._log, self._origin, self._reranker.rerank(query, documents, top_n)
        )
