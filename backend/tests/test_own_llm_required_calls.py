"""Own LLM required (GLOSSARY.md「必须自带 LLM」) for calls: the one rule text turns are
refused by holds for calls too. Asked before calling (`/api/ice-servers`), a call bringing
no LLM of the user's own is refused, 403 saying why, before anything is spent on it;
placed, it is refused alike, recorded rejected and counting towards nothing. A call on
the user's own LLM alone goes on, heard and voiced on the deployer's keys, and counts
towards the calls an hour; one on all three of their own counts towards nothing, as ever.
Admins are not bound by it, and a call in progress goes on to its end whatever the admin
console says meanwhile. Driven through the backend's external API, with a browser calling
in over a real WebRTC connection and fake outside services."""

import asyncio
from dataclasses import replace

import httpx
import pytest

from eidolon.config import Settings, UsageLimits
from tests.browser import TIMEOUT, Browser, open_browser
from tests.conftest import DEPLOYER_FISH_KEY, DEPLOYER_SONIOX_KEY, ClientFactory
from tests.fakes import FakeClock, FakeIdentityProvider, FakeLLM, FakeLLMService, FakeSpeech
from tests.test_activity_records import dashboard
from tests.test_admin_users import ADMIN
from tests.test_own_llm_required import DETAIL, ENV_LIMITS, LIMITS, admin_beside
from tests.test_own_speech_keys import ask_before_calling, own_keys
from tests.test_text_turn import start_conversation

REPLY = ["<ja>はいっ</ja><zh>好的</zh>"]
REFUSED = {"detail": DETAIL, "own_llm_required": True}


@pytest.fixture
def settings(settings: Settings) -> Settings:
    """With an admin, a call an hour, and users' own LLM required."""
    return replace(
        settings,
        admins=frozenset({ADMIN}),
        usage_limits=UsageLimits(calls_per_hour=1),
        own_llm_required=True,
    )


async def require(admin: httpx.AsyncClient, required: bool) -> httpx.Response:
    """Have the admin require users' own LLM, or not, in the admin console, keeping a call
    an hour."""
    return await admin.put(
        LIMITS, json=ENV_LIMITS | {"calls_per_hour": 1, "own_llm_required": required}
    )


async def calls_recorded(admin: httpx.AsyncClient, total: int) -> dict:
    """The dashboard's calls, once there are `total` of them."""
    async with asyncio.timeout(TIMEOUT):
        while (board := await dashboard(admin))["calls"]["total"] < total:
            await asyncio.sleep(0.05)
    return board["calls"]


async def test_asked_before_calling_a_call_without_an_own_llm_is_refused_before_anything_is_spent(
    make_client: ClientFactory, speech: FakeSpeech
):
    client = make_client(FakeLLM())

    refusals = [await ask_before_calling(client, *own) for own in ((), ("tts", "stt"))]

    for res in refusals:
        assert res.status_code == 403
        assert res.json() == REFUSED
    assert (speech.stts, speech.ttss) == ([], [])


async def test_a_call_without_an_own_llm_is_refused_recorded_rejected_and_not_counted(
    make_client: ClientFactory, github: FakeIdentityProvider, speech: FakeSpeech
):
    deployers = FakeLLM()
    client = make_client(deployers, clock=FakeClock())
    conversation_id = await start_conversation(client)

    async with admin_beside(client, github) as admin:
        async with open_browser() as browser:
            refused = await browser.call(
                client, conversation_id=conversation_id, own_keys=own_keys("tts", "stt")
            )
        calls = await calls_recorded(admin, 1)
        assert (await require(admin, False)).status_code == 200
        # Had the refused call counted, the hour's one call would be used up.
        async with open_browser() as browser:
            allowed = await browser.call(client, conversation_id=conversation_id)
            await browser.connect()
            await browser.hang_up()
        async with open_browser() as browser:
            over = await browser.call(client, conversation_id=conversation_id)

    assert refused.status_code == 403
    assert refused.json() == REFUSED
    assert calls["by_result"]["rejected"] == 1
    assert allowed.status_code == 200, allowed.text
    assert over.status_code == 429
    assert len(speech.stts) == 1  # only the call let through was heard
    assert deployers.prompts == []


