"""The producer profile: edited through the API, owned by the user rather than one device,
and carried into every conversation's prompt along with the current date and time
in the user's time zone."""

import sqlite3
from datetime import UTC, datetime

import httpx
import pytest

from eidolon.config import Settings
from tests.conftest import ClientFactory
from tests.fakes import FakeLLM
from tests.test_text_turn import send_turn, start_conversation

REPLY = ["<ja>はいっ</ja><zh>好的</zh>"]
NOW = datetime(2026, 9, 25, 12, 30, tzinfo=UTC)  # a Friday


def clock() -> datetime:
    return NOW


async def system_prompt(client: httpx.AsyncClient, llm: FakeLLM) -> str:
    conversation_id = await start_conversation(client)
    await send_turn(client, conversation_id, "在吗")
    system = llm.prompts[-1][0]
    assert system.role == "system"
    return system.content


async def test_profile_belongs_to_the_user_not_the_device(make_client: ClientFactory):
    desktop = make_client(FakeLLM())

    res = await desktop.put(
        "/api/profile",
        json={"form_of_address": "小林", "gender": "female", "timezone": "Asia/Tokyo"},
    )
    assert res.status_code == 200

    phone = await make_client(FakeLLM()).get("/api/profile")
    assert phone.json() == {
        "form_of_address": "小林",
        "gender": "female",
        "timezone": "Asia/Tokyo",
        "birthday": None,
    }
    friend = await make_client(FakeLLM(), "friend").get("/api/profile")
    assert friend.json() == {
        "form_of_address": None,
        "gender": None,
        "timezone": None,
        "birthday": None,
    }


async def test_birthday_belongs_to_the_user_not_the_device(make_client: ClientFactory):
    desktop = make_client(FakeLLM())

    res = await desktop.put("/api/profile", json={"birthday": {"month": 5, "day": 3}})
    assert res.status_code == 200
    assert res.json()["birthday"] == {"month": 5, "day": 3}

    phone = await make_client(FakeLLM()).get("/api/profile")
    assert phone.json()["birthday"] == {"month": 5, "day": 3}
    friend = await make_client(FakeLLM(), "friend").get("/api/profile")
    assert friend.json()["birthday"] is None


FULL_PROFILE = {
    "form_of_address": "小林",
    "gender": "male",
    "timezone": "Asia/Tokyo",
    "birthday": {"month": 5, "day": 3},
}
EMPTY_PROFILE = {"form_of_address": None, "gender": None, "timezone": None, "birthday": None}


@pytest.mark.parametrize(
    "cleared",
    [{"form_of_address": "  ", "gender": None, "timezone": None, "birthday": None}, {}],
    ids=["null", "left-out"],
)
async def test_clearing_a_field_restores_its_default(make_client: ClientFactory, cleared: dict):
    client = make_client(FakeLLM())
    await client.put("/api/profile", json=FULL_PROFILE)

    res = await client.put("/api/profile", json=cleared)

    assert res.json() == EMPTY_PROFILE
    assert (await client.get("/api/profile")).json() == EMPTY_PROFILE


@pytest.mark.parametrize(
    "profile",
    [
        {"form_of_address": "长" * 21},
        {"gender": "unknown"},
        {"timezone": "Mars/Olympus_Mons"},
        {"timezone": "../../etc/passwd"},
        {"timezone": "America"},
        {"timezone": "localtime"},
    ],
    ids=[
        "address-too-long",
        "unknown-gender",
        "unknown-timezone",
        "path-as-timezone",
        "region-as-timezone",
        "server-local-time",
    ],
)
async def test_invalid_profile_is_rejected(make_client: ClientFactory, profile: dict):
    client = make_client(FakeLLM())

    res = await client.put("/api/profile", json=profile)

    assert res.status_code == 422
    assert (await client.get("/api/profile")).json()["timezone"] is None


async def test_a_leap_day_birthday_can_be_saved(make_client: ClientFactory):
    client = make_client(FakeLLM())

    res = await client.put("/api/profile", json={"birthday": {"month": 2, "day": 29}})

    assert res.status_code == 200
    assert (await client.get("/api/profile")).json()["birthday"] == {"month": 2, "day": 29}


@pytest.mark.parametrize(
    "birthday",
    [
        {"month": 2, "day": 30},
        {"month": 4, "day": 31},
        {"month": 13, "day": 1},
        {"month": 0, "day": 1},
        {"month": 5, "day": 0},
        {"month": 5},
        {"month": 5, "day": None},
    ],
    ids=["feb-30", "apr-31", "month-13", "month-0", "day-0", "month-only", "day-null"],
)
async def test_a_birthday_that_is_no_day_of_the_year_is_rejected(
    make_client: ClientFactory, birthday: dict
):
    client = make_client(FakeLLM())
    await client.put("/api/profile", json=FULL_PROFILE)

    res = await client.put("/api/profile", json={**FULL_PROFILE, "birthday": birthday})

    assert res.status_code == 422
    assert (await client.get("/api/profile")).json() == FULL_PROFILE


async def test_profile_needs_a_session(make_client: ClientFactory):
    client = make_client(FakeLLM(), user=None)

    assert (await client.get("/api/profile")).status_code == 401
    assert (await client.put("/api/profile", json={})).status_code == 401


