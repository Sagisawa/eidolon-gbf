"""Activity records of text turns, and the dashboard over them: each turn leaves a record
of how it turned out (as it counts towards the limit), each service call in it a record of
how it went, how long it took and what it is billed for, all of it seen only as the
admin's dashboard sums it up, with nothing anyone said. Driven through the backend's
external API with a clock the tests control."""

import sqlite3
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

import httpx
import pytest

from eidolon.config import Settings, UsageLimits
from eidolon.llm import ChatLLM, LLMError
from eidolon.llm.anthropic import AnthropicLLM
from eidolon.llm.openai_compat import OpenAICompatLLM
from eidolon.llm.responses import ResponsesLLM
from tests.conftest import (
    ClientFactory,
    agree_to_terms,
    github_identity,
    sign_in_with,
)
from tests.fakes import (
    START,
    FakeBackgroundLLM,
    FakeClock,
    FakeEmbedder,
    FakeIdentityProvider,
    FakeJudge,
    FakeLLM,
    FakeLLMService,
    FakeReranker,
)
from tests.test_delete_account import rows_mentioning, user_id
from tests.test_llm_protocols import recorded, serving
from tests.test_openai_compat import RECORDED_STREAM
from tests.test_own_llm import MINE, bring_llm
from tests.test_rate_limit import post_turn
from tests.test_shared_memory import CAT, memorized
from tests.test_text_turn import leave_turn, send_turn, start_conversation

REPLY = ["<ja>はいっ</ja><zh>好的</zh>"]
SAID = "我家的猫叫小白哦"


@pytest.fixture
def settings(settings: Settings) -> Settings:
    """The tests' settings, where the GitHub user 1001 is an admin."""
    return replace(settings, admins=frozenset({("github", "1001")}))


async def admin_client(
    make_client: ClientFactory, github: FakeIdentityProvider, clock: FakeClock
) -> httpx.AsyncClient:
    client = make_client(FakeLLM(), user=None, clock=clock)
    await sign_in_with(client, github, github_identity("1001", name="octo"))
    await agree_to_terms(client)
    return client


async def dashboard(client: httpx.AsyncClient, range: str = "24h") -> dict:
    res = await client.get("/api/admin/dashboard", params={"range": range})
    assert res.status_code == 200, res.text
    return res.json()


def health(board: dict, service: str, own_key: bool = False) -> dict | None:
    """The dashboard's health row of `service`, on the deployer's keys or the users' own."""
    return next(
        (h for h in board["health"] if (h["service"], h["own_key"]) == (service, own_key)),
        None,
    )


async def test_the_dashboard_counts_turns_by_how_they_turned_out_and_says_nothing_said(
    make_client: ClientFactory, settings: Settings, github: FakeIdentityProvider
):
    clock = FakeClock()
    two = replace(settings, usage_limits=UsageLimits(turns_per_hour=2))
    llm = FakeLLM(
        REPLY,
        LLMError("模型返回 503: overloaded"),
        ["<ja>はい", "っ</ja>", "<zh>好", "的</zh>"],
        delay=0.2,
    )
    producer = make_client(llm, settings=two, clock=clock)
    friend = make_client(FakeLLM(REPLY), "friend", settings=two, clock=clock)
    conversation_id = await start_conversation(producer)
    admin = await admin_client(make_client, github, clock)

    succeeded = await send_turn(producer, conversation_id, SAID)
    failed = await send_turn(producer, conversation_id, "在吗")
    await leave_turn(producer, conversation_id, "你好", after="user")
    refused = await post_turn(producer, conversation_id)
    await send_turn(friend, await start_conversation(friend, "kogane"), "早上好")
    board = await dashboard(admin)

    assert (succeeded[-1]["type"], failed[-1]["type"], refused.status_code) == (
        "done", "error", 429
    )
    turns = board["turns"]
    assert turns["total"] == 5
    assert turns["by_result"] == {"success": 2, "failed": 1, "rejected": 1, "left": 1}
    assert turns["own_keys"] == 0
    assert turns["active_users"] == 2
    assert turns["time_to_speak_ms"]["p50"] is not None
    assert [(c["character_id"], c["name"], c["turns"]) for c in board["characters"]] == [
        ("mano", "櫻木真乃", 4), ("kogane", "月岡恋鐘", 1)
    ]
    assert sum(point["turns"] for point in board["trend"]) == 5
    # Each turn that reached the model called it once; only the one that failed failed.
    chat = health(board, "chat_llm")
    assert chat is not None
    assert (chat["calls"], chat["errors"]) == (4, 1)
    assert chat["errors_by_kind"] == {"server_error": 1}
    assert chat["latency_ms"]["p50"] is not None
    # The fakes say nothing of tokens: what the calls are billed for is not known.
    assert chat["usage_unknown"] == 4
    for text in [SAID, "在吗", "你好", "早上好", "はいっ", "好的", "overloaded"]:
        assert text not in str(board), text


