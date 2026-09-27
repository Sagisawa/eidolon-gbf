"""Whose keys a turn or call runs on, answered once, through the own keys module: the
user's own where they brought them, the deployer's otherwise, never falling back from a
key of theirs that no longer works; and whether it counts towards the user's limit."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from eidolon.llm import ChatLLM, ChatMessage
from eidolon.own_keys import (
    CallsUnavailable,
    DeployerKeys,
    OwnKeyFailed,
    OwnKeys,
    OwnLLMSettings,
)
from eidolon.store import Store
from tests.fakes import (
    DEPLOYER_FISH_KEY,
    DEPLOYER_SONIOX_KEY,
    FakeBackgroundLLM,
    FakeLLM,
    FakeLLMService,
    FakeSpeech,
)


class Deployment:
    """A store with a user, and the deployer's keys."""

    def __init__(self, path: Path) -> None:
        self.store = Store(path)
        self.user = self.store.create_user("producer").id
        self.chat = FakeLLM()
        self.memory = FakeBackgroundLLM()
        self.llm_service = FakeLLMService()
        self.speech = FakeSpeech()

    def own_keys(
        self,
        secret_key: str | None = "test-secret-key",
        *,
        stt: str | None = DEPLOYER_SONIOX_KEY,
        tts: str | None = DEPLOYER_FISH_KEY,
    ) -> OwnKeys:
        return OwnKeys(
            self.store, secret_key, self.llm_service,
            DeployerKeys(self.chat, self.memory, stt, tts), self.speech,
        )


MY_LLM = OwnLLMSettings("https://llm.example.com/v1", "sk-my-own-llm-cccc", "my-model")
MY_FISH = "fish-my-own-key-aaaa"
MY_SONIOX = "soniox-my-own-key-bbbb"


async def bring(own_keys: OwnKeys, user_id: str, *services: str) -> None:
    for service in services:
        if service == "llm":
            await own_keys.save_llm(user_id, MY_LLM)
        else:
            await own_keys.save_speech(
                user_id, service, MY_FISH if service == "tts" else MY_SONIOX  # pyright: ignore[reportArgumentType]
            )


async def ask(llm: ChatLLM) -> None:
    async for _ in llm.stream([ChatMessage("user", "在吗")]):
        pass


@pytest.fixture
def deployment(tmp_path: Path) -> Iterator[Deployment]:
    deployment = Deployment(tmp_path / "eidolon.db")
    yield deployment
    deployment.store.close()


def test_a_user_who_brought_nothing_takes_turns_on_the_deployers_llms_and_they_count(
    deployment: Deployment,
):
    keys = deployment.own_keys().for_turn(deployment.user)

    assert keys.llms.chat is deployment.chat
    assert keys.llms.memory is deployment.memory
    assert keys.exempt is False


async def test_a_user_who_brought_an_llm_takes_turns_on_it_for_both_and_they_do_not_count(
    deployment: Deployment,
):
    own_keys = deployment.own_keys()
    await bring(own_keys, deployment.user, "llm")
    deployment.llm_service.llm = FakeLLM(["好的"], ["好的"])

    keys = own_keys.for_turn(deployment.user)
    await ask(keys.llms.chat)
    await ask(keys.llms.memory)

    assert deployment.llm_service.llm.keys == [MY_LLM.api_key, MY_LLM.api_key]
    assert deployment.chat.keys == []
    assert deployment.memory.prompts == []
    assert keys.exempt is True


async def test_an_own_llm_that_can_no_longer_be_decrypted_fails_the_turn_before_it_starts(
    deployment: Deployment,
):
    await bring(deployment.own_keys(), deployment.user, "llm")
    changed = deployment.own_keys(secret_key="another-secret-key")  # EIDOLON_SECRET_KEY changed

    with pytest.raises(OwnKeyFailed) as failed:
        changed.for_turn(deployment.user)

    assert failed.value.service == "llm"
    assert "保存的密钥无法解密" in failed.value.message


async def test_a_call_hears_and_speaks_on_the_users_own_speech_keys_and_the_deployers_otherwise(
    deployment: Deployment,
):
    own_keys = deployment.own_keys()
    await bring(own_keys, deployment.user, "tts")

    keys = own_keys.for_call(deployment.user)

    assert (keys.stt, keys.tts) == (DEPLOYER_SONIOX_KEY, MY_FISH)
    assert keys.own == {"tts"}
    assert keys.llms.chat is deployment.chat
    assert keys.llms.memory is deployment.memory


@pytest.mark.parametrize(
    ("brought", "turns", "calls"),
    [
        ((), False, False),
        (("llm",), True, False),
        (("tts", "stt"), False, False),
        (("llm", "tts"), True, False),
        (("llm", "tts", "stt"), True, True),
    ],
)
async def test_turns_on_an_own_llm_and_calls_on_all_three_own_keys_do_not_count(
    deployment: Deployment, brought: tuple[str, ...], turns: bool, calls: bool
):
    own_keys = deployment.own_keys()
    await bring(own_keys, deployment.user, *brought)

    assert own_keys.for_turn(deployment.user).exempt is turns
    assert own_keys.for_call(deployment.user).exempt is calls
    assert own_keys.exemptions(deployment.user) == {"turns": turns, "calls": calls}


async def test_a_user_can_call_on_their_own_key_for_what_the_deployer_has_none_for(
    deployment: Deployment,
):
    await bring(deployment.own_keys(), deployment.user, "stt")
    without_stt = deployment.own_keys(stt=None)
    without_tts = deployment.own_keys(tts=None)

    assert without_stt.for_call(deployment.user).stt == MY_SONIOX
    with pytest.raises(CallsUnavailable):
        without_tts.for_call(deployment.user)


async def test_an_own_speech_key_that_can_no_longer_be_decrypted_fails_the_call_before_it_starts(
    deployment: Deployment,
):
    await bring(deployment.own_keys(), deployment.user, "tts")
    changed = deployment.own_keys(secret_key="another-secret-key")

    with pytest.raises(OwnKeyFailed) as failed:
        changed.for_call(deployment.user)

    assert failed.value.service == "tts"
    assert "保存的密钥无法解密" in failed.value.message


async def test_without_a_secret_key_the_keys_users_brought_are_left_unused_and_all_counts(
    deployment: Deployment,
):
    await bring(deployment.own_keys(), deployment.user, "llm", "tts", "stt")
    without = deployment.own_keys(secret_key=None)

    turn, call = without.for_turn(deployment.user), without.for_call(deployment.user)

    assert turn.llms.chat is deployment.chat and not turn.exempt
    assert (call.stt, call.tts, call.own, call.exempt) == (
        DEPLOYER_SONIOX_KEY, DEPLOYER_FISH_KEY, frozenset(), False
    )
