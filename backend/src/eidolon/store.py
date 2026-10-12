"""Relational storage (SQLite) for users, their sessions, producer profiles, conversations
and their messages; memories are kept by `memory`, recent usage by `usage`."""

import hashlib
import json
import secrets
import sqlite3
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from eidolon.database import connect, delete_user_data
from eidolon.delivery_cues import without_cues
from eidolon.producer import Birthday, ProducerProfile
from eidolon.reply_format import Segment

Role = Literal["user", "character"]

_SCHEMA = """
-- `name` only tells users apart on the admin command line; it need not be unique.
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    consented_at TEXT,
    banned_at TEXT,
    ban_note TEXT
);
-- Only a hash of each session's token is kept; the times are epoch seconds.
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    last_active_at REAL NOT NULL,
    expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_by_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS sessions_by_expiry ON sessions(expires_at);
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
CREATE TABLE IF NOT EXISTS producer_profiles (
    user_id TEXT PRIMARY KEY REFERENCES users(id),
    form_of_address TEXT,
    gender TEXT,
    timezone TEXT,
    updated_at TEXT NOT NULL,
    birthday_month INTEGER,
    birthday_day INTEGER
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
-- The identities banned users signed in with, kept when those users were deleted so that
-- deleting is not unbanning; only a keyed hash of each (`accounts.identity_hash`), no one's.
CREATE TABLE IF NOT EXISTS banned_identities (
    identity_hash TEXT PRIMARY KEY,
    added_at TEXT NOT NULL
);
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
    ban_note: str | None = None
    """Why they were banned, as the admin who banned them wrote; only admins see it."""


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


class IdentityTaken(Exception):
    """The identity already belongs to a user."""


class LastSignInMethod(Exception):
    """Removing it would leave the user no way to sign in."""


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

    def without_cues(self) -> "Message":
        """The message as people see it: a reply is kept as the model wrote it, delivery
        cues and all (ADR-0007)."""
        if self.role != "character":
            return self
        return Message(
            self.id, self.role, self.text,
            None if self.ja is None else without_cues(self.ja),
            None if self.zh is None else without_cues(self.zh),
            self.created_at,
            [Segment(without_cues(s.ja), without_cues(s.zh)) for s in self.segments],
        )


class Store:
    def __init__(self, path: Path) -> None:
        self._db = connect(path)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.executescript(_SCHEMA)
            self._migrate()

    def _migrate(self) -> None:
        columns = self._columns("users")
        if "name" not in columns:
            # Before access keys, users had no name; the one default user keeps its id as name.
            self._db.execute("ALTER TABLE users ADD COLUMN name TEXT")
            self._db.execute("UPDATE users SET name = id")
        self._add_missing_columns("users", ("consented_at", "banned_at", "ban_note"), "TEXT")
        self._add_missing_columns("producer_profiles", ("birthday_month", "birthday_day"), "INTEGER")
        # Access keys are gone (ADR-0006), and with them unique names.
        self._db.execute("DROP INDEX IF EXISTS users_by_name")
        self._db.execute("DROP TABLE IF EXISTS access_keys")
        # Users' own keys stay in their browsers (ADR-0017); those kept here, encrypted, go.
        self._db.execute("DROP TABLE IF EXISTS own_keys")

    def _columns(self, table: str) -> set[str]:
        return {row["name"] for row in self._db.execute(f"PRAGMA table_info({table})")}

    def _add_missing_columns(self, table: str, columns: tuple[str, ...], kind: str) -> None:
        """Add the columns a table made by an older version lacks; existing rows get NULL."""
        present = self._columns(table)
        for column in columns:
            if column not in present:
                self._db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")

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

    def find_users(
        self,
        query: str,
        offset: int,
        limit: int,
        ranking: tuple[str, list[Any]] | None = None,
    ) -> tuple[list[User], int]:
        """A page of the users whose id starts with `query`, or whose name, or the name or
        email of an identity they sign in with, has it in it, in any case; all users for
        an empty query. Newest first, or highest first by `ranking`, an SQL expression
        over a row of `users` with its parameters (as `ActivityLog.ranking`), then newest;
        with how many there are in all."""
        where, params = "", []
        if query := query.strip():
            # Taken as it is: `%` and `_` are not wildcards here.
            escaped = query.replace("!", "!!").replace("%", "!%").replace("_", "!_")
            inside = f"%{escaped}%"
            where = (
                "WHERE id LIKE ? ESCAPE '!' OR name LIKE ? ESCAPE '!' OR EXISTS ("
                "SELECT 1 FROM sign_in_methods m WHERE m.user_id = users.id"
                " AND (m.display_name LIKE ? ESCAPE '!' OR m.email LIKE ? ESCAPE '!'))"
            )
            params = [f"{escaped}%", inside, inside, inside]
        with self._lock:
            rows = self._db.execute(
                f"SELECT {_USER_COLUMNS} FROM users {where}"
                f" ORDER BY {f'{ranking[0]} DESC, ' if ranking else ''}"
                "created_at DESC, rowid DESC LIMIT ? OFFSET ?",
                [*params, *(ranking[1] if ranking else []), limit, offset],
            ).fetchall()
            [(total,)] = self._db.execute(f"SELECT COUNT(*) FROM users {where}", params)
        return [User(**row) for row in rows], total

    def last_active(self, user_ids: list[str]) -> dict[str, datetime]:
        """When each of the users, of those signed in anywhere, was last active: the
        latest renewal of any of their sessions."""
        with self._lock:
            rows = self._db.execute(
                "SELECT user_id, MAX(last_active_at) FROM sessions WHERE user_id IN"
                f" ({','.join('?' * len(user_ids))}) GROUP BY user_id",
                user_ids,
            ).fetchall()
        return {user_id: datetime.fromtimestamp(at, UTC) for user_id, at in rows}

    def set_banned(
        self, user_id: str, banned_at: datetime | None, note: str | None = None
    ) -> None:
        """Ban the user as of `banned_at`, with a note only admins see, signing them out
        everywhere; None lifts the ban, and the note with it. Raises NotFound for no such
        user."""
        with self._lock, self._db:
            cursor = self._db.execute(
                "UPDATE users SET banned_at = ?, ban_note = ? WHERE id = ?",
                (banned_at.isoformat() if banned_at else None,
                 note if banned_at else None, user_id),
            )
            if cursor.rowcount == 0:
                raise NotFound(f"用户 {user_id} 不存在")
            if banned_at is not None:
                self._db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))

    def active_users(self, user_ids: set[str]) -> set[str]:
        """Those of the users who still exist and are not banned."""
        with self._lock:
            return {
                row["id"]
                for row in self._db.execute(
                    f"SELECT id FROM users WHERE banned_at IS NULL AND id IN"
                    f" ({','.join('?' * len(user_ids))})",
                    list(user_ids),
                )
            } if user_ids else set()

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

    def delete_user(self, user_id: str, banned_identities: list[str] | None = None) -> None:
        """Delete the user and everything of theirs, for good, all at once (see
        `database.delete_user_data`), first putting `banned_identities`, hashes of the
        identities they signed in with, on the ban list if they were banned."""
        with self._lock:
            if banned_identities:
                with self._db:
                    self._db.executemany(
                        "INSERT OR IGNORE INTO banned_identities (identity_hash, added_at)"
                        " VALUES (?, ?)",
                        [(h, _now()) for h in banned_identities],
                    )
            delete_user_data(self._db, user_id)

    def is_banned_identity(self, identity_hash: str) -> bool:
        """Whether a banned user since deleted signed in with the identity of this hash."""
        with self._lock:
            return self._db.execute(
                "SELECT 1 FROM banned_identities WHERE identity_hash = ?", (identity_hash,)
            ).fetchone() is not None

    def create_session(self, user_id: str, now: datetime) -> str:
        """Start a session for the user; returns its token, which is not stored. Every
        session that has expired, whoever's it is, is deleted meanwhile, so that a user who
        does not come back leaves none behind."""
        token = secrets.token_urlsafe(32)
        with self._lock, self._db:
            self._db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now.timestamp(),))
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
                "SELECT form_of_address, gender, timezone, birthday_month, birthday_day"
                " FROM producer_profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if not row:
            return ProducerProfile()
        birthday = (
            Birthday(row["birthday_month"], row["birthday_day"])
            if row["birthday_month"] is not None and row["birthday_day"] is not None
            else None
        )
        return ProducerProfile(row["form_of_address"], row["gender"], row["timezone"], birthday)

    def save_profile(self, user_id: str, profile: ProducerProfile) -> None:
        birthday = profile.birthday
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO producer_profiles"
                " (user_id, form_of_address, gender, timezone, birthday_month, birthday_day,"
                " updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (user_id) DO UPDATE SET form_of_address = excluded.form_of_address,"
                " gender = excluded.gender, timezone = excluded.timezone,"
                " birthday_month = excluded.birthday_month, birthday_day = excluded.birthday_day,"
                " updated_at = excluded.updated_at",
                (
                    user_id,
                    profile.form_of_address,
                    profile.gender,
                    profile.timezone,
                    birthday and birthday.month,
                    birthday and birthday.day,
                    _now(),
                ),
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

    def latest_conversations(self, user_id: str) -> list[tuple[Conversation, Message | None]]:
        """Each character's newest conversation with the user, and its last message (None
        while it has none); for the conversation list."""
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM conversations WHERE user_id = ?"
                " ORDER BY created_at DESC, rowid DESC",
                (user_id,),
            ).fetchall()
            newest: dict[str, Conversation] = {}
            for row in rows:
                newest.setdefault(row["character_id"], Conversation(**row))
            last = {
                c.id: self._db.execute(
                    "SELECT id, role, text, ja, zh, segments, created_at FROM messages"
                    " WHERE conversation_id = ? ORDER BY id DESC LIMIT 1",
                    (c.id,),
                ).fetchone()
                for c in newest.values()
            }
        return [(c, _message(last[c.id]) if last[c.id] else None) for c in newest.values()]

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
        return [_message(row) for row in rows]

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


_USER_COLUMNS = "id, name, created_at, consented_at, banned_at, ban_note"

def _message(row: sqlite3.Row) -> Message:
    return Message(
        row["id"], row["role"], row["text"], row["ja"], row["zh"], row["created_at"],
        [Segment(**s) for s in json.loads(row["segments"] or "[]")],
    )


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()
