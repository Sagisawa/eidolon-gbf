"""Per-user rate limits, so one user cannot use up the API credit everyone shares."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from eidolon.config import UsageLimits
from eidolon.engine import Clock
from eidolon.store import Store

Kind = Literal["turn", "call"]

WINDOW = timedelta(hours=1)

_NAMES: dict[Kind, str] = {"turn": "文字对话", "call": "语音通话"}


@dataclass
class OverLimit(Exception):
    """The user has used up this hour's `kind`; they can go on at `retry_at`."""

    kind: Kind
    limit: int
    retry_at: datetime
    now: datetime

    @property
    def message(self) -> str:
        return f"这一小时的{_NAMES[self.kind]}次数已经用完了（每小时 {self.limit} 次）"


class UsageLimiter:
    """Counts each user's text turns and voice calls over the last hour, whichever of their
    access keys they come with."""

    def __init__(self, store: Store, limits: UsageLimits, clock: Clock) -> None:
        self._store = store
        self._limits = {"turn": limits.turns_per_hour, "call": limits.calls_per_hour}
        self._clock = clock

    def take(self, user_id: str, kind: Kind) -> None:
        """Count one `kind` against the user's limit; raises OverLimit, counting nothing,
        when they have none left this hour."""
        limit = self._limits[kind]
        if limit is None:
            return
        now = self._clock()
        retry_at = self._store.take_usage(user_id, kind, now, WINDOW, limit)
        if retry_at is not None:
            raise OverLimit(kind, limit, retry_at, now)