async def test_a_call_on_an_own_llm_alone_is_voiced_on_the_deployers_keys_and_counts(
    make_client: ClientFactory, speech: FakeSpeech, own_llm: FakeLLMService
):
    own_llm.llm = FakeLLM(REPLY)
    deployers = FakeLLM()
    client = make_client(deployers, clock=FakeClock())
    conversation_id = await start_conversation(client, "kogane")

    asked = await ask_before_calling(client, "llm")
    async with open_browser() as browser:
        placed = await browser.call(
            client, conversation_id=conversation_id, own_keys=own_keys("llm")
        )
        await browser.connect()
        await speech.stts[-1].hear("你好")
        turn = await browser.turn()
        await browser.hang_up()
    async with open_browser() as browser:
        over = await browser.call(
            client, conversation_id=conversation_id, own_keys=own_keys("llm")
        )

    assert asked.status_code == 200, asked.text
    assert asked.json()["callExempt"] is False
    assert placed.status_code == 200, placed.text
    assert turn[-1]["type"] == "done"
    assert [stt.api_key for stt in speech.stts] == [DEPLOYER_SONIOX_KEY]
    assert [tts.api_key for tts in speech.ttss] == [DEPLOYER_FISH_KEY]
    assert deployers.prompts == []  # she answered on the user's own LLM
    assert over.status_code == 429


async def test_a_call_on_all_three_own_keys_counts_towards_nothing_as_ever(
    make_client: ClientFactory, own_llm: FakeLLMService
):
    own_llm.llm = FakeLLM()
    client = make_client(FakeLLM(), clock=FakeClock())
    conversation_id = await start_conversation(client)

    asked = await ask_before_calling(client, "llm", "tts", "stt")
    placed = []
    for _ in range(2):  # one call an hour, but these count towards nothing
        async with open_browser() as browser:
            placed.append(
                await browser.call(
                    client,
                    conversation_id=conversation_id,
                    own_keys=own_keys("llm", "tts", "stt"),
                )
            )

    assert asked.status_code == 200, asked.text
    assert asked.json()["callExempt"] is True
    assert [res.status_code for res in placed] == [200, 200]


async def test_an_admin_without_an_own_llm_calls_and_counts(
    make_client: ClientFactory, github: FakeIdentityProvider
):
    producer = make_client(FakeLLM(), clock=FakeClock())

    async with admin_beside(producer, github) as admin:
        conversation_id = await start_conversation(admin)
        asked = await ask_before_calling(admin)
        async with open_browser() as browser:
            placed = await browser.call(admin, conversation_id=conversation_id)
            await browser.connect()
            await browser.hang_up()
        async with open_browser() as browser:
            over = await browser.call(admin, conversation_id=conversation_id)

    assert asked.status_code == 200, asked.text
    assert asked.json()["callExempt"] is False
    assert placed.status_code == 200, placed.text
    assert over.status_code == 429


async def test_off_calls_without_an_own_llm_go_on_and_count_as_before(
    make_client: ClientFactory, settings: Settings
):
    client = make_client(
        FakeLLM(), settings=replace(settings, own_llm_required=False), clock=FakeClock()
    )
    conversation_id = await start_conversation(client)

    asked = await ask_before_calling(client)
    async with open_browser() as browser:
        placed = await browser.call(client, conversation_id=conversation_id)
        await browser.connect()
        await browser.hang_up()
    async with open_browser() as browser:
        over = await browser.call(client, conversation_id=conversation_id)

    assert asked.status_code == 200, asked.text
    assert asked.json()["callExempt"] is False
    assert placed.status_code == 200, placed.text
    assert over.status_code == 429
    assert "语音通话" in over.json()["detail"]


async def test_a_call_in_progress_goes_on_to_its_end_once_an_own_llm_is_required(
    make_client: ClientFactory,
    settings: Settings,
    github: FakeIdentityProvider,
    speech: FakeSpeech,
    browser: Browser,
):
    client = make_client(
        FakeLLM(REPLY, REPLY),
        settings=replace(settings, own_llm_required=False),
        clock=FakeClock(),
    )
    conversation_id = await start_conversation(client)

    async with admin_beside(client, github) as admin:
        await browser.call(client, conversation_id=conversation_id)
        await browser.connect()
        await speech.stts[-1].hear("你好")
        before = await browser.turn()
        assert (await require(admin, True)).status_code == 200
        await speech.stts[-1].hear("还在吗")
        after = await browser.turn()
        await browser.hang_up()
        calls = await calls_recorded(admin, 1)

    assert before[-1]["type"] == "done"
    assert after[-1]["type"] == "done"
    assert calls["by_result"]["success"] == 1
    assert calls["by_result"]["rejected"] == 0
