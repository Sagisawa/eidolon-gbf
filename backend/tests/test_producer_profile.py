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


async def test_a_new_user_has_an_empty_profile(make_client: ClientFactory):
    res = await make_client(FakeLLM()).get("/api/profile")

    assert res.status_code == 200
    assert res.json() == {"form_of_address": None, "gender": None, "timezone": None}


async def test_profile_belongs_to_the_user_not_the_device(make_client: ClientFactory):
    desktop = make_client(FakeLLM())

    res = await desktop.put(
        "/api/profile",
        json={"form_of_address": "小林", "gender": "female", "timezone": "Asia/Tokyo"},
    )
    assert res.status_code == 200

    phone = await make_client(FakeLLM()).get("/api/profile")
    assert phone.json() == {"form_of_address": "小林", "gender": "female", "timezone": "Asia/Tokyo"}
    friend = await make_client(FakeLLM(), "friend").get("/api/profile")
    assert friend.json() == {"form_of_address": None, "gender": None, "timezone": None}


async def test_clearing_a_field_restores_its_default(make_client: ClientFactory):
    client = make_client(FakeLLM())
    await client.put(
        "/api/profile",
        json={"form_of_address": "小林", "gender": "male", "timezone": "Asia/Tokyo"},
    )

    res = await client.put(
        "/api/profile", json={"form_of_address": "  ", "gender": None, "timezone": None}
    )

    assert res.json() == {"form_of_address": None, "gender": None, "timezone": None}
    assert (await client.get("/api/profile")).json() == res.json()


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