async def test_form_of_address_enters_the_prompt_as_a_way_of_calling_the_producer(
    make_client: ClientFactory,
):
    llm = FakeLLM(REPLY)
    client = make_client(llm)
    await client.put("/api/profile", json={"form_of_address": "小林さん"})

    prompt = await system_prompt(client, llm)

    assert "「小林さん」" in prompt
    assert "仍然是你的制作人" in prompt


async def test_without_a_form_of_address_the_character_sheet_decides(
    make_client: ClientFactory,
):
    llm = FakeLLM(REPLY)
    client = make_client(llm)

    prompt = await system_prompt(client, llm)

    assert "你是櫻木真乃" in prompt
    assert "希望你称呼" not in prompt


async def test_gender_enters_the_prompt_without_rewriting_the_story(
    make_client: ClientFactory,
):
    llm = FakeLLM(REPLY)
    client = make_client(llm)
    await client.put("/api/profile", json={"gender": "female"})

    prompt = await system_prompt(client, llm)

    assert "制作人是女性" in prompt
    assert "剧情中发生过的事保持原样" in prompt


async def test_without_a_gender_the_original_producer_stands(make_client: ClientFactory):
    llm = FakeLLM(REPLY)
    client = make_client(llm)

    prompt = await system_prompt(client, llm)

    assert "制作人是男性" in prompt
    assert "女性" not in prompt


async def test_a_birthday_enters_the_prompt_as_the_producers_own_word(
    make_client: ClientFactory,
):
    llm = FakeLLM(REPLY)
    client = make_client(llm, clock=clock)
    await client.put("/api/profile", json={"birthday": {"month": 5, "day": 3}})

    prompt = await system_prompt(client, llm)

    assert "生日是5月3日" in prompt
    assert "以这里为准" in prompt
    assert "不要主动提起" in prompt


async def test_without_a_birthday_the_prompt_says_nothing_of_one(make_client: ClientFactory):
    llm = FakeLLM(REPLY)
    client = make_client(llm, clock=clock)

    prompt = await system_prompt(client, llm)

    assert "生日" not in prompt


async def test_prompt_tells_the_current_time_in_the_devices_timezone(
    make_client: ClientFactory,
):
    llm = FakeLLM(REPLY)
    client = make_client(llm, clock=clock)
    client.headers["X-Timezone"] = "Asia/Tokyo"

    prompt = await system_prompt(client, llm)

    assert "2026年9月25日" in prompt
    assert "星期五" in prompt
    assert "21:30" in prompt
    assert "Asia/Tokyo" in prompt


async def test_a_timezone_set_in_the_profile_overrides_the_device(make_client: ClientFactory):
    llm = FakeLLM(REPLY)
    client = make_client(llm, clock=clock)
    client.headers["X-Timezone"] = "Asia/Tokyo"
    await client.put("/api/profile", json={"timezone": "America/Los_Angeles"})

    prompt = await system_prompt(client, llm)

    assert "2026年9月25日" in prompt
    assert "05:30" in prompt
    assert "America/Los_Angeles" in prompt


@pytest.mark.parametrize(
    "header", [None, "Not/A_Zone", "America"], ids=["missing", "unknown", "region"]
)
async def test_without_a_usable_timezone_the_time_is_given_in_shanghai(
    make_client: ClientFactory, header: str | None
):
    llm = FakeLLM(REPLY)
    client = make_client(llm, clock=clock)
    if header is not None:
        client.headers["X-Timezone"] = header

    prompt = await system_prompt(client, llm)

    assert "20:30" in prompt
    assert "Asia/Shanghai" in prompt


async def test_a_saved_timezone_no_longer_known_falls_back_instead_of_failing(
    make_client: ClientFactory, settings: Settings
):
    llm = FakeLLM(REPLY)
    client = make_client(llm, clock=clock)
    client.headers["X-Timezone"] = "Asia/Tokyo"
    await client.put("/api/profile", json={"timezone": "Asia/Tokyo"})
    with sqlite3.connect(settings.database_path) as db:  # as if tzdata dropped the zone
        db.execute("UPDATE producer_profiles SET timezone = 'Gone/Away'")

    prompt = await system_prompt(client, llm)

    assert "21:30" in prompt and "Asia/Tokyo" in prompt


async def test_a_profile_saved_before_birthdays_keeps_working(
    make_client: ClientFactory, settings: Settings
):
    old = {"form_of_address": "小林", "gender": "female", "timezone": "Asia/Tokyo"}
    await make_client(FakeLLM()).put("/api/profile", json=old)
    with sqlite3.connect(settings.database_path) as db:  # as the table was before birthdays
        db.execute("ALTER TABLE producer_profiles DROP COLUMN birthday_month")
        db.execute("ALTER TABLE producer_profiles DROP COLUMN birthday_day")

    upgraded = make_client(FakeLLM())

    assert (await upgraded.get("/api/profile")).json() == {**old, "birthday": None}
    res = await upgraded.put("/api/profile", json={**old, "birthday": {"month": 5, "day": 3}})
    assert res.status_code == 200
    assert (await upgraded.get("/api/profile")).json()["birthday"] == {"month": 5, "day": 3}
