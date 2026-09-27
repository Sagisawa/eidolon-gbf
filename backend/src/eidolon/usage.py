"""Per-user rate limits, so one user cannot use up the API credit everyone shares.

A turn or call on the user's own keys alone is recorded all the same, for the admin to
see, but does not count towards the limit."""

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

    def take(self, user_id: str, kind: UsageKind, exempt: bool = False) -> Use:
        """Record one `kind` by the user, counting it against their limit unless it is
        `exempt`; raises OverLimit, recording nothing, when they have none left this hour."""
        limit = self._limits[kind]
        now = self._clock()
        try:
            use_id = self._store.take_usage(user_id, kind, now, WINDOW, limit, exempt)
        except LimitReached as e:
            assert limit is not None
            raise OverLimit(kind, limit, e.retry_at, now) from None
        return Use(self._store, use_id)
