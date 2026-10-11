"""Letting a user use the deployer's LLM (GLOSSARY.md「必须自带 LLM」): beside a user's own
limits, an admin may let them use the deployer's LLM where the deployment requires users to
bring their own. Only that set, the user's limits follow the deployment's; taken off with
the user's own limits. A user let use it takes turns and calls without their own LLM, and
they count as ever; one whose own limit is 0 is refused all the same, by the limit. Driven
through the backend's external API."""

import sqlite3
from dataclasses import replace

import httpx
import pytest

from eidolon.config import Settings, UsageLimits
from tests.browser import open_browser
from tests.conftest import ClientFactory
from tests.fakes import START, FakeClock, FakeIdentityProvider, FakeLLM
from tests.test_admin_users import ADMIN, admin_client, details, find
from tests.test_own_llm_required import DETAIL, account_requires_own_llm
from tests.test_own_speech_keys import ask_before_calling
from tests.test_rate_limit import REPLY, post_turn
from tests.test_text_turn import send_turn, start_conversation


@pytest.fixture
def settings(settings: Settings) -> Settings:
    """With an admin, a turn and a call an hour, and users' own LLM required."""
    return replace(
        settings,
        admins=frozenset({ADMIN}),
        usage_limits=UsageLimits(turns_per_hour=1, calls_per_hour=1),
        own_llm_required=True,
    )


def limits_url(user_id: str) -> str:
    return f"/api/admin/users/{user_id}/limits"


async def allow(admin: httpx.AsyncClient, user_id: str, **limits) -> dict:
    """Let the user use the deployer's LLM, with `limits` beside it."""
    res = await admin.put(limits_url(user_id), json={"deployer_llm_allowed": True} | limits)
    assert res.status_code == 200, res.text
    return res.json()


async def test_an_admin_lets_a_user_use_the_deployers_llm_alone_and_takes_it_off_with_the_limits(
    make_client: ClientFactory, github: FakeIdentityProvider
):
    admin = await admin_client(make_client, github, clock=FakeClock())
    make_client(FakeLLM())
    producer_id = (await find(admin, "producer"))["id"]

    shown = await allow(admin, producer_id, note="朋友")
    listed = await find(admin, "producer")
    taken_off = await admin.delete(limits_url(producer_id))

    allowed = {"turns_per_hour": None, "calls_per_hour": None, "note": "朋友",
               "updated_at": START.isoformat(), "deployer_llm_allowed": True}
    assert shown["limits"] == allowed
    assert listed["limits"] == allowed
    assert taken_off.status_code == 200
    assert taken_off.json()["limits"] is None
    assert (await details(admin, producer_id))["limits"] is None


async def test_own_limits_set_before_users_could_be_let_still_hold_and_let_no_one(
    make_client: ClientFactory, settings: Settings, github: FakeIdentityProvider
):
    clock = FakeClock()
    admin = await admin_client(make_client, github, clock=clock)
    producer = make_client(FakeLLM(REPLY), clock=clock)
    conversation_id = await start_conversation(producer)
    producer_id = (await find(admin, "producer"))["id"]
    with sqlite3.connect(settings.database_path) as db:  # own limits as they were kept then
        db.execute("DROP TABLE user_limits")
        db.execute(
            "CREATE TABLE user_limits (user_id TEXT PRIMARY KEY REFERENCES users(id),"
            " turns_per_hour INTEGER, calls_per_hour INTEGER, note TEXT,"
            " updated_at TEXT NOT NULL)"
        )
        db.execute(
            "INSERT INTO user_limits VALUES (?, -1, NULL, '老数据', ?)",
            (producer_id, START.isoformat()),
        )
    db.close()

    upgraded = await admin_client(make_client, github, clock=clock)
    producer = make_client(FakeLLM(REPLY), clock=clock)
    shown = (await details(upgraded, producer_id))["limits"]
    refused = await post_turn(producer, conversation_id)

    assert shown == {"turns_per_hour": "unlimited", "calls_per_hour": None, "note": "老数据",
                     "updated_at": START.isoformat(), "deployer_llm_allowed": False}
    assert refused.status_code == 403
    assert refused.json()["detail"] == DETAIL


async def test_a_user_let_takes_turns_on_the_deployers_llm_and_they_count(
    make_client: ClientFactory, github: FakeIdentityProvider
):
    admin = await admin_client(make_client, github)
    deployers = FakeLLM(REPLY)
    producer = make_client(deployers, clock=FakeClock())
    conversation_id = await start_conversation(producer)
    await allow(admin, (await find(admin, "producer"))["id"])

    allowed = await send_turn(producer, conversation_id, "早上好")
    over = await post_turn(producer, conversation_id)

    assert allowed[-1]["type"] == "done"
    assert len(deployers.prompts) == 1
    assert over.status_code == 429  # the deployment's turn an hour, used up
    assert "每小时 1 次" in over.json()["detail"]


async def test_the_account_of_a_user_let_says_they_need_not_bring_their_own_llm(
    make_client: ClientFactory, github: FakeIdentityProvider
):
    admin = await admin_client(make_client, github)
    producer = make_client(FakeLLM())
    producer_id = (await find(admin, "producer"))["id"]

    before = await account_requires_own_llm(producer)
    await allow(admin, producer_id)
    let = await account_requires_own_llm(producer)
    await admin.delete(limits_url(producer_id))
    taken_off = await account_requires_own_llm(producer)

    assert (before, let, taken_off) == (True, False, True)


async def test_a_user_let_with_an_own_limit_of_0_is_still_refused_by_the_limit(
    make_client: ClientFactory, github: FakeIdentityProvider
):
    admin = await admin_client(make_client, github)
    deployers = FakeLLM(REPLY)
    producer = make_client(deployers, clock=FakeClock())
    conversation_id = await start_conversation(producer)
    await allow(admin, (await find(admin, "producer"))["id"], turns_per_hour=0)

    refused = await post_turn(producer, conversation_id)

    assert refused.status_code == 429
    assert "只能用自带密钥" in refused.json()["detail"]
    assert deployers.prompts == []


async def test_a_user_let_places_calls_without_their_own_llm_and_they_count(
    make_client: ClientFactory, github: FakeIdentityProvider
):
    admin = await admin_client(make_client, github)
    producer = make_client(FakeLLM(REPLY), clock=FakeClock())
    conversation_id = await start_conversation(producer)
    await allow(admin, (await find(admin, "producer"))["id"])

    asked = await ask_before_calling(producer)
    async with open_browser() as first:
        placed = await first.call(producer, conversation_id=conversation_id)
    async with open_browser() as second:
        over = await second.call(producer, conversation_id=conversation_id)

    assert asked.status_code == 200, asked.text
    assert placed.status_code == 200, placed.text
    assert over.status_code == 429  # the deployment's call an hour, used up
    assert "语音通话" in over.json()["detail"]
