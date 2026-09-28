"""Bringing your own speech keys, and what bringing your own keys exempts from the limits.

Fish Audio (speech synthesis) and Soniox (speech recognition) keys are tried before they
are kept, then used for the user's calls; one that fails ends the call saying which,
without falling back to the deployer's. Text turns on the user's own LLM do not count
towards the hourly limit; calls count unless the LLM, synthesis and recognition are all
the user's own. How long a call may last and how many turns it may take is the same for
everyone."""

from dataclasses import replace

import httpx

from eidolon.config import Settings, UsageLimits
from tests.browser import Browser, open_browser
from tests.conftest import ClientFactory
from tests.fakes import (
    DEPLOYER_FISH_KEY,
    DEPLOYER_SONIOX_KEY,
    FakeClock,
    FakeLLM,
    FakeLLMService,
    FakeSpeech,
)
from tests.test_text_turn import send_turn, start_conversation

REPLY = ["<ja>はいっ</ja><zh>好的</zh>"]
MY_FISH = "fish-my-own-key-aaaa"
MY_SONIOX = "soniox-my-own-key-bbbb"
MY_LLM = {"base_url": "https://llm.example.com/v1", "api_key": "sk-my-own-llm-cccc", "model": "m"}


async def bring(client: httpx.AsyncClient, *services: str) -> None:
    for service in services:
        if service == "llm":
            res = await client.put("/api/account/keys/llm", json=MY_LLM)
        else:
            key = MY_FISH if service == "tts" else MY_SONIOX
            res = await client.put(f"/api/account/keys/{service}", json={"api_key": key})
        assert res.status_code == 200, res.text


def limited(settings: Settings, **limits: int | None) -> Settings:
    return replace(settings, usage_limits=UsageLimits(**limits))  # pyright: ignore[reportArgumentType]


async def test_speech_keys_are_tried_then_kept_showing_only_their_last_4_characters(
    make_client: ClientFactory, speech: FakeSpeech
):
    client = make_client(FakeLLM())

    await bring(client, "tts", "stt")
    listed = (await client.get("/api/account/keys")).json()

    assert speech.checked == [("tts", MY_FISH), ("stt", MY_SONIOX)]
    assert listed["keys"] == {"tts": {"last4": "aaaa"}, "stt": {"last4": "bbbb"}}
    assert MY_FISH not in str(listed) and MY_SONIOX not in str(listed)


async def test_a_speech_key_that_fails_its_try_is_not_kept(
    make_client: ClientFactory, speech: FakeSpeech
):
    client = make_client(FakeLLM())
    speech.rejects[MY_SONIOX] = "401 Incorrect API key provided"

    res = await client.put("/api/account/keys/stt", json={"api_key": MY_SONIOX})

    assert res.status_code == 422
    assert "Incorrect API key" in res.json()["detail"]
    assert (await client.get("/api/account/keys")).json()["keys"] == {}


async def test_a_call_hears_and_speaks_on_the_users_own_keys(
    make_client: ClientFactory, speech: FakeSpeech, browser: Browser
):
    client = make_client(FakeLLM(REPLY))
    await bring(client, "tts", "stt")

    await browser.call(client, conversation_id=await start_conversation(client, "kogane"))
    await browser.connect()

    assert [stt.api_key for stt in speech.stts] == [MY_SONIOX]
    assert [(tts.api_key, tts.voice_id) for tts in speech.ttss] == [(MY_FISH, "kogane-voice")]


async def test_the_deployers_keys_serve_what_the_user_did_not_bring(
    make_client: ClientFactory, speech: FakeSpeech, browser: Browser
):
    client = make_client(FakeLLM())
    await bring(client, "stt")

    await browser.call(client, conversation_id=await start_conversation(client))

    assert [stt.api_key for stt in speech.stts] == [MY_SONIOX]
    assert [tts.api_key for tts in speech.ttss] == [DEPLOYER_FISH_KEY]
    assert DEPLOYER_SONIOX_KEY not in {stt.api_key for stt in speech.stts}


async def test_the_users_own_keys_let_them_call_where_the_deployer_has_none(
    make_client: ClientFactory, browser: Browser
):
    client = make_client(FakeLLM(), voice_configured=False)
    conversation_id = await start_conversation(client)
    assert (await client.get("/api/ice-servers")).status_code == 503

    await bring(client, "tts", "stt")

    assert (await client.get("/api/ice-servers")).status_code == 200
    assert (await browser.call(client, conversation_id=conversation_id)).status_code == 200


async def test_a_failing_own_speech_key_ends_the_call_saying_which(
    make_client: ClientFactory, speech: FakeSpeech, browser: Browser
):
    client = make_client(FakeLLM())
    await bring(client, "stt")
    await browser.call(client, conversation_id=await start_conversation(client))
    await browser.connect()

    await speech.stts[-1].break_down()

    ended = await browser.next_server_message("ended")
    assert "你的语音识别（Soniox）密钥调用失败" in ended["message"]
    assert (ended["reason"], ended["counts"]) == ("own_key", False)  # before any turn
    await browser.hung_up()
    assert [stt.api_key for stt in speech.stts] == [MY_SONIOX]  # no second try on the deployer's


async def test_text_turns_on_the_users_own_llm_do_not_count(
    make_client: ClientFactory, settings: Settings, own_llm: FakeLLMService
):
    own_llm.llm = FakeLLM(REPLY, REPLY, REPLY)
    client = make_client(FakeLLM(), settings=limited(settings, turns_per_hour=1), clock=FakeClock())
    await bring(client, "llm")
    conversation_id = await start_conversation(client)

    for _ in range(3):
        assert (await send_turn(client, conversation_id, "在吗"))[-1]["type"] == "done"
    assert (await client.get("/api/account/keys")).json()["exempt"] == {
        "turns": True, "calls": False,
    }


async def test_calls_count_unless_all_three_services_are_the_users_own(
    make_client: ClientFactory, settings: Settings
):
    client = make_client(FakeLLM(), settings=limited(settings, calls_per_hour=1), clock=FakeClock())
    await bring(client, "llm", "tts")
    conversation_id = await start_conversation(client)

    async with open_browser() as first:
        assert (await first.call(client, conversation_id=conversation_id)).status_code == 200
        await first.connect()
    async with open_browser() as second:
        assert (await second.call(client, conversation_id=conversation_id)).status_code == 429

    await bring(client, "stt")
    assert (await client.get("/api/account/keys")).json()["exempt"] == {
        "turns": True, "calls": True,
    }
    assert (await client.get("/api/ice-servers")).json()["callExempt"] is True
    async with open_browser() as third:
        assert (await third.call(client, conversation_id=conversation_id)).status_code == 200


async def test_a_calls_own_limits_hold_for_everyone(
    make_client: ClientFactory,
    settings: Settings,
    own_llm: FakeLLMService,
    speech: FakeSpeech,
    browser: Browser,
):
    own_llm.llm = FakeLLM(REPLY)
    client = make_client(FakeLLM(), settings=limited(settings, turns_per_call=1))
    await bring(client, "llm", "tts", "stt")
    await browser.call(client, conversation_id=await start_conversation(client))
    await browser.connect()

    await speech.stts[-1].hear("你好")
    await browser.turn()

    assert "1 轮" in (await browser.next_server_message("ended"))["message"]
