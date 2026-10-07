"""Whose keys a turn or call runs on, answered once, through the own keys module: the
user's own where they brought them, the deployer's otherwise, never falling back from a
key of theirs that no longer works; and whether it counts towards the user's limit."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from eidolon.config import SttKey, SttProvider
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
        stt: SttKey | None = SttKey("soniox", DEPLOYER_SONIOX_KEY),
        tts: str | None = DEPLOYER_FISH_KEY,
    ) -> OwnKeys:
        return OwnKeys(
            self.store, secret_key, self.llm_service,
            DeployerKeys(self.chat, self.memory, stt, tts), self.speech,
        )


MY_LLM = OwnLLMSettings("https://llm.example.com/v1", "sk-my-own-llm-cccc", "my-model")
MY_FISH = "fish-my-own-key-aaaa"
MY_SONIOX = "soniox-my-own-key-bbbb"
MY_DASHSCOPE = "sk-my-own-dashscope-dddd"


async def bring(
    own_keys: OwnKeys, user_id: str, *services: str, stt: SttProvider = "soniox"
) -> None:
    for service in services:
        if service == "llm":
            await own_keys.save_llm(user_id, MY_LLM)
        elif service == "tts":
            await own_keys.save_speech(user_id, "tts", MY_FISH)
        else:
            api_key = MY_SONIOX if stt == "soniox" else MY_DASHSCOPE
            await own_keys.save_speech(user_id, "stt", api_key, stt_provider=stt)


async def ask(llm: ChatLLM) -> None:
    async for _ in llm.stream([ChatMessage("user", "在吗")]):
        pass


@pytest.fixture
def deployment(tmp_path: Path) -> Iterator[Deployment]:
    deployment = Deployment(tmp_path / "eidolon.db")
    yield deployment
    deployment.store.close()


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


async def test_a_call_hears_and_speaks_on_the_users_own_speech_keys_and_the_deployers_otherwise(
    deployment: Deployment,
):
    own_keys = deployment.own_keys()
    await bring(own_keys, deployment.user, "tts")

    keys = own_keys.for_call(deployment.user)

    assert (keys.stt, keys.tts) == (SttKey("soniox", DEPLOYER_SONIOX_KEY), MY_FISH)
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


@pytest.mark.parametrize(
    ("deployers", "mine"),
    [
        (SttKey("bailian", "deployer-dashscope-key", "beijing"), SttKey("soniox", MY_SONIOX)),
        (SttKey("soniox", DEPLOYER_SONIOX_KEY), SttKey("bailian", MY_DASHSCOPE, "singapore")),
    ],
)
async def test_a_users_own_speech_recognition_is_the_service_they_chose_whichever_the_deployer_did(
    deployment: Deployment, deployers: SttKey, mine: SttKey
):
    deployment.speech.regions[MY_DASHSCOPE] = "singapore"
    own_keys = deployment.own_keys(stt=deployers)
    other = deployment.store.create_user("other").id
    await bring(own_keys, deployment.user, "stt", stt=mine.provider)

    assert own_keys.for_call(deployment.user).stt == mine
    assert own_keys.for_call(other).stt == deployers
    assert own_keys.describe(deployment.user)["stt"] == {
        "last4": mine.api_key[-4:], "provider": mine.provider,
    }


async def test_a_speech_recognition_key_kept_before_there_was_a_choice_is_sonioxs(
    deployment: Deployment, tmp_path: Path
):
    await bring(deployment.own_keys(), deployment.user, "stt")
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

    assert own_keys.for_call(deployment.user).stt == SttKey("soniox", MY_SONIOX)
    assert own_keys.describe(deployment.user)["stt"] == {"last4": "bbbb", "provider": "soniox"}


@pytest.mark.parametrize(
    ("provider", "label"), [("soniox", "语音识别（Soniox）"), ("bailian", "语音识别（阿里云百炼）")]
)
async def test_an_own_speech_recognition_key_failing_says_whose_service_it_is_for(
    deployment: Deployment, provider: SttProvider, label: str
):
    await bring(deployment.own_keys(), deployment.user, "stt", stt=provider)
    changed = deployment.own_keys(secret_key="another-secret-key")

    with pytest.raises(OwnKeyFailed) as failed:
        changed.for_call(deployment.user)

    assert failed.value.message.startswith(f"你的{label}密钥调用失败")


async def test_a_user_can_call_on_their_own_key_for_what_the_deployer_has_none_for(
    deployment: Deployment,
):
    await bring(deployment.own_keys(), deployment.user, "stt")
    without_stt = deployment.own_keys(stt=None)
    without_tts = deployment.own_keys(tts=None)

    assert without_stt.for_call(deployment.user).stt == SttKey("soniox", MY_SONIOX)
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
        SttKey("soniox", DEPLOYER_SONIOX_KEY), DEPLOYER_FISH_KEY, frozenset(), False
    )
