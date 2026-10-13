"""Users need not bring their own LLM, whatever the deployment: a text turn or call without
it goes on, on the deployer's LLM, and counts towards the limit like any other; only the
limit refuses it. Users once had to where the deployer required it (「必须自带 LLM」, since
taken out): `.env`'s `EIDOLON_OWN_LLM_REQUIRED` is only warned of as the server starts, the
admin console has no such switch, a user's own limits no letting, and a database from then
forgets both as it is opened. Driven through the backend's external API, calls with a
browser over a real WebRTC connection."""

import logging
import sqlite3
from dataclasses import replace

import pytest

from eidolon.config import Settings, UsageLimits
from tests.browser import open_browser
from tests.conftest import DEPLOYER_FISH_KEY, DEPLOYER_SONIOX_KEY, ClientFactory
from tests.fakes import START, FakeClock, FakeIdentityProvider, FakeLLM, FakeSpeech
from tests.test_admin_users import ADMIN, admin_beside, admin_client, details, find
from tests.test_live_config_limits import LIMITS
from tests.test_own_speech_keys import ask_before_calling
from tests.test_rate_limit import REPLY, post_turn
from tests.test_text_turn import send_turn, start_conversation

CALL_REPLY = ["<ja>はいっ</ja><zh>好的</zh>"]


@pytest.fixture
def settings(settings: Settings) -> Settings:
    """With an admin, and a turn and a call an hour."""
    return replace(
        settings,
        admins=frozenset({ADMIN}),
        usage_limits=UsageLimits(turns_per_hour=1, calls_per_hour=1),
    )


def limits_url(user_id: str) -> str:
    return f"/api/admin/users/{user_id}/limits"


async def test_a_turn_without_an_own_llm_goes_on_and_counts(make_client: ClientFactory):
    deployers = FakeLLM(REPLY)
    producer = make_client(deployers, clock=FakeClock())
    conversation_id = await start_conversation(producer)

    allowed = await send_turn(producer, conversation_id, "早上好")
    over = await post_turn(producer, conversation_id)

    assert allowed[-1]["type"] == "done"
    assert len(deployers.prompts) == 1
    assert over.status_code == 429
    assert "每小时 1 次" in over.json()["detail"]


async def test_a_call_without_an_own_llm_is_placed_on_the_deployers_keys_and_counts(
    make_client: ClientFactory, speech: FakeSpeech
):
    deployers = FakeLLM(CALL_REPLY)
    client = make_client(deployers, clock=FakeClock())
    conversation_id = await start_conversation(client, "kogane")

    asked = await ask_before_calling(client)
    async with open_browser() as browser:
        placed = await browser.call(client, conversation_id=conversation_id)
        await browser.connect()
        await speech.stts[-1].hear("你好")
        turn = await browser.turn()
        await browser.hang_up()
    async with open_browser() as browser:
        over = await browser.call(client, conversation_id=conversation_id)

    assert asked.status_code == 200, asked.text
    assert asked.json()["callExempt"] is False
    assert placed.status_code == 200, placed.text
    assert turn[-1]["type"] == "done"
    assert len(deployers.prompts) == 1
    assert [stt.api_key for stt in speech.stts] == [DEPLOYER_SONIOX_KEY]
    assert [tts.api_key for tts in speech.ttss] == [DEPLOYER_FISH_KEY]
    assert over.status_code == 429


async def test_the_admin_console_has_no_switch_requiring_an_own_llm(
    make_client: ClientFactory, github: FakeIdentityProvider
):
    producer = make_client(FakeLLM())

    async with admin_beside(producer, github) as admin:
        env = (await admin.get("/api/admin/config")).json()["limits"]["env"]
        saved = await admin.put(LIMITS, json=env | {"own_llm_required": True})

    assert saved.status_code == 200, saved.text
    assert saved.json()["limits"]["override"] is None  # nothing it takes was changed
    assert "own_llm_required" not in saved.json()["limits"]["effective"]


