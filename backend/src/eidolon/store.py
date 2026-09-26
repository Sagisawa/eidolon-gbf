"""Relational storage (SQLite) for users, access keys, producer profiles, conversations
and their messages, and each user's recent usage; memories are kept by `memory`."""

import hashlib
import json
import secrets
import sqlite3
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from eidolon.producer import ProducerProfile
from eidolon.reply_format import Segment

Role = Literal["user", "character"]

UsageKind = Literal["turn", "call"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS access_keys (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    secret_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS producer_profiles (
    user_id TEXT PRIMARY KEY REFERENCES users(id),
    form_of_address TEXT,
    gender TEXT,
    timezone TEXT,
    updated_at TEXT NOT NULL
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
-- `at` is epoch seconds rather than ISO text, so that the window is a plain range query.
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL,
    at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS usage_by_user ON usage(user_id, kind, at);
"""


@dataclass(frozen=True)
class User:
    id: str
    name: str
    created_at: str


@dataclass(frozen=True)
class AccessKey:
    """A key as the admin sees it: its id and state, never the secret itself."""

    id: str
    user_id: str
    created_at: str
    revoked_at: str | None


class KeyRevoked(Exception):
    pass


class LimitReached(Exception):
    """The user has no uses left in the window; the next is allowed at `retry_at`."""

    def __init__(self, retry_at: datetime) -> None:
        super().__init__(f"limit reached until {retry_at.isoformat()}")
        self.retry_at = retry_at


class NotFound(LookupError):
    pass


class DuplicateName(ValueError):
    pass


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
    role: Role
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
            self._migrate()

    def _migrate(self) -> None:
        columns = {row["name"] for row in self._db.execute("PRAGMA table_info(users)")}
        if "name" not in columns:
            # Before access keys, users had no name; the one default user keeps its id as name.
            self._db.execute("ALTER TABLE users ADD COLUMN name TEXT")
            self._db.execute("UPDATE users SET name = id")
        self._db.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_by_name ON users(name)")

    def create_user(self, name: str) -> User:
        user = User(uuid.uuid4().hex, name, _now())
        try:
            with self._lock, self._db:
                self._db.execute(
                    "INSERT INTO users (id, name, created_at) VALUES (?, ?, ?)",
                    (user.id, user.name, user.created_at),
                )
        except sqlite3.IntegrityError:
            raise DuplicateName(f"用户 {name} 已存在") from None
        return user

    def list_users(self) -> list[User]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, name, created_at FROM users ORDER BY created_at, rowid"
            ).fetchall()
        return [User(**row) for row in rows]

    def get_user_by_name(self, name: str) -> User:
        with self._lock:
            row = self._db.execute(
                "SELECT id, name, created_at FROM users WHERE name = ?", (name,)
            ).fetchone()
        if row is None:
            raise NotFound(f"用户 {name} 不存在")
        return User(**row)

    def issue_key(self, user_id: str) -> tuple[AccessKey, str]:
        """Issue a new key for the user; returns it with its secret, which is not stored."""
        key = AccessKey(secrets.token_hex(4), user_id, _now(), None)
        secret = f"esc_{secrets.token_urlsafe(24)}"
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO access_keys (id, user_id, secret_hash, created_at)"
                " VALUES (?, ?, ?, ?)",
                (key.id, user_id, _hash(secret), key.created_at),
            )
        return key, secret

    def revoke_key(self, key_id: str) -> None:
        with self._lock, self._db:
            cursor = self._db.execute(
                "UPDATE access_keys SET revoked_at = COALESCE(revoked_at, ?) WHERE id = ?",
                (_now(), key_id),
            )
        if cursor.rowcount == 0:
            raise NotFound(f"访问密钥 {key_id} 不存在")

    def list_keys(self, user_id: str) -> list[AccessKey]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, user_id, created_at, revoked_at FROM access_keys"
                " WHERE user_id = ? ORDER BY created_at, rowid",
                (user_id,),
            ).fetchall()
        return [AccessKey(**row) for row in rows]

    def user_for_key(self, secret: str) -> str | None:
        """The id of the user holding this key; None for an unknown key.

        Raises KeyRevoked for a key that has been revoked.
        """
        with self._lock:
            row = self._db.execute(
                "SELECT user_id, revoked_at FROM access_keys WHERE secret_hash = ?",
                (_hash(secret),),
            ).fetchone()
        if row is None:
            return None
        if row["revoked_at"] is not None:
            raise KeyRevoked
        return row["user_id"]

    def get_profile(self, user_id: str) -> ProducerProfile:
        """The user's producer profile; all defaults until they save one."""
        with self._lock:
            row = self._db.execute(
                "SELECT form_of_address, gender, timezone FROM producer_profiles"
                " WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return ProducerProfile(**row) if row else ProducerProfile()

    def save_profile(self, user_id: str, profile: ProducerProfile) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO producer_profiles"
                " (user_id, form_of_address, gender, timezone, updated_at)"
                " VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT (user_id) DO UPDATE SET form_of_address = excluded.form_of_address,"
                " gender = excluded.gender, timezone = excluded.timezone,"
                " updated_at = excluded.updated_at",
                (user_id, profile.form_of_address, profile.gender, profile.timezone, _now()),
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

    def add_turn(self, conversation_id: str, text: str, reply: list[Segment]) -> Message:
        """Record the user's input and the character's reply together; returns the reply."""
        with self._lock, self._db:
            self._insert_message(conversation_id, "user", text=text)
            return self._insert_message(conversation_id, "character", segments=reply)

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

    def take_usage(
        self, user_id: str, kind: UsageKind, now: datetime, window: timedelta, limit: int
    ) -> int:
        """Record one use of `kind` by the user at `now` and return its id, unless they
        already have `limit` uses in the `window` before it: then record nothing and raise
        LimitReached with when enough of those will have aged out. The user's older uses
        of `kind` are forgotten."""
        since = (now - window).timestamp()
        with self._lock, self._db:
            self._db.execute(
                "DELETE FROM usage WHERE user_id = ? AND kind = ? AND at <= ?",
                (user_id, kind, since),
            )
            recent = [
                row["at"]
                for row in self._db.execute(
                    "SELECT at FROM usage WHERE user_id = ? AND kind = ? ORDER BY at",
                    (user_id, kind),
                )
            ]
            if len(recent) >= limit:
                blocking = recent[len(recent) - limit]  # this one must age out first
                raise LimitReached(datetime.fromtimestamp(blocking, UTC) + window)
            cursor = self._db.execute(
                "INSERT INTO usage (user_id, kind, at) VALUES (?, ?, ?)",
                (user_id, kind, now.timestamp()),
            )
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def give_back_usage(self, use_id: int) -> None:
        """Forget a use, as if it had never been taken."""
        with self._lock, self._db:
            self._db.execute("DELETE FROM usage WHERE id = ?", (use_id,))

    def close(self) -> None:
        self._db.close()

    def _insert_message(
        self,
        conversation_id: str,
        role: Role,
        text: str | None = None,
        segments: list[Segment] | None = None,
    ) -> Message:
        created_at = _now()
        ja = zh = stored_segments = None
        if segments is not None:
            ja = "".join(s.ja for s in segments)
            zh = "".join(s.zh for s in segments)
            stored_segments = json.dumps([asdict(s) for s in segments], ensure_ascii=False)
        cursor = self._db.execute(
            "INSERT INTO messages (conversation_id, role, text, ja, zh, segments, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (conversation_id, role, text, ja, zh, stored_segments, created_at),
        )
        assert cursor.lastrowid is not None
        return Message(cursor.lastrowid, role, text, ja, zh, created_at, segments or [])


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()