async def test_a_failing_judge_shows_in_health_though_the_turn_goes_on(
    make_client: ClientFactory, settings: Settings, github: FakeIdentityProvider
):
    clock = FakeClock()
    client = make_client(
        FakeLLM(REPLY, REPLY), clock=clock, retrieval_judge=FakeJudge(None),
        embedder=FakeEmbedder(), reranker=FakeReranker("制作人"),
        background_llm=FakeBackgroundLLM(memorized(CAT)),
    )
    admin = await admin_client(make_client, github, clock)
    conversation_id = await start_conversation(client)

    await send_turn(client, conversation_id, SAID)
    assert [m["text"] for m in (await client.get("/api/memories")).json()] == [CAT]
    events = await send_turn(client, conversation_id, "你还记得我的猫吗")
    board = await dashboard(admin)

    assert events[-1]["type"] == "done"
    assert board["turns"]["by_result"]["success"] == 2
    judge = health(board, "judge")
    assert judge is not None and (judge["calls"], judge["errors"]) == (2, 2)
    # Retrieving anyway, the turns looked up references and memories, the second finding
    # and reranking the one the first wrote down with the background model, embedding it.
    for service in ["embedding", "rerank", "memory_llm", "chat_llm"]:
        row = health(board, service)
        assert row is not None and row["calls"] >= 1 and row["errors"] == 0, service
    assert CAT not in str(board)


async def test_calls_on_the_users_own_keys_are_counted_apart(
    make_client: ClientFactory,
    settings: Settings,
    github: FakeIdentityProvider,
    own_llm: FakeLLMService,
):
    clock = FakeClock()
    own_llm.llm = FakeLLM(REPLY, LLMError("402 Payment Required"))
    deployers = FakeLLM(REPLY)
    client = make_client(deployers, clock=clock)
    admin = await admin_client(make_client, github, clock)
    await bring_llm(client)
    conversation_id = await start_conversation(client)

    await send_turn(client, conversation_id, "在吗")
    await send_turn(client, conversation_id, "在吗")
    board = await dashboard(admin)

    own = health(board, "chat_llm", own_key=True)
    assert own is not None and (own["calls"], own["errors"]) == (2, 1)
    assert health(board, "chat_llm") is None
    assert board["turns"]["own_keys"] == 2
    assert board["turns"]["by_result"]["failed"] == 1
    assert MINE not in str(board)


async def test_each_range_takes_the_turns_since_that_long_ago(
    make_client: ClientFactory, settings: Settings, github: FakeIdentityProvider
):
    clock = FakeClock()
    client = make_client(FakeLLM(REPLY), clock=clock)
    admin = await admin_client(make_client, github, clock)
    await send_turn(client, await start_conversation(client), "在吗")

    clock.advance(hours=23, minutes=59)
    day = await dashboard(admin, "24h")
    assert day["turns"]["total"] == 1
    assert day["bucket"] == "hour" and len(day["trend"]) == 24
    clock.advance(minutes=1)
    assert (await dashboard(admin, "24h"))["turns"]["total"] == 0
    week = await dashboard(admin, "7d")
    assert week["turns"]["total"] == 1
    assert sum(point["turns"] for point in week["trend"]) == 1
    assert datetime.fromisoformat(week["from"]) <= START
    assert [len((await dashboard(admin, r))["trend"]) for r in ["7d", "30d", "90d"]] == [
        28, 30, 90
    ]
    assert (await admin.get("/api/admin/dashboard", params={"range": "1y"})).status_code == 422


