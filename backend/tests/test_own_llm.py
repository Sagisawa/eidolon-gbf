"""Bringing your own LLM: tried once, without being kept, before the browser keeps it; then
brought with each of the user's text turns, which it plays the character and writes down
memories on instead of the deployer's. It fails loudly rather than falling back to the
deployer's key.

Until calls bring their own keys too, a call still runs on an LLM kept on the server
(`keep_llm`)."""

import sqlite3
from dataclasses import replace

import httpcore
import httpx
import pytest

from eidolon.config import LLMSettings, Settings, UsageLimits
from eidolon.llm import ChatMessage, LLMError
from eidolon.own_keys import ProviderLLMService, PublicOnlyBackend
from tests.browser import Browser
from tests.conftest import ClientFactory
from tests.fakes import (
    DEPLOYER_KEY,
    FakeBackgroundLLM,
    FakeEmbedder,
    FakeJudge,
    FakeLLM,
    FakeLLMService,
    FakeReranker,
    FakeSpeech,
)
from tests.test_delete_account import rows_mentioning
from tests.test_shared_memory import CAT, memorized
from tests.test_text_turn import send_turn, start_conversation

REPLY = ["<ja>はいっ</ja><zh>好的</zh>"]
MINE = "sk-my-own-key-1234"
LLM = {
    "base_url": "https://llm.example.com/v1",
    "api_key": MINE,
    "model": "my-model",
    "protocol": "chat-completions",
}


async def check_llm(client: httpx.AsyncClient, **changes: str) -> httpx.Response:
    return await client.post("/api/account/keys/llm/check", json=LLM | changes)


async def keep_llm(client: httpx.AsyncClient) -> httpx.Response:
    """Keep the LLM on the server, as calls still take it from there."""
    return await client.put("/api/account/keys/llm", json=LLM)


async def test_an_own_llm_is_tried_and_not_kept(
    make_client: ClientFactory, own_llm: FakeLLMService, settings: Settings
):
    client = make_client(FakeLLM())

    checked = await check_llm(client, base_url=" https://llm.example.com/v1 ", model=" my-model ")

    assert checked.status_code == 200
    assert checked.json() == {"base_url": "https://llm.example.com/v1", "model": "my-model"}
    assert [(s.api_key, s.base_url, s.model) for s in own_llm.checked] == [
        (MINE, "https://llm.example.com/v1", "my-model")
    ]
    assert MINE not in checked.text
    assert (await client.get("/api/account/keys")).json()["keys"] == {}
    assert rows_mentioning(settings.database_path, "my-model") == {}


async def test_an_own_llm_that_fails_its_try_is_refused_with_what_the_service_said(
    make_client: ClientFactory, own_llm: FakeLLMService
):
    client = make_client(FakeLLM())
    own_llm.rejects[MINE] = "401 Unauthorized: invalid api key"

    res = await check_llm(client)

    assert res.status_code == 422
    assert "试调失败" in res.json()["detail"]
    assert "401 Unauthorized" in res.json()["detail"]


async def test_a_turn_bringing_an_own_llm_plays_on_it_and_one_bringing_none_on_the_deployers(
    make_client: ClientFactory, own_llm: FakeLLMService
):
    deployers = FakeLLM(REPLY)
    own_llm.llm = FakeLLM(REPLY)
    client = make_client(deployers)
    conversation_id = await start_conversation(client)

    on_own = await send_turn(client, conversation_id, "在吗", own_llm=LLM)

    assert on_own[-1]["type"] == "done"
    assert own_llm.llm.keys == [MINE]
    assert own_llm.opened[-1].base_url == "https://llm.example.com/v1"
    assert own_llm.opened[-1].model == "my-model"
    assert deployers.keys == []

    on_deployers = await send_turn(client, conversation_id, "在吗")

    assert on_deployers[-1]["type"] == "done"
    assert deployers.keys == [DEPLOYER_KEY]
    assert own_llm.llm.keys == [MINE]


async def test_the_users_own_llm_writes_down_their_memories(
    make_client: ClientFactory, own_llm: FakeLLMService
):
    own_llm.llm = FakeLLM(REPLY, [memorized(CAT)])
    deployers_background = FakeBackgroundLLM()
    client = make_client(
        FakeLLM(), retrieval_judge=FakeJudge(), embedder=FakeEmbedder(), reranker=FakeReranker("制作人"),
        background_llm=deployers_background,
    )

    await send_turn(client, await start_conversation(client), "我家的猫叫小白哦", own_llm=LLM)

    assert [m["text"] for m in (await client.get("/api/memories")).json()] == [CAT]
    assert own_llm.llm.keys == [MINE, MINE]
    assert deployers_background.prompts == []


