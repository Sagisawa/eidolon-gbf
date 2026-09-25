"""Memory: what users tell the characters, kept across conversations.

After each turn the background model reads the exchange and writes down, in Chinese,
whatever the user revealed about themselves that is worth keeping. Each memory belongs
to the user and names the character it was told to, its source character. All of a
user's characters share their memories, and a character recalling one told to someone
else is asked to pass it on as hearsay (ADR-0002); users never share theirs.

Writing runs in the background so it never holds up the reply. The user's next turn
waits briefly for it, so what they just said is remembered by the time they go on; a
new conversation picks up where earlier ones left off only through the memories it
retrieves.

Memories are searched like character facts: each is embedded the first time its user's
memories are searched, and the vector is kept until the memory is gone.
"""

import asyncio
import json
import logging
import sqlite3
import threading
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from eidolon.characters import Character
from eidolon.embedding import Embedder, nearest, to_blob
from eidolon.llm import ChatLLM, ChatMessage
from eidolon.store import Conversation, Memory, Message, Store

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


_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_vectors (
    memory_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    model TEXT NOT NULL,
    embedding BLOB NOT NULL,
    PRIMARY KEY (memory_id, model)
);
CREATE INDEX IF NOT EXISTS memory_vectors_by_user ON memory_vectors(user_id, model);
"""


class MemoryIndex:
    """The vector index of each user's memories."""

    def __init__(self, path: Path, store: Store, embedder: Embedder) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self._lock = threading.Lock()
        self._store = store
        self._embedder = embedder
        with self._lock, self._db:
            self._db.executescript(_SCHEMA)

    async def search_by_vector(
        self, query_vector: Sequence[float], user_id: str, limit: int
    ) -> list[Memory]:
        """The user's memories most similar to a query embedded with this index's embedder."""
        memories = await asyncio.to_thread(self._store.list_memories, user_id)
        vectors = await self._vectors(user_id, memories)
        best = nearest([vectors[m.id] for m in memories], query_vector, limit)
        return [memories[i] for i, _ in best]

    def close(self) -> None:
        self._db.close()

    async def _vectors(self, user_id: str, memories: list[Memory]) -> dict[int, bytes]:
        """The vector of each memory, embedding those not yet stored and forgetting those of
        memories that are gone."""
        model = self._embedder.model
        with self._lock:
            stored: dict[int, bytes] = dict(
                self._db.execute(
                    "SELECT memory_id, embedding FROM memory_vectors"
                    " WHERE user_id = ? AND model = ?",
                    (user_id, model),
                ).fetchall()
            )
        missing = [m for m in memories if m.id not in stored]
        stale = stored.keys() - {m.id for m in memories}
        if missing:
            embedded = await self._embedder.embed_documents([m.text for m in missing])
            stored.update(zip((m.id for m in missing), map(to_blob, embedded), strict=True))
        if missing or stale:
            with self._lock, self._db:
                self._db.executemany(
                    "INSERT OR REPLACE INTO memory_vectors (memory_id, user_id, model, embedding)"
                    " VALUES (?, ?, ?, ?)",
                    [(m.id, user_id, model, stored[m.id]) for m in missing],
                )
                self._db.executemany(
                    "DELETE FROM memory_vectors WHERE memory_id = ? AND model = ?",
                    [(memory_id, model) for memory_id in stale],
                )
        return stored


_INSTRUCTIONS = """\
你负责替《偶像大师 闪耀色彩》283 事务所的偶像们记住关于制作人的事。制作人就是正在和偶像对话的用户。
读下面的对话，从制作人最新的一句话里找出值得长期记住的、关于制作人本人的信息。

要记的：制作人自己透露的个人情况、喜好、经历、近况、计划、身边的人和宠物、希望偶像记住的事。
不要记的：寒暄和一时的情绪；偶像说的话；原作剧情和偶像的设定；制作人向偶像提的问题；已经记住的事。

每条记忆是一句能单独看懂的中文陈述，以「制作人」开头，例如「制作人养了一只叫小白的猫」。
提到「明天」「下周六」这样的相对时间时，换算成具体日期写下来。
和已经记住的事有出入时（例如搬了家），把新的情况写成一条新记忆。

只输出 JSON，格式为 {"memories": ["……"]}；没有值得记住的就输出 {"memories": []}。"""


