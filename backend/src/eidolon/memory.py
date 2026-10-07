"""Memory: what users tell the characters, kept across conversations.

After each turn the background model reads the exchange and writes down, in Chinese,
whatever the user revealed about themselves that is worth keeping. Each memory belongs
to the user and names the character it was told to, its source character. All of a
user's characters share their memories, and a character finding one told to someone
else is asked to pass it on as hearsay (ADR-0002); users never share theirs.

A turn goes `begin` → `find` → `write_down`. Writing runs in the background so it never
holds up the reply; the user's next turn begins by waiting briefly for it, so what they
just said is remembered by the time they go on. A new conversation picks up where
earlier ones left off only through the memories it finds.

Users can list their memories and delete them one by one or all at once, never add or
edit them. Listing and deleting wait briefly for what is being written down too;
whatever turns begun before a clearing write down after it is dropped, so a cleared
memory never turns up again.

Each memory is embedded as it is written down, and the vector kept until the memory is
gone; a memory whose embedding failed is embedded the next time its user's memories are
searched. After the embedding model changes, `eidolon reembed` embeds them all again.

Each turn writes down with the model it began with (see `OwnKeys.for_turn`). Without an
embedder and reranker, memory is off: turns find and write down nothing, but users can
still list and delete the memories already kept.
"""

import asyncio
import json
import logging
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from eidolon.activity import detached
from eidolon.characters import Character
from eidolon.clock import Clock
from eidolon.corpus import REEMBED_BATCH
from eidolon.database import connect
from eidolon.embedding import Document, Embedder, EmbeddingError, nearest, to_blob
from eidolon.llm import ChatLLM, ChatMessage
from eidolon.rerank import DEFAULT_THRESHOLDS, Reranker, RerankError
from eidolon.store import Conversation, Message

log = logging.getLogger(__name__)

SETTLE_TIMEOUT = 5.0
"""How long, in seconds, a turn waits for the memories of the user's previous turn to be
written before going on without them."""
KNOWN_MEMORIES = 50
"""How many of the user's latest memories the background model is shown, so it does not
write them down again."""
EXCHANGE_HISTORY = 4
"""How many of the messages before the user's latest the background model reads with it."""
MAX_NEW_MEMORIES = 5
"""The most memories one turn writes down."""
MAX_MEMORY_LENGTH = 200
"""How much of a memory, in characters, is kept; longer ones are cut short."""
CANDIDATES = 12
"""How many of the user's memories nearest the turn the reranker is offered."""
MAX_FOUND = 3
"""The most memories one turn's prompt carries, after reranking."""
ANOTHER_IDOL = "事务所的另一位偶像"
"""Who a memory was told to, when that character has been removed from the configuration."""