async def test_records_are_forgotten_after_90_days(
    make_client: ClientFactory, settings: Settings, github: FakeIdentityProvider
):
    clock = FakeClock()
    client = make_client(FakeLLM(REPLY), clock=clock)
    await send_turn(client, await start_conversation(client), "在吗")

    clock.advance(days=90)
    later = make_client(FakeLLM(REPLY), clock=clock)  # signed in again
    await send_turn(later, await start_conversation(later), "在吗")
    admin = await admin_client(make_client, github, clock)

    assert (await dashboard(admin, "90d"))["turns"]["total"] == 1
    with sqlite3.connect(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM activity_records").fetchone() == (1,)
        assert db.execute("SELECT COUNT(*) FROM service_calls").fetchone() == (1,)


async def test_deleting_a_user_keeps_the_numbers_but_not_who_it_was(
    make_client: ClientFactory, settings: Settings, github: FakeIdentityProvider
):
    clock = FakeClock()
    client = make_client(FakeLLM(REPLY, REPLY), clock=clock)
    friend = make_client(FakeLLM(REPLY), "friend", clock=clock)
    admin = await admin_client(make_client, github, clock)
    conversation_id = await start_conversation(client)
    await send_turn(client, conversation_id, "在吗")
    await send_turn(client, conversation_id, "在吗")
    await send_turn(friend, await start_conversation(friend), "在吗")
    producer = user_id(settings.database_path, "producer")
    before = await dashboard(admin)

    assert (await client.post("/api/account/delete", json={"confirm": True})).status_code == 204

    after = await dashboard(admin)
    assert after == before
    assert after["turns"]["active_users"] == 2
    assert rows_mentioning(settings.database_path, producer) == {}


async def test_the_dashboard_is_for_admins_only(
    make_client: ClientFactory, settings: Settings
):
    client = make_client(FakeLLM())

    assert (await client.get("/api/admin/dashboard")).status_code == 404


Protocol = Callable[[httpx.AsyncClient], ChatLLM]
PROTOCOLS: dict[str, tuple[Protocol, str, tuple[int, int]]] = {
    # Each protocol's recorded reply, and the tokens it says the request was billed for.
    "chat-completions": (
        lambda http: OpenAICompatLLM("https://llm.example/v1", "sk", "m", client=http),
        RECORDED_STREAM,
        (10, 5),
    ),
    "responses": (
        lambda http: ResponsesLLM("https://llm.example/v1", "sk", "m", client=http),
        recorded("responses_text"),
        (57, 518),
    ),
    "anthropic": (
        lambda http: AnthropicLLM("https://llm.example/v1", "sk", "m", client=http),
        recorded("anthropic_text"),
        (57, 124),
    ),
}


@pytest.mark.parametrize("protocol", PROTOCOLS)
async def test_the_tokens_each_protocol_bills_are_recorded(
    make_client: ClientFactory,
    settings: Settings,
    github: FakeIdentityProvider,
    protocol: str,
):
    adapter, stream, (input_tokens, output_tokens) = PROTOCOLS[protocol]
    requests: list[httpx.Request] = []
    clock = FakeClock()
    client = make_client(adapter(serving(stream, requests)), clock=clock)  # pyright: ignore[reportArgumentType]
    admin = await admin_client(make_client, github, clock)

    events = await send_turn(client, await start_conversation(client), "你好")
    chat = health(await dashboard(admin), "chat_llm")

    assert events[-1]["type"] == "done"
    assert chat is not None
    assert chat["usage"] == [{"unit": "tokens", "input": input_tokens, "output": output_tokens}]
    assert chat["usage_unknown"] == 0
    if protocol == "chat-completions":  # which sends the usage only when asked to
        assert b'"stream_options":{"include_usage":true}' in requests[0].content.replace(
            b" ", b""
        )
