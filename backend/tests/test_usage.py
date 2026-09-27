"""The usage limit module: each user's text turns and calls over the last hour, counted
against their limits unless on their own keys, given back when they fail, and kept a day
for the admin to look over."""

import sqlite3
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest

from eidolon.config import UsageLimits
from eidolon.store import Store
from eidolon.usage import OverLimit, Tally, UsageLimiter
from tests.fakes import START, FakeClock


class Deployment:
    """A database with two users, and a clock the tests move."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.store = Store(path)
        self.user = self.store.create_user("producer").id
        self.friend = self.store.create_user("friend").id
        self.clock = FakeClock()

    def limiter(self, turns: int | None = 2, calls: int | None = 1) -> UsageLimiter:
        limits = UsageLimits(turns_per_hour=turns, calls_per_hour=calls)
        return UsageLimiter(self.path, limits, self.clock)


@pytest.fixture
def deployment(tmp_path: Path) -> Iterator[Deployment]:
    deployment = Deployment(tmp_path / "eidolon.db")
    yield deployment
    deployment.store.close()


@pytest.fixture
def usage(deployment: Deployment) -> Iterator[UsageLimiter]:
    usage = deployment.limiter()
    yield usage
    usage.close()


def test_uses_over_the_hourly_limit_are_refused_until_the_oldest_ages_out(
    deployment: Deployment, usage: UsageLimiter
):
    usage.take(deployment.user, "turn")
    deployment.clock.advance(minutes=20)
    usage.take(deployment.user, "turn")
    deployment.clock.advance(minutes=10)

    with pytest.raises(OverLimit) as refused:
        usage.take(deployment.user, "turn")

    assert refused.value.retry_at == START + timedelta(hours=1)
    assert refused.value.now == START + timedelta(minutes=30)
    assert "文字对话" in str(refused.value) and "每小时 2 次" in str(refused.value)
    deployment.clock.advance(minutes=30)
    usage.take(deployment.user, "turn")


def test_the_last_day_is_tallied_by_hour_with_what_was_on_own_keys(
    deployment: Deployment, usage: UsageLimiter
):
    deployment.clock.advance(minutes=10)  # 12:10
    usage.take(deployment.user, "turn")
    usage.take(deployment.user, "turn", exempt=True)
    usage.take(deployment.friend, "turn")
    deployment.clock.advance(hours=2)  # 14:10
    usage.take(deployment.user, "call", exempt=True)
    usage.take(deployment.user, "turn")

    day = usage.last_day(deployment.user)

    hour = START.replace(minute=0)
    assert day.hours == {
        hour: Tally(turns=2, exempt_turns=1),
        hour + timedelta(hours=2): Tally(turns=1, calls=1, exempt_calls=1),
    }
    assert day.total == Tally(turns=3, calls=1, exempt_turns=1, exempt_calls=1)


def test_uses_on_own_keys_are_recorded_but_do_not_count(
    deployment: Deployment, usage: UsageLimiter
):
    for _ in range(2):
        usage.take(deployment.user, "call", exempt=True)

    usage.take(deployment.user, "call")  # the limit of 1 is still all there
    usage.take(deployment.user, "call", exempt=True)  # and even once it is used up

    with pytest.raises(OverLimit):
        usage.take(deployment.user, "call")
    assert usage.last_day(deployment.user).total == Tally(calls=4, exempt_calls=3)


def test_each_user_and_each_kind_has_a_limit_of_its_own(
    deployment: Deployment, usage: UsageLimiter
):
    usage.take(deployment.user, "call")

    usage.take(deployment.friend, "call")
    usage.take(deployment.user, "turn")

    with pytest.raises(OverLimit) as refused:
        usage.take(deployment.user, "call")
    assert "语音通话" in str(refused.value)


def test_a_limit_of_none_lets_everything_through(deployment: Deployment):
    usage = deployment.limiter(turns=None)
    try:
        for _ in range(100):
            usage.take(deployment.user, "turn")
    finally:
        usage.close()


def test_a_use_given_back_is_as_if_never_taken(deployment: Deployment, usage: UsageLimiter):
    usage.take(deployment.user, "call").give_back()
    use = usage.take(deployment.user, "call")

    use.give_back()
    use.give_back()  # once is enough
    usage.take(deployment.user, "call")

    assert usage.last_day(deployment.user).total == Tally(calls=1)


def test_uses_are_kept_a_day(deployment: Deployment, usage: UsageLimiter):
    usage.take(deployment.user, "turn", exempt=True)
    deployment.clock.advance(hours=23)
    usage.take(deployment.user, "turn", exempt=True)

    deployment.clock.advance(hours=1)
    usage.take(deployment.user, "call", exempt=True)

    assert usage.last_day(deployment.user).total == Tally(turns=1, calls=1, exempt_turns=1,
                                                         exempt_calls=1)


def test_uses_kept_before_own_keys_existed_still_count(deployment: Deployment):
    with sqlite3.connect(deployment.path) as db:  # a database from before own keys
        db.execute("CREATE TABLE usage (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                   " user_id TEXT NOT NULL, kind TEXT NOT NULL, at REAL NOT NULL)")
        db.execute("INSERT INTO usage (user_id, kind, at) VALUES (?, 'call', ?)",
                   (deployment.user, START.timestamp()))
    db.close()
    usage = deployment.limiter()
    try:
        with pytest.raises(OverLimit):
            usage.take(deployment.user, "call")
        usage.take(deployment.user, "call", exempt=True)
        assert usage.last_day(deployment.user).total == Tally(calls=2, exempt_calls=1)
    finally:
        usage.close()