# `memories` predates this module and keeps the columns and constraints it had in the
# store; `memory_vectors` holds each memory's embedding, per embedding model.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(id),
    source_character_id TEXT NOT NULL,
    conversation_id TEXT REFERENCES conversations(id),
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (user_id, text)
);
CREATE TABLE IF NOT EXISTS memory_vectors (
    memory_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    model TEXT NOT NULL,
    embedding BLOB NOT NULL,
    PRIMARY KEY (memory_id, model)
);
CREATE INDEX IF NOT EXISTS memory_vectors_by_user ON memory_vectors(user_id, model);
"""


@dataclass(frozen=True)
class Memory:
    """Something about a user worth keeping across conversations, written in Chinese,
    with the character it was told to (its source character)."""

    id: int
    user_id: str
    source_character_id: str
    source_character_name: str | None
    """None if that character has been removed from the configuration."""
    text: str
    created_at: str
    """When it was told, as an ISO timestamp in UTC."""


@dataclass(frozen=True)
class _Services:
    """What memory needs to be on."""

    embedder: Embedder
    reranker: Reranker
    min_relevance: float


class Memories:
    """Every user's memories."""

    label = "记忆"
    unit = "条"

    def __init__(
        self,
        path: Path,
        characters: Mapping[str, Character],
        clock: Clock,
        *,
        embedder: Embedder | None = None,
        reranker: Reranker | None = None,
        min_relevance: float = DEFAULT_THRESHOLDS.memories,
    ) -> None:
        """Memories kept in the database at `path`, next to the users and conversations
        they belong to; off unless `embedder` and `reranker` are both given, though
        `embedder` alone is enough to embed them again. A memory the reranker scores below
        `min_relevance` is not found (see `rerank.KNOWN_THRESHOLDS`)."""
        self._db = connect(path)
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.executescript(_SCHEMA)
        self._characters = characters
        self._clock = clock
        self._embedder = embedder
        self._services = (
            _Services(embedder, reranker, min_relevance)
            if embedder is not None and reranker is not None
            else None
        )
        self._pending: dict[str, set[asyncio.Task[None]]] = {}  # user id → writing
        self._clearings: dict[str, int] = {}  # user id → how many times cleared

    async def begin(
        self,
        conversation: Conversation,
        timezone: str,
        llm: ChatLLM,
    ) -> "MemoryTurn":
        """Begin a turn of `conversation`, whose user is in `timezone`, once what their
        earlier turns are writing down is written (a while at most). The turn writes down
        with `llm`."""
        clearings = self._clearings.get(conversation.user_id, 0)
        await self._settle(conversation.user_id)
        return MemoryTurn(self, conversation, timezone, clearings, llm)

    async def entries(self, user_id: str) -> list[Memory]:
        """All of the user's memories, newest first, including what their turns so far
        are writing down (unless that takes too long). Not named `list`, which would
        shadow the builtin in this class's annotations."""
        await self._settle(user_id)
        return list(reversed(await asyncio.to_thread(self._all, user_id)))

    async def delete(self, user_id: str, memory_id: int) -> bool:
        """Forget one of the user's memories; False if they have no such memory."""
        await self._settle(user_id)
        return await asyncio.to_thread(self._delete, user_id, memory_id)

    async def clear(self, user_id: str) -> None:
        """Forget all of the user's memories, including those their turns so far are still
        writing down."""
        self._clearings[user_id] = self._clearings.get(user_id, 0) + 1
        await self._settle(user_id)
        await asyncio.to_thread(self._clear, user_id)

    async def forget(self, user_id: str) -> None:
        """Drop whatever the user's turns so far are still writing down, before the user
        is deleted (see `database.delete_user_data`, which deletes their memories)."""
        self._clearings[user_id] = self._clearings.get(user_id, 0) + 1
        await self._settle(user_id)

    async def embed_missing(
        self, batch: int = REEMBED_BATCH, progress: Callable[[int], None] | None = None
    ) -> int:
        """Embed every user's memories that have no vector from the embedder given, `batch`
        at a time; returns how many it embedded, telling `progress` the count so far after
        each batch. Interrupted, what it finished is kept; a memory deleted meanwhile gets
        no vector."""
        embedder = self._reembedder()
        model = embedder.model
        done = 0
        after = 0
        while True:
            with self._lock:
                rows = self._db.execute(
                    "SELECT id, user_id, text FROM memories m WHERE id > ? AND NOT EXISTS"
                    " (SELECT 1 FROM memory_vectors v WHERE v.memory_id = m.id AND v.model = ?)"
                    " ORDER BY id LIMIT ?",
                    (after, model, batch),
                ).fetchall()
            if not rows:
                return done
            vectors = await embedder.embed_documents([Document(text) for _, _, text in rows])
            with self._lock, self._db:
                self._db.executemany(
                    "INSERT OR REPLACE INTO memory_vectors (memory_id, user_id, model, embedding)"
                    " SELECT ?, ?, ?, ? WHERE EXISTS (SELECT 1 FROM memories WHERE id = ?)",
                    [
                        (id, user_id, model, to_blob(v), id)
                        for (id, user_id, _), v in zip(rows, vectors, strict=True)
                    ],
                )
            done += len(rows)
            after = rows[-1][0]
            if progress is not None:
                progress(done)

    def forget_other_models(self) -> int:
        """Drop every memory's vector not from the embedder given; returns how many there
        were."""
        model = self._reembedder().model
        with self._lock, self._db:
            return self._db.execute(
                "DELETE FROM memory_vectors WHERE model != ?", (model,)
            ).rowcount

    def _reembedder(self) -> Embedder:
        """The embedder given, which embedding the memories again needs."""
        if self._embedder is None:
            raise RuntimeError("embedding memories again needs the embedder they were opened with")
        return self._embedder

    async def aclose(self) -> None:
        """Let whatever is being written down finish, a while at most, then give up on it."""
        tasks = {t for pending in self._pending.values() for t in pending}
        if tasks:
            _, unfinished = await asyncio.wait(tasks, timeout=SETTLE_TIMEOUT)
            for task in unfinished:
                task.cancel()
            await asyncio.gather(*unfinished, return_exceptions=True)
        self._db.close()

    async def _settle(self, user_id: str) -> None:
        if pending := self._pending.get(user_id):
            await asyncio.wait(set(pending), timeout=SETTLE_TIMEOUT)

    async def _find(
        self, conversation: Conversation, timezone: str, text: str
    ) -> str | None:
        if (services := self._services) is None:
            return None
        user_id = conversation.user_id
        try:
            query = await services.embedder.embed_query(text)
            memories = await asyncio.to_thread(self._all, user_id)
            vectors = await self._vectors(services.embedder, user_id, memories)
            nearest_memories = [
                memories[i]
                for i, _ in nearest([vectors[m.id] for m in memories], query, CANDIDATES)
            ]
            best = (
                await services.reranker.rerank(
                    text, [m.text for m in nearest_memories], len(nearest_memories)
                )
                if nearest_memories
                else []
            )
        except (EmbeddingError, RerankError):
            log.warning("finding memories failed; replying without them", exc_info=True)
            return None
        found = [nearest_memories[i] for i, score in best if score >= services.min_relevance]
        character = self._characters[conversation.character_id]
        return _memories_prompt(found[:MAX_FOUND], character, timezone) if found else None

    def _write_down(
        self,
        conversation: Conversation,
        timezone: str,
        clearings: int,
        llm: ChatLLM,
        history: Sequence[Message],
        text: str,
        reply: Message,
    ) -> None:
        if (services := self._services) is None:
            return
        now = self._clock().astimezone(ZoneInfo(timezone))
        task = asyncio.create_task(
            self._write(services, llm, conversation, clearings, history, text, reply, now),
            context=detached(),  # after the turn, not part of it (see `activity`)
        )
        pending = self._pending.setdefault(conversation.user_id, set())
        pending.add(task)

        def done(task: asyncio.Task[None]) -> None:
            pending.discard(task)
            if not pending and self._pending.get(conversation.user_id) is pending:
                del self._pending[conversation.user_id]

        task.add_done_callback(done)

    async def _write(
        self,
        services: _Services,
        llm: ChatLLM,
        conversation: Conversation,
        clearings: int,
        history: Sequence[Message],
        text: str,
        reply: Message,
        now: datetime,
    ) -> None:
        user_id = conversation.user_id
        try:
            character = self._characters[conversation.character_id]
            known = await asyncio.to_thread(self._all, user_id)
            prompt = _extraction_prompt(character, history, text, reply, known, now)
            answer = "".join([
                chunk async for chunk in llm.stream(prompt)
                if isinstance(chunk, str)
            ])
            texts = parse_memories(answer)
            if texts is None:
                log.warning(  # its length only: the answer is about the user
                    "background model wrote no memories JSON (%d characters) in conversation %s",
                    len(answer), conversation.id,
                )
                return
            if self._clearings.get(user_id, 0) != clearings:
                return  # cleared since the turn began
            added = await asyncio.to_thread(self._add, conversation, texts, now)
        except Exception:
            log.warning("writing memories failed in conversation %s", conversation.id,
                        exc_info=True)
            return
        try:
            if added:
                await self._vectors(services.embedder, user_id, added, forget=False)
        except EmbeddingError:
            log.warning("embedding new memories failed; they are embedded when searched",
                        exc_info=True)

    def _all(self, user_id: str) -> list[Memory]:
        """Oldest first."""
        with self._lock:
            rows = self._db.execute(
                "SELECT id, user_id, source_character_id, text, created_at FROM memories"
                " WHERE user_id = ? ORDER BY id",
                (user_id,),
            ).fetchall()
        return [self._memory(*row) for row in rows]

    def _memory(
        self, id: int, user_id: str, source_character_id: str, text: str, created_at: str
    ) -> Memory:
        source = self._characters.get(source_character_id)
        return Memory(
            id, user_id, source_character_id, source.name if source else None, text,
            created_at,
        )

    def _add(self, conversation: Conversation, texts: list[str], now: datetime) -> list[Memory]:
        """Remember what the user told the conversation's character just `now`; returns the
        memories that are new, leaving out any the user already has."""
        added = []
        created_at = now.astimezone(UTC).isoformat()
        with self._lock, self._db:
            for text in texts:
                cursor = self._db.execute(
                    "INSERT OR IGNORE INTO memories"
                    " (user_id, source_character_id, conversation_id, text, created_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (conversation.user_id, conversation.character_id, conversation.id, text,
                     created_at),
                )
                if cursor.rowcount and cursor.lastrowid is not None:
                    added.append(self._memory(
                        cursor.lastrowid, conversation.user_id, conversation.character_id,
                        text, created_at,
                    ))
        return added

    def _delete(self, user_id: str, memory_id: int) -> bool:
        with self._lock, self._db:
            cursor = self._db.execute(
                "DELETE FROM memories WHERE id = ? AND user_id = ?", (memory_id, user_id)
            )
            self._db.execute(
                "DELETE FROM memory_vectors WHERE user_id = ? AND memory_id = ?",
                (user_id, memory_id),
            )
        return cursor.rowcount > 0

    def _clear(self, user_id: str) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM memories WHERE user_id = ?", (user_id,))
            self._db.execute("DELETE FROM memory_vectors WHERE user_id = ?", (user_id,))

    async def _vectors(
        self, embedder: Embedder, user_id: str, memories: list[Memory], forget: bool = True
    ) -> dict[int, bytes]:
        """The vector of each memory, embedding those not yet stored and, if `memories` are
        all the user's, forgetting those of memories that are gone. A memory deleted while
        it was being embedded gets no vector."""
        model = embedder.model
        with self._lock:
            stored: dict[int, bytes] = dict(
                self._db.execute(
                    "SELECT memory_id, embedding FROM memory_vectors"
                    " WHERE user_id = ? AND model = ?",
                    (user_id, model),
                ).fetchall()
            )
        missing = [m for m in memories if m.id not in stored]
        stale = stored.keys() - {m.id for m in memories} if forget else set()
        if missing:
            embedded = await embedder.embed_documents([Document(m.text) for m in missing])
            stored.update(zip((m.id for m in missing), map(to_blob, embedded), strict=True))
        if missing or stale:
            with self._lock, self._db:
                self._db.executemany(
                    "INSERT OR REPLACE INTO memory_vectors (memory_id, user_id, model, embedding)"
                    " SELECT ?, ?, ?, ? WHERE EXISTS (SELECT 1 FROM memories WHERE id = ?)",
                    [(m.id, user_id, model, stored[m.id], m.id) for m in missing],
                )
                self._db.executemany(
                    "DELETE FROM memory_vectors WHERE memory_id = ? AND model = ?",
                    [(memory_id, model) for memory_id in stale],
                )
        return stored