async def test_a_failing_own_llm_fails_the_turn_without_the_deployers_key_or_counting_it(
    make_client: ClientFactory, own_llm: FakeLLMService, settings: Settings
):
    own_llm.llm = FakeLLM(LLMError("402 Payment Required: insufficient balance"), REPLY)
    deployers = FakeLLM(REPLY)
    one_turn = replace(settings, usage_limits=UsageLimits(turns_per_hour=1))
    client = make_client(deployers, settings=one_turn)
    conversation_id = await start_conversation(client)

    failed = await send_turn(client, conversation_id, "在吗", own_llm=LLM)
    again = await send_turn(client, conversation_id, "在吗", own_llm=LLM)

    assert failed[-1]["type"] == "error"
    assert "你的LLM密钥调用失败" in failed[-1]["message"]
    assert "402 Payment Required" in failed[-1]["message"]
    assert deployers.keys == []
    # The next turn goes on. Turns on an own LLM never count, so with the limit of one this
    # does not show the failed turn was given back (test_rate_limit does).
    assert again[-1]["type"] == "done"
    messages = await client.get(f"/api/conversations/{conversation_id}/messages")
    assert len(messages.json()) == 2


async def test_a_turn_runs_on_the_llm_it_brings_not_one_kept_on_the_server(
    make_client: ClientFactory, own_llm: FakeLLMService
):
    deployers = FakeLLM(REPLY)
    client = make_client(deployers)
    await keep_llm(client)

    await send_turn(client, await start_conversation(client), "在吗")

    assert deployers.keys == [DEPLOYER_KEY]
    assert own_llm.llm.keys == []


async def test_own_keys_are_kept_encrypted(make_client: ClientFactory, settings: Settings):
    await keep_llm(make_client(FakeLLM()))

    with sqlite3.connect(settings.database_path) as db:
        [row] = db.execute("SELECT * FROM own_keys").fetchall()
    assert not any(isinstance(v, (str, bytes)) and MINE.encode() in (
        v.encode() if isinstance(v, str) else v) for v in row)


async def test_without_a_secret_key_no_one_can_bring_their_own(
    make_client: ClientFactory, settings: Settings, own_llm: FakeLLMService
):
    client = make_client(FakeLLM(), settings=replace(settings, secret_key=None))

    listed = await client.get("/api/account/keys")
    saved = await keep_llm(client)

    assert listed.json()["available"] is False
    assert saved.status_code == 404
    assert "没有开放" in saved.json()["detail"]
    assert own_llm.checked == []


async def test_trying_needs_a_plausible_key(make_client: ClientFactory, own_llm: FakeLLMService):
    client = make_client(FakeLLM())

    for bad in ({"api_key": "short"}, {"api_key": "has space in it"}, {"model": ""},
                {"protocol": "grpc"}):
        assert (await check_llm(client, **bad)).status_code == 422, bad
    assert own_llm.checked == []


async def test_a_call_uses_the_users_own_llm(
    make_client: ClientFactory, own_llm: FakeLLMService, speech: FakeSpeech, browser: Browser
):
    own_llm.llm = FakeLLM(REPLY)
    deployers = FakeLLM()
    client = make_client(deployers)
    await keep_llm(client)
    await browser.call(client, conversation_id=await start_conversation(client))
    await browser.connect()

    await speech.stts[-1].hear("你好")
    messages = await browser.turn()

    assert messages[-1]["type"] == "done"
    assert own_llm.llm.keys == [MINE]
    assert deployers.keys == []


@pytest.mark.parametrize(
    "base_url",
    ["http://llm.example.com/v1", "https://127.0.0.1:8000/v1", "https://localhost/v1",
     "https://[::1]/v1", "https://169.254.169.254/latest", "https://10.0.0.8/v1"],
)
async def test_a_public_deployment_tries_only_llms_on_the_public_internet(base_url: str):
    service = ProviderLLMService(public_only=True)
    try:
        with pytest.raises(LLMError, match="https|公网地址"):
            await service.check(LLMSettings(base_url, MINE, "m"))
    finally:
        await service.aclose()


class FakeNetwork(httpcore.AsyncNetworkBackend):
    """Records where it was asked to connect, and connects nowhere."""

    def __init__(self) -> None:
        self.connected: list[str] = []

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):  # type: ignore[override]
        self.connected.append(host)
        raise httpcore.ConnectError("fake network")


async def test_every_connection_to_an_own_llm_goes_to_the_public_address_it_checked():
    answers = [["93.184.216.34"], ["127.0.0.1"]]  # the name is rebound after the first check

    async def resolver(host: str, port: int) -> list[str]:
        return answers.pop(0)

    network = FakeNetwork()
    backend = PublicOnlyBackend(network, resolver)

    with pytest.raises(httpcore.ConnectError, match="fake network"):
        await backend.connect_tcp("llm.example.com", 443)
    with pytest.raises(httpcore.ConnectError, match="不是公网地址"):
        await backend.connect_tcp("llm.example.com", 443)

    assert network.connected == ["93.184.216.34"]  # the checked address, never the name


async def test_a_public_deployment_never_reaches_a_private_address_on_a_kept_own_llm():
    service = ProviderLLMService(public_only=True)
    llm = service.open(LLMSettings("https://localhost:9/v1", MINE, "m"))  # as if kept earlier
    try:
        with pytest.raises(LLMError, match="不是公网地址"):
            async for _ in llm.stream([ChatMessage("user", "hi")]):
                pass
    finally:
        await service.aclose()
