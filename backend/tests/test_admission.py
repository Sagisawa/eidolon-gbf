"""Letting a turn begin and settling it once it is over, through `Admissions` alone:
whose keys it runs on, its activity record, its use of the limit and the deployer's
lease, each of them looked at as the admin and the limiter see them.

All of it is real, on a fresh database, but the deployer, which counts its leases; the
user is allowed one turn an hour.
"""

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest

from eidolon.activity import ActivityLog, Result
from eidolon.admission import Admissions
from eidolon.config import LLMSettings, UsageLimits
from eidolon.own_keys import DeployerKeys, DeployerLease, OwnKeyFailed, OwnKeys, OwnLLMSettings
from eidolon.store import Store
from eidolon.usage import OverLimit, UsageLimiter
from tests.fakes import FakeBackgroundLLM, FakeClock, FakeLLM, FakeLLMService

SECRET = "test-secret-key"
MY_LLM = OwnLLMSettings("https://llm.example.com/v1", "sk-my-own-llm-cccc", "my-model")
CHAT = LLMSettings("https://chat.example.com/v1", "deployer-chat", "chat-model")
MEMORY = LLMSettings("https://memory.example.com/v1", "deployer-memory", "memory-model")


class CountingDeployer:
    """The deployer's keys, counting how many times they were leased and let go."""

    def __init__(self) -> None:
        self.keys = DeployerKeys(FakeLLM(), FakeBackgroundLLM())
        self.leased = 0
        self.released = 0

    def lease(self) -> DeployerLease:
        self.leased += 1
        return DeployerLease(self.keys, self._release)

    def _release(self) -> None:
        self.released += 1


class Deployment:
    """A user allowed one turn an hour, and everything letting their turns begin."""

    def __init__(self, path: Path) -> None:
        self.clock = FakeClock()
        self.store = Store(path)
        self.user = self.store.create_user("producer").id
        self.usage = UsageLimiter(path, UsageLimits(turns_per_hour=1), self.clock)
        self.activity = ActivityLog(path, self.clock)
        self.deployer = CountingDeployer()
        self.llm_service = FakeLLMService()
        self.deployer_models_broken = False
        self.secret = SECRET

    def admissions(self) -> Admissions:
        return Admissions(self.usage, self.activity, self.own_keys(), self._deployer_models)

    def own_keys(self) -> OwnKeys:
        return OwnKeys(self.store, self.secret, self.llm_service, self.deployer)

    def _deployer_models(self) -> tuple[LLMSettings, LLMSettings]:
        if self.deployer_models_broken:
            raise RuntimeError("the live configuration could not be read")
        return CHAT, MEMORY

    async def bring_llm(self) -> None:
        await self.own_keys().save_llm(self.user, MY_LLM)

    def counted(self) -> bool:
        """Whether this hour's turn is used up, that is, the last one counted."""
        try:
            self.usage.take(self.user, "turn").give_back()
        except OverLimit:
            return True
        return False

    def turns_taken(self) -> int:
        """Uses of the limit kept for the admin, counting or not."""
        return self.usage.last_day(self.user).total.turns

    def records(self) -> list[tuple[Result, bool]]:
        """Each of the user's records: how it turned out, and whether on their own keys."""
        return [
            (r.result, r.own_keys)
            for r in self.activity.of_user(self.user, self.clock() - timedelta(hours=1))
        ]

    def close(self) -> None:
        self.activity.close()
        self.usage.close()
        self.store.close()


@pytest.fixture
def deployment(tmp_path: Path) -> Iterator[Deployment]:
    deployment = Deployment(tmp_path / "eidolon.db")
    yield deployment
    deployment.close()


@pytest.mark.parametrize(
    ("result", "counted"),
    [("success", True), ("failed", False), ("rejected", False), ("left", True)],
)
def test_a_turn_counts_when_it_succeeded_or_was_left_and_is_given_back_otherwise(
    deployment: Deployment, result: Result, counted: bool
):
    admission = deployment.admissions().turn(deployment.user, "mano")

    admission.settle(result)

    assert deployment.counted() is counted
    assert admission.counts(result) is counted
    assert deployment.records() == [(result, False)]
    assert deployment.deployer.released == 1


def test_a_turn_over_the_limit_is_refused_recorded_rejected_and_lets_go_of_its_lease(
    deployment: Deployment,
):
    admissions = deployment.admissions()
    admissions.turn(deployment.user, "mano").settle("success")

    with pytest.raises(OverLimit):
        admissions.turn(deployment.user, "mano")

    assert deployment.turns_taken() == 1
    assert deployment.records() == [("success", False), ("rejected", False)]
    assert deployment.deployer.released == 2


async def test_a_turn_on_an_own_key_that_no_longer_decrypts_is_recorded_failed_and_takes_no_use(
    deployment: Deployment,
):
    await deployment.bring_llm()
    deployment.secret = "a-changed-secret-key"

    with pytest.raises(OwnKeyFailed):
        deployment.admissions().turn(deployment.user, "mano")

    assert deployment.turns_taken() == 0
    assert deployment.records() == [("failed", True)]
    assert deployment.deployer.leased == deployment.deployer.released == 0


async def test_a_turn_on_an_own_llm_does_not_count_and_leases_nothing(deployment: Deployment):
    await deployment.bring_llm()
    admissions = deployment.admissions()

    for _ in range(2):  # over the limit, were they counted
        admission = admissions.turn(deployment.user, "mano")
        assert admission.exempt
        assert not any(admission.counts(r) for r in ("success", "failed", "rejected", "left"))
        admission.settle("success")

    assert not deployment.counted()
    assert deployment.turns_taken() == 2  # kept for the admin all the same
    assert deployment.records() == [("success", True), ("success", True)]
    assert deployment.deployer.leased == 0


def test_a_turn_settled_twice_is_settled_once(deployment: Deployment):
    admission = deployment.admissions().turn(deployment.user, "mano")

    admission.settle("failed")
    admission.settle("success")

    assert not deployment.counted()
    assert deployment.records() == [("failed", False)]
    assert deployment.deployer.released == 1


def test_a_turn_failing_as_it_is_prepared_is_recorded_failed_takes_no_use_and_lets_go(
    deployment: Deployment,
):
    deployment.deployer_models_broken = True

    with pytest.raises(RuntimeError):
        deployment.admissions().turn(deployment.user, "mano")

    assert deployment.turns_taken() == 0
    assert deployment.records() == [("failed", False)]
    assert deployment.deployer.released == 1