class MemoryTurn:
    """One turn's use of the user's memories; see `Memories.begin`."""

    def __init__(
        self,
        memories: Memories,
        conversation: Conversation,
        timezone: str,
        clearings: int,
        llm: ChatLLM,
    ) -> None:
        self._memories = memories
        self._conversation = conversation
        self._timezone = timezone
        self._clearings = clearings
        self._llm = llm

    async def find(self, text: str) -> str | None:
        """The prompt section carrying the user's memories relevant to `text`, most
        relevant first, each labelled with who it was told to and to be passed on as
        hearsay when that was someone else; None if none are relevant, memory is off or
        finding them failed."""
        return await self._memories._find(self._conversation, self._timezone, text)

    def write_down(self, history: Sequence[Message], text: str, reply: Message) -> None:
        """Start writing down what the user revealed in this turn: `text`, said after
        `history` and answered with `reply`."""
        self._memories._write_down(
            self._conversation, self._timezone, self._clearings, self._llm,
            history, text, reply,
        )


_INSTRUCTIONS = """\
你负责替《偶像大师 闪耀色彩》283 事务所的偶像们记住关于制作人的事。制作人就是正在和偶像对话的用户。
读下面的对话，从制作人最新的一句话里找出值得长期记住的、关于制作人本人的信息。

要记的：制作人自己透露的个人情况、喜好、经历、近况、计划、身边的人和宠物、希望偶像记住的事。
不要记的：寒暄和一时的情绪；偶像说的话；原作剧情和偶像的设定；制作人向偶像提的问题；已经记住的事。

每条记忆是一句能单独看懂的中文陈述，以「制作人」开头，例如「制作人养了一只叫小白的猫」。
提到「明天」「下周六」这样的相对时间时，换算成具体日期写下来。
和已经记住的事有出入时（例如搬了家），把新的情况写成一条新记忆。

只输出 JSON，格式为 {"memories": ["……"]}；没有值得记住的就输出 {"memories": []}。"""


