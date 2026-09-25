"""Per-user rate limits: text turns and voice calls count against the user's hourly limits,
whichever of their access keys they come with, driven through the backend's external API
with a clock the tests control."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from aiortc import RTCConfiguration, RTCPeerConnection

from eidolon.config import Settings, UsageLimits
from tests.conftest import Admin, ClientFactory
from tests.fakes import FakeCalls, FakeLLM
from tests.test_text_turn import send_turn, start_conversation
from tests.test_voice_call import call, offer_body

REPLY = ["<ja>はいっ</ja><zh>好的</zh>"]
START = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, now: datetime = START) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


def limited(settings: Settings, *, turns: int | None = 60, calls: int | None = 5) -> Settings:
    return replace(settings, usage_limits=UsageLimits(turns_per_hour=turns, calls_per_hour=calls))


@asynccontextmanager
async def browser() -> AsyncIterator[RTCPeerConnection]:
    """A browser's side of one call."""
    pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
    pc.addTransceiver("audio", direction="sendrecv")
    pc.createDataChannel("chat")
    try:
        yield pc
    finally:
        await pc.close()


async def post_turn(client: httpx.AsyncClient, conversation_id: str) -> httpx.Response:
    return await client.post(f"/api/conversations/{conversation_id}/turns", json={"text": "在吗"})


async def test_text_turns_over_the_hourly_limit_are_refused_until_the_oldest_ages_out(
    make_client: ClientFactory, settings: Settings
):
    clock = FakeClock()
    llm = FakeLLM(REPLY, REPLY, REPLY)
    client = make_client(llm, settings=limited(settings, turns=2), clock=clock)
    conversation_id = await start_conversation(client)
    await send_turn(client, conversation_id, "早上好")
    clock.advance(minutes=20)
    await send_turn(client, conversation_id, "在吗")
    clock.advance(minutes=10)

    refused = await post_turn(client, conversation_id)

    assert refused.status_code == 429
    body = refused.json()
    assert "文字对话" in body["detail"]
    assert datetime.fromisoformat(body["retry_at"]) == START + timedelta(hours=1)
    assert refused.headers["Retry-After"] == str(30 * 60)
    assert len(llm.prompts) == 2  # the model was never asked

    clock.advance(minutes=30)
    events = await send_turn(client, conversation_id, "现在呢")
    assert events[-1]["type"] == "done"


async def test_all_of_a_users_keys_share_one_limit_and_other_users_have_their_own(
    make_client: ClientFactory, settings: Settings, admin: Admin
):
    clock = FakeClock()
    settings = limited(settings, turns=2)
    desktop = make_client(FakeLLM(REPLY), settings=settings, clock=clock)
    phone = make_client(
        FakeLLM(REPLY), admin.issue_key("producer").secret, settings=settings, clock=clock
    )
    admin.create_user("friend")
    friend = make_client(
        FakeLLM(REPLY), admin.issue_key("friend").secret, settings=settings, clock=clock
    )
    conversation_id = await start_conversation(desktop)
    await send_turn(desktop, conversation_id, "在吗")
    await send_turn(phone, conversation_id, "在吗")

    assert (await post_turn(desktop, conversation_id)).status_code == 429
    assert (await post_turn(phone, conversation_id)).status_code == 429
    events = await send_turn(friend, await start_conversation(friend), "在吗")
    assert events[-1]["type"] == "done"


async def test_voice_calls_have_their_own_hourly_limit_and_renegotiating_is_free(
    make_client: ClientFactory, settings: Settings, calls: FakeCalls
):
    clock = FakeClock()
    client = make_client(FakeLLM(REPLY), settings=limited(settings, calls=2), clock=clock)
    conversation_id = await start_conversation(client)
    async with browser() as first:
        pc_id = (await call(client, first, conversation_id=conversation_id)).json()["pc_id"]
        renegotiation = {**await offer_body(first, conversation_id=conversation_id), "pc_id": pc_id}
        assert (await client.post("/api/offer", json=renegotiation)).status_code == 200
    clock.advance(minutes=5)
    async with browser() as second:
        assert (await call(client, second, conversation_id=conversation_id)).status_code == 200
    clock.advance(minutes=5)

    async with browser() as third:
        refused = await call(client, third, conversation_id=conversation_id)

    assert refused.status_code == 429
    assert "语音通话" in refused.json()["detail"]
    assert datetime.fromisoformat(refused.json()["retry_at"]) == START + timedelta(hours=1)
    assert len(calls.started) == 2
    # Calls and text turns are counted apart.
    events = await send_turn(client, conversation_id, "在吗")
    assert events[-1]["type"] == "done"


async def test_a_limit_of_none_lets_everything_through(
    make_client: ClientFactory, settings: Settings
):
    client = make_client(
        FakeLLM(*[REPLY] * 5), settings=limited(settings, turns=None), clock=FakeClock()
    )
    conversation_id = await start_conversation(client)

    for _ in range(5):
        assert (await send_turn(client, conversation_id, "在吗"))[-1]["type"] == "done"


def test_limits_come_from_the_environment(monkeypatch: pytest.MonkeyPatch):
    for name in ["TURNS_PER_HOUR", "CALLS_PER_HOUR", "CALL_MINUTES", "TURNS_PER_CALL"]:
        monkeypatch.delenv(f"EIDOLON_{name}", raising=False)
    assert UsageLimits.from_env() == UsageLimits(
        turns_per_hour=60, calls_per_hour=5, call_minutes=10, turns_per_call=40
    )

    monkeypatch.setenv("EIDOLON_TURNS_PER_HOUR", "30")
    monkeypatch.setenv("EIDOLON_CALLS_PER_HOUR", "0")
    monkeypatch.setenv("EIDOLON_CALL_MINUTES", "15")
    monkeypatch.setenv("EIDOLON_TURNS_PER_CALL", "0")
    assert UsageLimits.from_env() == UsageLimits(
        turns_per_hour=30, calls_per_hour=None, call_minutes=15, turns_per_call=None
    )

    monkeypatch.setenv("EIDOLON_CALLS_PER_HOUR", "-1")
    with pytest.raises(RuntimeError, match="EIDOLON_CALLS_PER_HOUR"):
        UsageLimits.from_env()


async def test_a_turn_that_fails_gives_its_use_back(make_client: ClientFactory, settings: Settings):
    llm = FakeLLM()  # no scripted reply: the first turn fails
    client = make_client(llm, settings=limited(settings, turns=1), clock=FakeClock())
    conversation_id = await start_conversation(client)

    assert (await send_turn(client, conversation_id, "在吗"))[-1]["type"] == "error"

    llm._replies.append(list(REPLY))
    assert (await send_turn(client, conversation_id, "在吗"))[-1]["type"] == "done"


async def test_a_call_that_cannot_be_set_up_gives_its_use_back(
    make_client: ClientFactory, settings: Settings, calls: FakeCalls
):
    client = make_client(FakeLLM(), settings=limited(settings, calls=1), clock=FakeClock())
    conversation_id = await start_conversation(client)
    async with browser() as pc:
        broken = {**await offer_body(pc, conversation_id=conversation_id), "type": "answer"}
        failed = await client.post("/api/offer", json=broken)
    assert failed.status_code == 500
    assert failed.json()["detail"] == "无法建立通话"

    async with browser() as pc:
        assert (await call(client, pc, conversation_id=conversation_id)).status_code == 200
