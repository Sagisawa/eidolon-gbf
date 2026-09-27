"""Per-user rate limits, so one user cannot use up the API credit everyone shares."""

from datetime import datetime, timedelta

from eidolon.clock import Clock
from eidolon.config import UsageLimits
from eidolon.store import LimitReached, Store, UsageKind

WINDOW = timedelta(hours=1)

_NAMES: dict[UsageKind, str] = {"turn": "文字对话", "call": "语音通话"}


class OverLimit(Exception):
    """The user has used up this hour's `kind`; they can go on at `retry_at`."""

    def __init__(self, kind: UsageKind, limit: int, retry_at: datetime, now: datetime) -> None:
        super().__init__(f"这一小时的{_NAMES[kind]}次数已经用完了（每小时 {limit} 次）")
        self.retry_at = retry_at
        self.now = now


class Use:
    """One counted text turn or call; given back when it fails, so the user keeps it."""

    def __init__(self, store: Store | None = None, use_id: int | None = None) -> None:
        self._store = store
        self._id = use_id

    def give_back(self) -> None:
        if self._store is not None and self._id is not None:
            self._store.give_back_usage(self._id)
            self._id = None


class UsageLimiter:
    """Counts each user's text turns and voice calls over the last hour, whichever device
    or sign-in method they come with."""

    def __init__(self, store: Store, limits: UsageLimits, clock: Clock) -> None:
        self._store = store
        self._limits: dict[UsageKind, int | None] = {
            "turn": limits.turns_per_hour,
            "call": limits.calls_per_hour,
        }
        self._clock = clock

    def take(self, user_id: str, kind: UsageKind) -> Use:
        """Count one `kind` against the user's limit; raises OverLimit, counting nothing,
        when they have none left this hour."""
        limit = self._limits[kind]
        if limit is None:
            return Use()
        now = self._clock()
        try:
            return Use(self._store, self._store.take_usage(user_id, kind, now, WINDOW, limit))
        except LimitReached as e:
            raise OverLimit(kind, limit, e.retry_at, now) from None