def _extraction_prompt(
    character: Character,
    history: Sequence[Message],
    text: str,
    reply: Message,
    known: Sequence[Memory],
    now: datetime,
) -> list[ChatMessage]:
    lines = [f"今天是 {_date(now)}（制作人所在时区）。", "", "# 已经记住的事"]
    lines += [f"- {m.text}" for m in known[-KNOWN_MEMORIES:]] or ["（还没有）"]
    lines += ["", f"# 制作人和{character.name}的对话"]
    for message in history[-EXCHANGE_HISTORY:]:
        if message.role == "user":
            lines.append(f"制作人：{message.text}")
        else:
            lines.append(f"{character.name}：{_said(message)}")
    lines += [f"制作人（最新的一句话）：{text}", f"{character.name}：{_said(reply)}"]
    return [ChatMessage("system", _INSTRUCTIONS), ChatMessage("user", "\n".join(lines))]


def _said(reply: Message) -> str:
    reply = reply.without_cues()
    return reply.zh or reply.ja or ""


def parse_memories(answer: str) -> list[str] | None:
    """The memories in the background model's answer; None if it is not the JSON asked for."""
    start, end = answer.find("{"), answer.rfind("}")
    try:
        memories = json.loads(answer[start : end + 1])["memories"] if start >= 0 else None
    except (ValueError, KeyError, TypeError):
        return None
    if not isinstance(memories, list):
        return None
    texts = [m.strip() for m in memories if isinstance(m, str) and m.strip()]
    return [t[:MAX_MEMORY_LENGTH] for t in dict.fromkeys(texts)][:MAX_NEW_MEMORIES]


def _memories_prompt(memories: Sequence[Memory], character: Character, timezone: str) -> str:
    lines = [
        "# 关于制作人的记忆",
        "下面是制作人以前说过的、和这句话可能有关的事，按相关程度排列，和话题无关的可以忽略。"
        "像平时记得这些事一样自然地提起，不要逐条复述。",
    ]
    for memory in memories:
        when = _date(datetime.fromisoformat(memory.created_at).astimezone(ZoneInfo(timezone)))
        if memory.source_character_id == character.id:
            lines.append(f"- {memory.text}（{when}，制作人对你说的）")
        else:
            name = memory.source_character_name or ANOTHER_IDOL
            lines.append(
                f"- {memory.text}（{when}，制作人对{name}说的，你是听{name}说的：提起时要用转述的口吻，"
                f"例如「听{name}说……」，不要说成是制作人亲口告诉你的）"
            )
    return "\n".join(lines)


def _date(moment: datetime) -> str:
    return f"{moment.year}年{moment.month}月{moment.day}日"