async def test_a_users_own_limits_let_no_one_use_the_deployers_llm(
    make_client: ClientFactory, github: FakeIdentityProvider
):
    admin = await admin_client(make_client, github, clock=FakeClock())
    make_client(FakeLLM())
    producer_id = (await find(admin, "producer"))["id"]

    letting_alone = await admin.put(limits_url(producer_id), json={"deployer_llm_allowed": True})
    with_a_limit = await admin.put(
        limits_url(producer_id), json={"turns_per_hour": 3, "deployer_llm_allowed": True}
    )

    assert letting_alone.status_code == 422
    assert with_a_limit.status_code == 200, with_a_limit.text
    assert with_a_limit.json()["limits"] == {
        "turns_per_hour": 3, "calls_per_hour": None, "note": None,
        "updated_at": START.isoformat(),
    }


async def test_a_database_from_then_forgets_the_switch_and_the_letting_and_keeps_the_rest(
    make_client: ClientFactory, settings: Settings, github: FakeIdentityProvider
):
    clock = FakeClock()
    admin = await admin_client(make_client, github, clock=clock)
    make_client(FakeLLM(), clock=clock)
    producer_id = (await find(admin, "producer"))["id"]
    with sqlite3.connect(settings.database_path) as db:  # kept as they were then
        db.execute(
            "ALTER TABLE user_limits ADD COLUMN deployer_llm_allowed INTEGER NOT NULL DEFAULT 0"
        )
        db.execute(
            "INSERT INTO user_limits VALUES (?, -1, NULL, '老数据', ?, 1)",
            (producer_id, START.isoformat()),
        )
        db.executemany(
            "INSERT INTO config_overrides (name, value, updated_at) VALUES (?, ?, ?)",
            [
                ("limits.own_llm_required", "true", START.isoformat()),
                ("limits.turns_per_hour", "3", START.isoformat()),
            ],
        )
    db.close()

    for start in ["first", "again"]:
        upgraded = await admin_client(make_client, github, clock=clock)

        with sqlite3.connect(settings.database_path) as db:
            columns = {row[1] for row in db.execute("PRAGMA table_info(user_limits)")}
            overrides = [row[0] for row in db.execute("SELECT name FROM config_overrides")]
        db.close()
        assert "deployer_llm_allowed" not in columns, start
        assert overrides == ["limits.turns_per_hour"], start
        assert (await details(upgraded, producer_id))["limits"] == {
            "turns_per_hour": "unlimited", "calls_per_hour": None, "note": "老数据",
            "updated_at": START.isoformat(),
        }, start
        limits = (await upgraded.get("/api/admin/config")).json()["limits"]
        assert limits["override"] == {"turns_per_hour": 3}, start

    changed = await upgraded.put(limits_url(producer_id), json={"calls_per_hour": 2})
    assert changed.status_code == 200, changed.text
    assert changed.json()["limits"]["calls_per_hour"] == 2


def test_env_still_setting_it_starts_all_the_same_warning_it_does_nothing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    monkeypatch.setenv("CHAT_LLM_BASE_URL", "https://llm.example.com/v1")
    monkeypatch.setenv("CHAT_LLM_API_KEY", "sk-deployer")
    monkeypatch.setenv("CHAT_LLM_MODEL", "deployer-model")
    caplog.set_level(logging.WARNING)
    monkeypatch.delenv("EIDOLON_OWN_LLM_REQUIRED", raising=False)
    Settings.from_env()
    assert "EIDOLON_OWN_LLM_REQUIRED" not in caplog.text

    for value in ("1", "0", "", "true"):
        caplog.clear()
        monkeypatch.setenv("EIDOLON_OWN_LLM_REQUIRED", value)

        Settings.from_env()

        assert "EIDOLON_OWN_LLM_REQUIRED" in caplog.text, value
