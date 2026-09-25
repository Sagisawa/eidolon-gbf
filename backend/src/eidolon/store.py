"""Relational storage (SQLite) for users, conversations and their messages."""

import json
import sqlite3
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from eidolon.reply_format import Segment

DEFAULT_USER_ID = "default"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    character_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    role TEXT NOT NULL CHECK (role IN ('user', 'character')),
    text TEXT,
    ja TEXT,
    zh TEXT,
    segments TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_by_conversation ON messages(conversation_id, id);
"""


@dataclass(frozen=True)
class Conversation:
    id: str
    user_id: str
    character_id: str
    created_at: str


@dataclass(frozen=True)
class Message:
    """A user's input (`text`) or a character's reply.

    A reply keeps its full Japanese text (`ja`) and Chinese subtitle (`zh`), plus
    the segments that pair each Japanese line with its own subtitle.
    """

    id: int
    role: Literal["user", "character"]
    text: str | None
    ja: str | None
    zh: str | None
    created_at: str
    segments: list[Segment] = field(default_factory=list)


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.execute("PRAGMA foreign_keys = ON")
            self._db.executescript(_SCHEMA)
            self._db.execute(
                "INSERT OR IGNORE INTO users (id, created_at) VALUES (?, ?)",
                (DEFAULT_USER_ID, _now()),
            )

    def create_conversation(self, user_id: str, character_id: str) -> Conversation:
        conversation = Conversation(uuid.uuid4().hex, user_id, character_id, _now())
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO conversations (id, user_id, character_id, created_at)"
                " VALUES (?, ?, ?, ?)",
                (conversation.id, user_id, character_id, conversation.created_at),
            )
        return conversation

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
        return Conversation(**row) if row else None

    def list_conversations(self, user_id: str, character_id: str) -> list[Conversation]:
        """Newest first."""
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM conversations WHERE user_id = ? AND character_id = ?"
                " ORDER BY created_at DESC, rowid DESC",
                (user_id, character_id),
            ).fetchall()
        return [Conversation(**row) for row in rows]

    def add_user_message(self, conversation_id: str, text: str) -> Message:
        return self._add_message(conversation_id, "user", text=text)

    def add_character_message(self, conversation_id: str, segments: list[Segment]) -> Message:
        return self._add_message(conversation_id, "character", segments=segments)

    def list_messages(self, conversation_id: str) -> list[Message]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, role, text, ja, zh, segments, created_at FROM messages"
                " WHERE conversation_id = ? ORDER BY id",
                (conversation_id,),
            ).fetchall()
        return [
            Message(
                row["id"], row["role"], row["text"], row["ja"], row["zh"], row["created_at"],
                [Segment(**s) for s in json.loads(row["segments"] or "[]")],
            )
            for row in rows
        ]

    def close(self) -> None:
        self._db.close()

    def _add_message(
        self,
        conversation_id: str,
        role: Literal["user", "character"],
        text: str | None = None,
        segments: list[Segment] | None = None,
    ) -> Message:
        created_at = _now()
        ja = zh = stored_segments = None
        if segments is not None:
            ja = "".join(s.ja for s in segments)
            zh = "".join(s.zh for s in segments)
            stored_segments = json.dumps([asdict(s) for s in segments], ensure_ascii=False)
        with self._lock, self._db:
            cursor = self._db.execute(
                "INSERT INTO messages (conversation_id, role, text, ja, zh, segments, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (conversation_id, role, text, ja, zh, stored_segments, created_at),
            )
        assert cursor.lastrowid is not None
        return Message(cursor.lastrowid, role, text, ja, zh, created_at, segments or [])


def _now() -> str:
    return datetime.now(UTC).isoformat()
