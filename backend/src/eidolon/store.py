"""Relational storage (SQLite) for users, their sessions, producer profiles, conversations
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
-- `name` only tells users apart on the admin command line; it need not be unique.
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    consented_at TEXT,
    banned_at TEXT
);
-- Only a hash of each session's token is kept; the times are epoch seconds.
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    last_active_at REAL NOT NULL,
    expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_by_user ON sessions(user_id);
-- A Google or GitHub identity a user signs in with; each belongs to one user only.
CREATE TABLE IF NOT EXISTS sign_in_methods (
    user_id TEXT NOT NULL REFERENCES users(id),
    provider TEXT NOT NULL,
    subject TEXT NOT NULL,
    display_name TEXT NOT NULL,
    email TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (provider, subject)
);
CREATE INDEX IF NOT EXISTS sign_in_methods_by_user ON sign_in_methods(user_id);
-- A user's own key for a service, encrypted; an LLM also has where it is and which model.
CREATE TABLE IF NOT EXISTS own_keys (
    user_id TEXT NOT NULL REFERENCES users(id),
    service TEXT NOT NULL,
    secret BLOB NOT NULL,
    last4 TEXT NOT NULL,
    base_url TEXT,
    model TEXT,
    protocol TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, service)
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


SESSION_LIFETIME = timedelta(days=30)
"""How long a session lasts after it was last used."""
SESSION_RENEWAL = timedelta(hours=1)
"""How long after its last renewal a session in use is renewed again, rather than on
every request."""


@dataclass(frozen=True)
class User:
    id: str
    name: str
    created_at: str
    consented_at: str | None = None
    """When they agreed to the privacy policy and terms of use; None until they do."""
    banned_at: str | None = None


@dataclass(frozen=True)
class Session:
    """A signed-in browser's session. `renewed` says this use renewed it, so the browser's
    cookie should be renewed too."""

    user: User
    renewed: bool


@dataclass(frozen=True)
class SignInMethod:
    """An identity at a provider (Google or GitHub) that signs a user in; `subject` is the
    provider's id for it."""

    provider: str
    subject: str
    display_name: str
    email: str | None
    created_at: str


@dataclass(frozen=True)
class OwnKeyRecord:
    """A user's own key for a service as stored: `secret` is the key, encrypted."""

    service: str
    secret: bytes
    last4: str
    base_url: str | None = None
    model: str | None = None
    protocol: str | None = None


class IdentityTaken(Exception):
    """The identity already belongs to a user."""


class LastSignInMethod(Exception):
    """Removing it would leave the user no way to sign in."""


class LimitReached(Exception):
    """The user has no uses left in the window; the next is allowed at `retry_at`."""

    def __init__(self, retry_at: datetime) -> None:
        super().__init__(f"limit reached until {retry_at.isoformat()}")
        self.retry_at = retry_at