class MemoryWriter:
    """Has the background model write down what the user reveals in each turn."""

    def __init__(self, store: Store, background_llm: ChatLLM) -> None:
        self._store = store
        self._llm = background_llm
        self._pending: dict[str, set[asyncio.Task[None]]] = {}  # user id → writing

    def remember(
        self,
        conversation: Conversation,
        character: Character,
        history: Sequence[Message],
        text: str,
        reply: Message,
        now: datetime,
    ) -> None:
        """Start writing down what the user revealed in this turn; `now` is the current time
        where the user is."""
        task = asyncio.create_task(
            self._write(conversation, character, history, text, reply, now)
        )
        pending = self._pending.setdefault(conversation.user_id, set())
        pending.add(task)

        def done(task: asyncio.Task[None]) -> None:
            pending.discard(task)
            if not pending and self._pending.get(conversation.user_id) is pending:
                del self._pending[conversation.user_id]

        task.add_done_callback(done)

    async def settle(self, user_id: str, timeout: float = SETTLE_TIMEOUT) -> None:
        """Wait, a while at most, for what the user's earlier turns are writing down."""
        if pending := self._pending.get(user_id):
            await asyncio.wait(set(pending), timeout=timeout)

    async def aclose(self, timeout: float = SETTLE_TIMEOUT) -> None:
        """Let whatever is being written down finish, a while at most."""
        tasks = {t for pending in self._pending.values() for t in pending}
        if tasks:
            await asyncio.wait(tasks, timeout=timeout)

    async def _write(
        self,
        conversation: Conversation,
        character: Character,
        history: Sequence[Message],
        text: str,
        reply: Message,
        now: datetime,
    ) -> None:
        try:
            known = await asyncio.to_thread(self._store.list_memories, conversation.user_id)
            prompt = _extraction_prompt(character, history, text, reply, known, now)
            said = "".join([chunk async for chunk in self._llm.stream(prompt) if isinstance(chunk, str)])
            texts = parse_memories(said)
            if texts is None:
                log.warning("background model wrote no memories JSON: %.500s", said)
                return
            await asyncio.to_thread(self._store.add_memories, conversation, texts)
        except Exception:
            log.warning("writing memories failed in conversation %s", conversation.id,
                        exc_info=True)


def _extraction_prompt(
    character: Character,
    history: Sequence[Message],
    text: str,
    reply: Message,
    known: Sequence[Memory],
    now: datetime,
) -> list[ChatMessage]:
    lines = [f"今天是 {now.year}年{now.month}月{now.day}日（制作人所在时区）。", "", "# 已经记住的事"]
    lines += [f"- {m.text}" for m in known[-KNOWN_MEMORIES:]] or ["（还没有）"]
    lines += ["", f"# 制作人和{character.name}的对话"]
    for message in history[-EXCHANGE_HISTORY:]:
        if message.role == "user":
            lines.append(f"制作人：{message.text}")
        else:
            lines.append(f"{character.name}：{message.zh or message.ja}")
    lines += [f"制作人（最新的一句话）：{text}", f"{character.name}：{reply.zh or reply.ja}"]
    return [ChatMessage("system", _INSTRUCTIONS), ChatMessage("user", "\n".join(lines))]


def parse_memories(said: str) -> list[str] | None:
    """The memories in the background model's answer; None if it is not the JSON asked for."""
    start, end = said.find("{"), said.rfind("}")
    try:
        memories = json.loads(said[start : end + 1])["memories"] if start >= 0 else None
    except (ValueError, KeyError, TypeError):
        return None
    if not isinstance(memories, list):
        return None
    texts = [m.strip() for m in memories if isinstance(m, str) and m.strip()]
    return [t[:MAX_MEMORY_LENGTH] for t in dict.fromkeys(texts)][:MAX_NEW_MEMORIES]


def memories_prompt(
    memories: Sequence[Memory], character: Character, names: Mapping[str, str], timezone: str
) -> str:
    """The prompt section carrying a turn's memories, each labelled with who it was told
    to, and to be passed on as hearsay when that was someone else."""
    lines = [
        "# 关于制作人的记忆",
        "下面是制作人以前说过的、和这句话可能有关的事，按相关程度排列，和话题无关的可以忽略。"
        "像平时记得这些事一样自然地提起，不要逐条复述。",
    ]
    for memory in memories:
        told = datetime.fromisoformat(memory.created_at).astimezone(ZoneInfo(timezone))
        when = f"{told.year}年{told.month}月{told.day}日"
        if memory.source_character_id == character.id:
            lines.append(f"- {memory.text}（{when}，制作人对你说的）")
        else:
            name = names.get(memory.source_character_id, "事务所的另一位偶像")
            lines.append(
                f"- {memory.text}（{when}，制作人对{name}说的，你是听{name}说的：提起时要用转述的口吻，"
                f"例如「听{name}说……」，不要说成是制作人亲口告诉你的）"
            )
    return "\n".join(lines)
