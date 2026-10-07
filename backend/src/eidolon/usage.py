"""Per-user rate limits, so one user cannot use up the API credit everyone shares.

A turn or call on the user's own keys alone is recorded all the same, for the admin to
see, but does not count towards the limit. Each use is kept in the database, next to the
user it belongs to, for a day; whoever's they are, uses older than that are deleted
whenever anyone takes one."""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from eidolon.clock import Clock
from eidolon.config import UsageLimits
from eidolon.database import connect

UsageKind = Literal["turn", "call"]

WINDOW = timedelta(hours=1)

KEPT = timedelta(hours=24)
"""How long each use is kept: an hour for the limits, a day for the admin to look over."""

_NAMES: dict[UsageKind, str] = {"turn": "文字对话", "call": "语音通话"}

_SCHEMA = """
-- `at` is epoch seconds rather than ISO text, so that the window is a plain range query.
-- A use on the user's own keys alone is `exempt`: recorded, but not limited.
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL,
    at REAL NOT NULL,
    exempt INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS usage_by_user ON usage(user_id, kind, at);
-- For forgetting everyone's uses once they are older than `KEPT`.
CREATE INDEX IF NOT EXISTS usage_by_time ON usage(at);
"""


class OverLimit(Exception):
    """The user has used up this hour's `kind`; they can go on at `retry_at`."""

    def __init__(self, kind: UsageKind, limit: int, retry_at: datetime, now: datetime) -> None:
        super().__init__(f"这一小时的{_NAMES[kind]}次数已经用完了（每小时 {limit} 次）")
        self.retry_at = retry_at
        self.now = now


@dataclass(frozen=True)
class Tally:
    """How many text turns and calls, and how many of each were on the user's own keys."""

    turns: int = 0
    calls: int = 0
    exempt_turns: int = 0
    exempt_calls: int = 0


@dataclass(frozen=True)
class DayOfUse:
    """A user's uses in the last day: each UTC hour that has any, oldest first, and all."""

    hours: dict[datetime, Tally]
    total: Tally


class Use:
    """One counted text turn or call; given back when it fails, so the user keeps it."""

    def __init__(self, limiter: "UsageLimiter", use_id: int) -> None:
        self._limiter = limiter
        self._id: int | None = use_id

    def give_back(self) -> None:
        if self._id is not None:
            self._limiter._give_back(self._id)
            self._id = None


class UsageLimiter:
    """Counts each user's text turns and voice calls over the last hour, whichever device
    or sign-in method they come with."""

    def __init__(
        self, path: Path, limits: UsageLimits | Callable[[], UsageLimits], clock: Clock
    ) -> None:
        """Uses kept in the database at `path`, next to the users they belong to, limited
        by `limits`, or by what it says as each use is taken (the live configuration's)."""
        # What is given back or forgotten is overwritten, not just freed (see `database`).
        self._db = connect(path)
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.executescript(_SCHEMA)
            columns = {name for _, name, *_ in self._db.execute("PRAGMA table_info(usage)")}
            if "exempt" not in columns:
                self._db.execute("ALTER TABLE usage ADD COLUMN exempt INTEGER NOT NULL DEFAULT 0")
        self._limits = limits if callable(limits) else lambda: limits
        self._clock = clock

    @property
    def limits(self) -> UsageLimits:
        """The limits in effect now."""
        return self._limits()

    def take(self, user_id: str, kind: UsageKind, exempt: bool = False) -> Use:
        """Record one `kind` by the user, counting it against their limit unless it is
        `exempt`; raises OverLimit, recording nothing, when they have none left this hour,
        that is, when the last hour already holds as many counting uses as the limit."""
        limits = self._limits()
        limit = limits.turns_per_hour if kind == "turn" else limits.calls_per_hour
        now = self._clock()
        with self._lock, self._db:
            # Everyone's, so that a user who does not come back leaves none behind.
            self._db.execute("DELETE FROM usage WHERE at <= ?", ((now - KEPT).timestamp(),))
            if limit is not None and not exempt:
                recent = [
                    at
                    for (at,) in self._db.execute(
                        "SELECT at FROM usage WHERE user_id = ? AND kind = ? AND NOT exempt"
                        " AND at > ? ORDER BY at",
                        (user_id, kind, (now - WINDOW).timestamp()),
                    )
                ]
                if len(recent) >= limit:
                    blocking = recent[len(recent) - limit]  # this one must age out first
                    retry_at = datetime.fromtimestamp(blocking, UTC) + WINDOW
                    raise OverLimit(kind, limit, retry_at, now)
            cursor = self._db.execute(
                "INSERT INTO usage (user_id, kind, at, exempt) VALUES (?, ?, ?, ?)",
                (user_id, kind, now.timestamp(), int(exempt)),
            )
        assert cursor.lastrowid is not None
        return Use(self, cursor.lastrowid)

    def last_day(self, user_id: str) -> DayOfUse:
        """The user's uses in the last day, by hour, for the admin to look over."""
        with self._lock:
            rows = self._db.execute(
                "SELECT kind, at, exempt FROM usage WHERE user_id = ? AND at >= ? ORDER BY at",
                (user_id, (self._clock() - KEPT).timestamp()),
            ).fetchall()
        hours: dict[datetime, list[tuple[UsageKind, bool]]] = {}
        for kind, at, exempt in rows:
            hour = datetime.fromtimestamp(at, UTC).replace(minute=0, second=0, microsecond=0)
            hours.setdefault(hour, []).append((kind, bool(exempt)))
        return DayOfUse(
            {hour: _tally(uses) for hour, uses in hours.items()},
            _tally([use for uses in hours.values() for use in uses]),
        )

    def close(self) -> None:
        self._db.close()

    def _give_back(self, use_id: int) -> None:
        """Forget a use, as if it had never been taken."""
        with self._lock, self._db:
            self._db.execute("DELETE FROM usage WHERE id = ?", (use_id,))


def _tally(uses: list[tuple[UsageKind, bool]]) -> Tally:
    return Tally(
        turns=sum(kind == "turn" for kind, _ in uses),
        calls=sum(kind == "call" for kind, _ in uses),
        exempt_turns=sum(kind == "turn" and exempt for kind, exempt in uses),
        exempt_calls=sum(kind == "call" and exempt for kind, exempt in uses),
    )