class NotFound(LookupError):
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
        # Readers need not wait for a writer: the store, memory and the corpus each have a
        # connection to this database.
        self._db.execute("PRAGMA journal_mode = WAL")
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
        for column in ("consented_at", "banned_at"):
            if column not in columns:
                self._db.execute(f"ALTER TABLE users ADD COLUMN {column} TEXT")
        # Access keys are gone (ADR-0006), and with them unique names.
        self._db.execute("DROP INDEX IF EXISTS users_by_name")
        self._db.execute("DROP TABLE IF EXISTS access_keys")

    def create_user(self, name: str) -> User:
        user = User(uuid.uuid4().hex, name, _now())
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO users (id, name, created_at) VALUES (?, ?, ?)",
                (user.id, user.name, user.created_at),
            )
        return user

    def list_users(self) -> list[User]:
        with self._lock:
            rows = self._db.execute(
                f"SELECT {_USER_COLUMNS} FROM users ORDER BY created_at, rowid"
            ).fetchall()
        return [User(**row) for row in rows]

    def get_user(self, user_id: str) -> User:
        with self._lock:
            row = self._db.execute(
                f"SELECT {_USER_COLUMNS} FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        if row is None:
            raise NotFound(f"用户 {user_id} 不存在")
        return User(**row)

    def first_user_named(self, name: str) -> User | None:
        """The earliest user with this name, if any; names are not unique."""
        with self._lock:
            row = self._db.execute(
                f"SELECT {_USER_COLUMNS} FROM users WHERE name = ? ORDER BY created_at, rowid",
                (name,),
            ).fetchone()
        return User(**row) if row else None

    def consent(self, user_id: str, now: datetime) -> None:
        """Record that the user agreed to the privacy policy and terms of use."""
        with self._lock, self._db:
            self._db.execute(
                "UPDATE users SET consented_at = ? WHERE id = ?", (now.isoformat(), user_id)
            )

    def user_signing_in_with(self, provider: str, subject: str) -> str | None:
        """The id of the user this identity belongs to, if any."""
        with self._lock:
            row = self._db.execute(
                "SELECT user_id FROM sign_in_methods WHERE provider = ? AND subject = ?",
                (provider, subject),
            ).fetchone()
        return row["user_id"] if row else None

    def create_user_signing_in_with(self, name: str, method: SignInMethod) -> User:
        """A new user, whose one sign-in method is `method`. Raises IdentityTaken, making
        no one, if the identity already belongs to someone."""
        user = User(uuid.uuid4().hex, name, _now())
        try:
            with self._lock, self._db:
                self._db.execute(
                    "INSERT INTO users (id, name, created_at) VALUES (?, ?, ?)",
                    (user.id, user.name, user.created_at),
                )
                self._insert_sign_in_method(user.id, method)
        except sqlite3.IntegrityError:
            raise IdentityTaken from None
        return user

    def add_sign_in_method(self, user_id: str, method: SignInMethod) -> None:
        """Raises IdentityTaken if the identity already belongs to someone."""
        try:
            with self._lock, self._db:
                self._insert_sign_in_method(user_id, method)
        except sqlite3.IntegrityError:
            raise IdentityTaken from None

    def update_sign_in_method(self, provider: str, subject: str, display_name: str,
                              email: str | None) -> None:
        """Keep the name and email the provider now gives for the identity."""
        with self._lock, self._db:
            self._db.execute(
                "UPDATE sign_in_methods SET display_name = ?, email = ?"
                " WHERE provider = ? AND subject = ?",
                (display_name, email, provider, subject),
            )

    def sign_in_methods(self, user_id: str) -> list[SignInMethod]:
        """In the order they were added."""
        with self._lock:
            rows = self._db.execute(
                "SELECT provider, subject, display_name, email, created_at FROM sign_in_methods"
                " WHERE user_id = ? ORDER BY created_at, rowid",
                (user_id,),
            ).fetchall()
        return [SignInMethod(**row) for row in rows]

    def remove_sign_in_method(self, user_id: str, provider: str) -> bool:
        """Remove the user's sign-in method at `provider`; False if they have none there.
        Raises LastSignInMethod, removing nothing, if it is the only one they have."""
        with self._lock, self._db:
            providers = [
                row["provider"]
                for row in self._db.execute(
                    "SELECT provider FROM sign_in_methods WHERE user_id = ?", (user_id,)
                )
            ]
            if provider not in providers:
                return False
            if len(providers) == 1:
                raise LastSignInMethod
            self._db.execute(
                "DELETE FROM sign_in_methods WHERE user_id = ? AND provider = ?",
                (user_id, provider),
            )
        return True

    def save_own_key(self, user_id: str, key: OwnKeyRecord) -> None:
        """Keep the user's key for `key.service`, replacing the one they had."""
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO own_keys"
                " (user_id, service, secret, last4, base_url, model, protocol, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, key.service, key.secret, key.last4, key.base_url, key.model,
                 key.protocol, _now()),
            )

    def own_keys(self, user_id: str) -> dict[str, OwnKeyRecord]:
        """The user's own keys, by service."""
        with self._lock:
            rows = self._db.execute(
                "SELECT service, secret, last4, base_url, model, protocol FROM own_keys"
                " WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        return {row["service"]: OwnKeyRecord(**row) for row in rows}

    def delete_own_key(self, user_id: str, service: str) -> bool:
        with self._lock, self._db:
            cursor = self._db.execute(
                "DELETE FROM own_keys WHERE user_id = ? AND service = ?", (user_id, service)
            )
        return cursor.rowcount > 0

    def delete_user(self, user_id: str) -> None:
        """Delete the user and everything of theirs, for good, all at once."""
        with self._lock, self._db:
            tables = {
                row["name"]
                for row in self._db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
            for table, where in _USER_DATA:
                if table in tables:  # memory's tables exist once memory has opened them
                    self._db.execute(f"DELETE FROM {table} WHERE {where}", (user_id,))

    def create_session(self, user_id: str, now: datetime) -> str:
        """Start a session for the user; returns its token, which is not stored."""
        token = secrets.token_urlsafe(32)
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO sessions (token_hash, user_id, last_active_at, expires_at)"
                " VALUES (?, ?, ?, ?)",
                (_hash(token), user_id, now.timestamp(), (now + SESSION_LIFETIME).timestamp()),
            )
        return token

    def use_session(self, token: str, now: datetime) -> Session | None:
        """The session with this token, renewed for another `SESSION_LIFETIME` if it has
        not been for a while; None if there is none or it has expired."""
        token_hash = _hash(token)
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT user_id, last_active_at, expires_at FROM sessions WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            if row["expires_at"] <= now.timestamp():
                self._db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
                return None
            renewed = now.timestamp() - row["last_active_at"] >= SESSION_RENEWAL.total_seconds()
            if renewed:
                self._db.execute(
                    "UPDATE sessions SET last_active_at = ?, expires_at = ? WHERE token_hash = ?",
                    (now.timestamp(), (now + SESSION_LIFETIME).timestamp(), token_hash),
                )
            user = self._db.execute(
                f"SELECT {_USER_COLUMNS} FROM users WHERE id = ?", (row["user_id"],)
            ).fetchone()
        return Session(User(**user), renewed)

    def end_session(self, token: str) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash(token),))

    def end_sessions(self, user_id: str) -> None:
        """Sign the user out everywhere."""
        with self._lock, self._db:
            self._db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))

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

    def _insert_sign_in_method(self, user_id: str, method: SignInMethod) -> None:
        self._db.execute(
            "INSERT INTO sign_in_methods"
            " (user_id, provider, subject, display_name, email, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, method.provider, method.subject, method.display_name, method.email,
             method.created_at),
        )

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


_USER_COLUMNS = "id, name, created_at, consented_at, banned_at"

_USER_DATA = [
    ("memory_vectors", "user_id = ?"),
    ("memories", "user_id = ?"),
    ("messages", "conversation_id IN (SELECT id FROM conversations WHERE user_id = ?)"),
    ("conversations", "user_id = ?"),
    ("producer_profiles", "user_id = ?"),
    ("usage", "user_id = ?"),
    ("sessions", "user_id = ?"),
    ("sign_in_methods", "user_id = ?"),
    ("own_keys", "user_id = ?"),
    ("users", "id = ?"),
]
"""Every table holding a user's data, and which rows are theirs, in an order that deletes
what refers to a row before the row. A table added for users' data must be added here."""


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()
