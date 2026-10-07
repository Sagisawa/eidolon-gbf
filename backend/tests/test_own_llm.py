"""Bringing your own LLM: tried once before it is kept, then used for the user's turns,
calls and memories instead of the deployer's. It fails loudly rather than falling back to
the deployer's key, is shown only by its last 4 characters, and is kept encrypted."""

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


async def bring_llm(client: httpx.AsyncClient, **changes: str) -> httpx.Response:
    return await client.put("/api/account/keys/llm", json=LLM | changes)


async def test_an_own_llm_is_tried_then_kept_showing_only_its_last_4_characters(
    make_client: ClientFactory, own_llm: FakeLLMService
):
    client = make_client(FakeLLM())

    saved = await bring_llm(client)
    listed = await client.get("/api/account/keys")

    assert saved.status_code == 200
    assert [s.api_key for s in own_llm.checked] == [MINE]
    shown = {"last4": "1234", "base_url": "https://llm.example.com/v1", "model": "my-model",
             "protocol": "chat-completions"}
    assert saved.json() == shown
    assert listed.json()["available"] is True
    assert listed.json()["keys"] == {"llm": shown}
    assert MINE not in saved.text + listed.text


async def test_an_own_llm_that_fails_its_try_is_not_kept(
    make_client: ClientFactory, own_llm: FakeLLMService
):
    client = make_client(FakeLLM())
    own_llm.rejects[MINE] = "401 Unauthorized: invalid api key"

    res = await bring_llm(client)

    assert res.status_code == 422
    assert "401 Unauthorized" in res.json()["detail"]
    assert (await client.get("/api/account/keys")).json()["keys"] == {}


async def test_the_users_turns_use_their_own_llm(
    make_client: ClientFactory, own_llm: FakeLLMService
):
    deployers = FakeLLM()
    own_llm.llm = FakeLLM(REPLY)
    client = make_client(deployers)
    await bring_llm(client)

    events = await send_turn(client, await start_conversation(client), "在吗")

    assert events[-1]["type"] == "done"
    assert own_llm.llm.keys == [MINE]
    assert own_llm.opened[-1].base_url == "https://llm.example.com/v1"
    assert own_llm.opened[-1].model == "my-model"
    assert deployers.keys == []


async def test_the_users_own_llm_writes_down_their_memories(
    make_client: ClientFactory, own_llm: FakeLLMService
):
    own_llm.llm = FakeLLM(REPLY, [memorized(CAT)])
    deployers_background = FakeBackgroundLLM()
    client = make_client(
        FakeLLM(), jev=FakeJudge(), embedder=FakeEmbedder(), reranker=FakeReranker("制作人"),
        background_llm=deployers_background,
    )
    await bring_llm(client)

    await send_turn(client, await start_conversation(client), "我家的猫叫小白哦")

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
    await bring_llm(client)
    conversation_id = await start_conversation(client)

    failed = await send_turn(client, conversation_id, "在吗")
    again = await send_turn(client, conversation_id, "在吗")

    assert failed[-1]["type"] == "error"
    assert "你的LLM密钥调用失败" in failed[-1]["message"]
    assert "402 Payment Required" in failed[-1]["message"]
    assert deployers.keys == []
    # The next turn goes on. Turns on an own LLM never count, so with the limit of one this
    # does not show the failed turn was given back (test_rate_limit does).
    assert again[-1]["type"] == "done"
    messages = await client.get(f"/api/conversations/{conversation_id}/messages")
    assert len(messages.json()) == 2


async def test_a_turn_on_an_own_llm_that_can_no_longer_be_decrypted_is_refused_uncounted(
    make_client: ClientFactory, own_llm: FakeLLMService, settings: Settings
):
    await bring_llm(make_client(FakeLLM()))
    deployers = FakeLLM(REPLY)
    changed = replace(  # EIDOLON_SECRET_KEY changed since the key was kept
        settings, secret_key="another-secret-key", usage_limits=UsageLimits(turns_per_hour=1)
    )
    client = make_client(deployers, settings=changed)
    conversation_id = await start_conversation(client)

    refused = await client.post(
        f"/api/conversations/{conversation_id}/turns", json={"text": "在吗"}
    )
    await client.delete("/api/account/keys/llm")
    again = await send_turn(client, conversation_id, "在吗")

    assert refused.status_code == 409
    assert "你的LLM密钥调用失败" in refused.json()["detail"]
    assert "保存的密钥无法解密" in refused.json()["detail"]
    assert again[-1]["type"] == "done"  # the refused turn did not count
    assert deployers.keys == [DEPLOYER_KEY]
    assert own_llm.llm.keys == []


async def test_deleting_the_own_llm_goes_back_to_the_deployers(
    make_client: ClientFactory, own_llm: FakeLLMService
):
    deployers = FakeLLM(REPLY)
    client = make_client(deployers)
    await bring_llm(client)

    deleted = await client.delete("/api/account/keys/llm")
    again = await client.delete("/api/account/keys/llm")
    await send_turn(client, await start_conversation(client), "在吗")

    assert deleted.status_code == 204
    assert again.status_code == 404
    assert (await client.get("/api/account/keys")).json()["keys"] == {}
    assert deployers.keys == [DEPLOYER_KEY]
    assert own_llm.llm.keys == []


async def test_other_users_keep_the_deployers_llm(
    make_client: ClientFactory, own_llm: FakeLLMService
):
    deployers = FakeLLM(REPLY)
    await bring_llm(make_client(FakeLLM()))
    friend = make_client(deployers, "friend")

    await send_turn(friend, await start_conversation(friend), "在吗")

    assert deployers.keys == [DEPLOYER_KEY]
    assert (await friend.get("/api/account/keys")).json()["keys"] == {}


async def test_own_keys_are_kept_encrypted(make_client: ClientFactory, settings: Settings):
    await bring_llm(make_client(FakeLLM()))

    with sqlite3.connect(settings.database_path) as db:
        [row] = db.execute("SELECT * FROM own_keys").fetchall()
    assert not any(isinstance(v, (str, bytes)) and MINE.encode() in (
        v.encode() if isinstance(v, str) else v) for v in row)


async def test_without_a_secret_key_no_one_can_bring_their_own(
    make_client: ClientFactory, settings: Settings, own_llm: FakeLLMService
):
    client = make_client(FakeLLM(), settings=replace(settings, secret_key=None))

    listed = await client.get("/api/account/keys")
    saved = await bring_llm(client)

    assert listed.json()["available"] is False
    assert saved.status_code == 404
    assert "没有开放" in saved.json()["detail"]
    assert own_llm.checked == []


async def test_saving_needs_a_plausible_key(make_client: ClientFactory):
    client = make_client(FakeLLM())

    for bad in ({"api_key": "short"}, {"api_key": "has space in it"}, {"model": ""},
                {"protocol": "grpc"}):
        assert (await bring_llm(client, **bad)).status_code == 422, bad


async def test_a_call_uses_the_users_own_llm(
    make_client: ClientFactory, own_llm: FakeLLMService, speech: FakeSpeech, browser: Browser
):
    own_llm.llm = FakeLLM(REPLY)
    deployers = FakeLLM()
    client = make_client(deployers)
    await bring_llm(client)
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
