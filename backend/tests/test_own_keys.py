"""Whose keys a turn or call runs on, answered once, through the own keys module, from the
user's own keys it brings: theirs where it brought them, the deployer's otherwise, never
falling back from a key of theirs that does not work; and whether it counts towards the
user's limit, also before a call, from the services it will bring keys for."""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from eidolon.activity import OWN, ActivityLog
from eidolon.config import SttKey
from eidolon.llm import ChatLLM, ChatMessage
from eidolon.own_keys import (
    BroughtKeys,
    CallsUnavailable,
    DeployerKeys,
    OwnKeys,
    OwnLLMSettings,
    Service,
)
from eidolon.store import Store
from tests.fakes import (
    DEPLOYER_FISH_KEY,
    DEPLOYER_SONIOX_KEY,
    FakeBackgroundLLM,
    FakeClock,
    FakeLLM,
    FakeLLMService,
    FakeSpeech,
)


class Deployment:
    """A store with a user, and the deployer's keys."""

    def __init__(self, path: Path) -> None:
        self.store = Store(path)
        self.activity = ActivityLog(path, FakeClock())
        self.user = self.store.create_user("producer").id
        self.chat = FakeLLM()
        self.memory = FakeBackgroundLLM()
        self.llm_service = FakeLLMService()
        self.speech = FakeSpeech()

    def own_keys(
        self,
        secret_key: str | None = "test-secret-key",
        *,
        stt: SttKey | None = SttKey("soniox", DEPLOYER_SONIOX_KEY),
        tts: str | None = DEPLOYER_FISH_KEY,
    ) -> OwnKeys:
        return OwnKeys(
            self.store, secret_key, self.llm_service,
            DeployerKeys(self.chat, self.memory, stt, tts), self.activity, self.speech,
        )


MY_LLM = OwnLLMSettings("https://llm.example.com/v1", "sk-my-own-llm-cccc", "my-model")
MY_FISH = "fish-my-own-key-aaaa"
MY_SONIOX = SttKey("soniox", "soniox-my-own-key-bbbb")
MY_DASHSCOPE = SttKey("bailian", "sk-my-own-dashscope-dddd", "singapore")


def brought(*services: Service, stt: SttKey = MY_SONIOX) -> BroughtKeys:
    """The user's own keys for `services`, as a turn or call brings them."""
    return BroughtKeys(
        llm=MY_LLM if "llm" in services else None,
        tts=MY_FISH if "tts" in services else None,
        stt=stt if "stt" in services else None,
    )


async def keep(own_keys: OwnKeys, user_id: str, *services: Service, stt: SttKey = MY_SONIOX) -> None:
    """The user saves their own keys for `services`."""
    for service in services:
        if service == "llm":
            await own_keys.save_llm(user_id, MY_LLM)
        elif service == "tts":
            await own_keys.save_speech(user_id, "tts", MY_FISH)
        else:
            await own_keys.save_speech(user_id, "stt", stt.api_key, stt_provider=stt.provider)


async def ask(llm: ChatLLM) -> None:
    async for _ in llm.stream([ChatMessage("user", "在吗")]):
        pass


@pytest.fixture
def deployment(tmp_path: Path) -> Iterator[Deployment]:
    deployment = Deployment(tmp_path / "eidolon.db")
    deployment.speech.regions[MY_DASHSCOPE.api_key] = "singapore"
    yield deployment
    deployment.activity.close()
    deployment.store.close()


async def test_a_turn_that_brings_an_llm_runs_on_it_for_both_and_does_not_count(
    deployment: Deployment,
):
    deployment.llm_service.llm = FakeLLM(["好的"], ["好的"])

    keys = deployment.own_keys().for_turn(brought("llm"))
    await ask(keys.llms.chat)
    await ask(keys.llms.memory)

    assert deployment.llm_service.llm.keys == [MY_LLM.api_key, MY_LLM.api_key]
    assert deployment.chat.keys == []
    assert deployment.memory.prompts == []
    assert keys.exempt is True and keys.own_llm is True
    # Each request is recorded as a service call on their own key, never saying which
    # host or model theirs is.
    _, calls = deployment.activity.since(datetime.min.replace(tzinfo=UTC))
    assert sorted((c.service, c.provider, c.model, c.own_key) for c in calls) == [
        ("chat_llm", OWN, OWN, True),
        ("memory_llm", OWN, OWN, True),
    ]


async def test_a_turn_that_brings_nothing_runs_on_the_deployers_models(
    deployment: Deployment,
):
    keys = deployment.own_keys().for_turn(BroughtKeys())

    assert keys.llms.chat is deployment.chat
    assert keys.llms.memory is deployment.memory
    assert keys.own_llm is False


