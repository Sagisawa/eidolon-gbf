"""How a call turns out: whether it counts towards the user's limit, whether it is given
back, and the one `ended` message the browser is told why with (CONTEXT.md「限额」「接通」).

The call is only its events here, reported as `_LiveCall` and `CallTurns` would; the
limiter is the real one, on a fresh database, allowing one call an hour. Neither Pipecat
nor aiortc is needed for any of it.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from eidolon.call_outcome import CallOutcome
from eidolon.config import UsageLimits
from eidolon.own_keys import OwnKeyFailed
from eidolon.store import Store
from eidolon.usage import OverLimit, UsageLimiter

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


class Limiter:
    """A user allowed one call an hour, and the limiter counting them."""

    def __init__(self, path: Path) -> None:
        self._store = Store(path)
        self.user = self._store.create_user("producer").id
        self.usage = UsageLimiter(path, UsageLimits(calls_per_hour=1), lambda: NOW)

    def call(self, exempt: bool = False) -> CallOutcome:
        return CallOutcome(self.usage, self.user, exempt)

    def counted(self) -> bool:
        """Whether this hour's call is used up, that is, the last one was not given back."""
        try:
            self.usage.take(self.user, "call").give_back()
        except OverLimit:
            return True
        return False

    def calls_recorded(self) -> int:
        return self.usage.last_day(self.user).total.calls

    def close(self) -> None:
        self.usage.close()
        self._store.close()


@pytest.fixture
def limiter(tmp_path: Path) -> Iterator[Limiter]:
    limiter = Limiter(tmp_path / "eidolon.db")
    yield limiter
    limiter.close()


def test_a_call_over_the_limit_is_refused(limiter: Limiter):
    limiter.call()

    with pytest.raises(OverLimit):
        limiter.call()


def test_an_exempt_call_is_taken_even_over_the_limit(limiter: Limiter):
    limiter.call()

    limiter.call(exempt=True)

    assert limiter.calls_recorded() == 2


def test_a_call_that_could_not_be_set_up_is_given_back_saying_nothing(limiter: Limiter):
    outcome = limiter.call()

    assert outcome.set_up_failed() is None
    assert not limiter.counted()


def test_a_call_that_ends_before_connecting_is_given_back(limiter: Limiter):
    outcome = limiter.call()

    outcome.settle()

    assert not limiter.counted()


def test_a_service_failing_before_the_call_connects_says_nothing_and_it_is_given_back(
    limiter: Limiter,
):
    outcome = limiter.call()

    assert outcome.service_failed(None) is None
    assert outcome.service_failed("tts") is None
    outcome.settle()

    assert not limiter.counted()


def test_the_deployers_service_failing_before_any_turn_is_not_connecting(limiter: Limiter):
    outcome = limiter.call()
    outcome.connected()

    message = outcome.service_failed(None)
    outcome.settle()

    assert message == {
        "type": "ended",
        "reason": "not_connected",
        "message": "语音服务出了故障，通话没能接通",
        "counts": False,
    }
    assert not limiter.counted()


def test_an_own_key_failing_before_any_turn_says_which_and_the_call_is_given_back(
    limiter: Limiter,
):
    outcome = limiter.call()
    outcome.connected()

    message = outcome.service_failed("stt")
    outcome.settle()

    assert message == {
        "type": "ended",
        "reason": "own_key",
        "message": OwnKeyFailed("stt", "通话已结束").message,
        "counts": False,
    }
    assert not limiter.counted()


@pytest.mark.parametrize("exempt", [False, True])
def test_a_service_failing_after_a_turn_ends_a_call_that_was_connected(
    limiter: Limiter, exempt: bool
):
    outcome = limiter.call(exempt)
    outcome.connected()
    outcome.turn_recorded()

    message = outcome.service_failed(None)
    outcome.settle()

    assert message == {
        "type": "ended",
        "reason": "dropped",
        "message": "语音服务出了故障，通话中断了",
        "counts": not exempt,
    }
    assert limiter.counted() is not exempt
    assert limiter.calls_recorded() == 1  # kept, for the admin to see, even when exempt


@pytest.mark.parametrize("exempt", [False, True])
def test_an_own_key_failing_after_a_turn_ends_a_call_that_was_connected(
    limiter: Limiter, exempt: bool
):
    outcome = limiter.call(exempt)
    outcome.connected()
    outcome.turn_recorded()

    message = outcome.service_failed("tts")
    outcome.settle()

    assert message is not None
    assert (message["reason"], message["counts"]) == ("own_key", not exempt)
    assert message["message"] == OwnKeyFailed("tts", "通话已结束").message
    assert limiter.calls_recorded() == 1


@pytest.mark.parametrize("reason", ["duration_limit", "turn_limit"])
@pytest.mark.parametrize("exempt", [False, True])
def test_a_call_that_reaches_its_limits_is_kept(limiter: Limiter, reason, exempt: bool):
    outcome = limiter.call(exempt)
    outcome.connected()
    outcome.turn_recorded()

    message = outcome.limit_reached(reason, "这次通话已经说了 1 轮了")
    outcome.settle()

    assert message == {
        "type": "ended",
        "reason": reason,
        "message": "这次通话已经说了 1 轮了，先挂断啦。想接着聊可以重新拨打。",
        "counts": not exempt,
    }
    assert limiter.counted() is not exempt
    assert limiter.calls_recorded() == 1


def test_a_call_that_reaches_its_time_before_any_turn_is_kept(limiter: Limiter):
    outcome = limiter.call()
    outcome.connected()

    message = outcome.limit_reached("duration_limit", "这次通话已经满 10 分钟了")
    outcome.settle()

    assert message is not None and message["counts"] is True
    assert limiter.counted()


@pytest.mark.parametrize("turns", [0, 1])
def test_a_call_hung_up_once_connected_counts(limiter: Limiter, turns: int):
    outcome = limiter.call()
    outcome.connected()
    for _ in range(turns):
        outcome.turn_recorded()

    outcome.settle()

    assert limiter.counted()


def test_the_browser_is_told_why_only_once(limiter: Limiter):
    outcome = limiter.call()
    outcome.connected()
    outcome.turn_recorded()

    first = outcome.limit_reached("turn_limit", "这次通话已经说了 1 轮了")

    assert first is not None
    assert outcome.service_failed(None) is None
    assert outcome.service_failed("stt") is None
    assert outcome.limit_reached("duration_limit", "这次通话已经满 10 分钟了") is None


def test_what_the_browser_was_told_is_how_the_call_is_settled(limiter: Limiter):
    """A turn recorded after the call was told it never connected does not make it count."""
    outcome = limiter.call()
    outcome.connected()
    told = outcome.service_failed(None)
    outcome.turn_recorded()

    outcome.settle()

    assert told is not None and told["counts"] is False
    assert not limiter.counted()


def test_settling_twice_gives_back_once(limiter: Limiter):
    outcome = limiter.call()
    outcome.settle()
    other = limiter.call()  # the call given back is taken again

    outcome.settle()

    assert limiter.counted()
    other.settle()  # never connected: given back
    assert not limiter.counted()