async def test_a_call_that_brings_speech_keys_hears_and_speaks_on_them_and_the_rest_on_the_deployers(
    deployment: Deployment,
):
    keys = deployment.own_keys().for_call(brought("tts"))

    assert (keys.stt, keys.tts) == (SttKey("soniox", DEPLOYER_SONIOX_KEY), MY_FISH)
    assert keys.own == {"tts"}
    assert keys.llms.chat is deployment.chat
    assert keys.llms.memory is deployment.memory
    assert keys.own_llm is False


async def test_a_call_that_brings_all_three_runs_on_them_alone(deployment: Deployment):
    deployment.llm_service.llm = FakeLLM(["好的"])

    keys = deployment.own_keys().for_call(brought("llm", "tts", "stt"))
    await ask(keys.llms.chat)

    assert (keys.stt, keys.tts, keys.own) == (MY_SONIOX, MY_FISH, {"stt", "tts"})
    assert keys.own_llm is True
    assert deployment.llm_service.llm.keys == [MY_LLM.api_key]
    assert deployment.chat.keys == []


@pytest.mark.parametrize(
    ("services", "turns", "calls"),
    [
        ((), False, False),
        (("llm",), True, False),
        (("tts", "stt"), False, False),
        (("llm", "tts"), True, False),
        (("llm", "tts", "stt"), True, True),
    ],
)
async def test_turns_bringing_an_own_llm_and_calls_bringing_all_three_do_not_count(
    deployment: Deployment, services: tuple[Service, ...], turns: bool, calls: bool
):
    own_keys = deployment.own_keys()

    assert own_keys.for_turn(brought(*services)).exempt is turns
    assert own_keys.for_call(brought(*services)).exempt is calls


@pytest.mark.parametrize(
    ("deployers", "mine"),
    [
        (SttKey("bailian", "deployer-dashscope-key", "beijing"), MY_SONIOX),
        (SttKey("soniox", DEPLOYER_SONIOX_KEY), MY_DASHSCOPE),
    ],
)
async def test_a_users_own_speech_recognition_is_the_service_they_chose_whichever_the_deployer_did(
    deployment: Deployment, deployers: SttKey, mine: SttKey
):
    own_keys = deployment.own_keys(stt=deployers)

    assert own_keys.for_call(brought("stt", stt=mine)).stt == mine
    assert own_keys.for_call(BroughtKeys()).stt == deployers


async def test_a_call_can_bring_a_key_for_what_the_deployer_has_none_for(
    deployment: Deployment,
):
    without_stt = deployment.own_keys(stt=None)
    without_tts = deployment.own_keys(tts=None)

    assert without_stt.for_call(brought("stt")).stt == MY_SONIOX
    with pytest.raises(CallsUnavailable):
        without_stt.for_call(BroughtKeys())
    with pytest.raises(CallsUnavailable):
        without_tts.for_call(brought("stt"))


async def test_a_speech_recognition_key_kept_before_there_was_a_choice_is_sonioxs(
    deployment: Deployment, tmp_path: Path
):
    await keep(deployment.own_keys(), deployment.user, "stt")
    deployment.store.close()
    with sqlite3.connect(tmp_path / "eidolon.db") as db:  # as kept before: no provider, no region
        db.executescript("""
            CREATE TABLE before AS SELECT user_id, service, secret, last4, base_url, model,
                protocol, updated_at FROM own_keys;
            DROP TABLE own_keys;
            ALTER TABLE before RENAME TO own_keys;
        """)
    db.close()
    deployment.store = Store(tmp_path / "eidolon.db")

    own_keys = deployment.own_keys(stt=SttKey("bailian", "deployer-dashscope-key", "beijing"))

    assert own_keys.describe(deployment.user)["stt"] == {"last4": "bbbb", "provider": "soniox"}


async def test_without_a_secret_key_the_keys_users_kept_exempt_nothing(
    deployment: Deployment,
):
    await keep(deployment.own_keys(), deployment.user, "llm", "tts", "stt")
    without = deployment.own_keys(secret_key=None)

    assert deployment.own_keys().exemptions(deployment.user) == {"turns": True, "calls": True}
    assert without.exemptions(deployment.user) == {"turns": False, "calls": False}


@pytest.mark.parametrize(
    ("services", "exempt"),
    [((), False), (("llm", "tts"), False), (("llm", "tts", "stt"), True)],
)
async def test_asking_before_a_call_says_whether_bringing_keys_for_some_services_would_count(
    deployment: Deployment, services: tuple[Service, ...], exempt: bool
):
    assert deployment.own_keys().call_exempt(services) is exempt


async def test_asking_before_a_call_needs_keys_for_speech_from_the_user_or_the_deployer(
    deployment: Deployment,
):
    without_stt = deployment.own_keys(stt=None)

    assert without_stt.call_exempt(("stt",)) is False
    with pytest.raises(CallsUnavailable):
        without_stt.call_exempt(("llm", "tts"))
