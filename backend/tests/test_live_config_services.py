"""The live configuration of the services besides the chat model (ADR-0013): the memory
model, speech synthesis and recognition, the judge model with its thresholds, and the
reranker's thresholds. Each change is tried before it is kept (the thresholds are not),
then holds for the next turn or call, while calls already connected keep what they
connected with. What cannot be changed in the admin console is only shown. The clients
are made by a fake `ServiceClients`, the speech services' keys tried on `FakeSpeech`."""

import asyncio
from collections.abc import Callable
from dataclasses import replace

import httpx
import pytest

from eidolon.assembly import Backend
from eidolon.config import (
    DEFAULT_FISH_AUDIO_MODEL,
    CloudflareJudgeSettings,
    JevSettings,
    LLMSettings,
    RerankSettings,
    Settings,
    SttKey,
)
from tests.browser import Browser, open_browser, until_gone
from tests.conftest import ClientFactory
from tests.fakes import (
    DEPLOYER_FISH_KEY,
    DEPLOYER_KEY,
    DEPLOYER_SONIOX_KEY,
    FakeBackgroundLLM,
    FakeEmbedder,
    FakeIdentityProvider,
    FakeJudge,
    FakeLLM,
    FakeReranker,
    FakeServiceClients,
    FakeSpeech,
)
from tests.test_live_config import CONFIG, NEW, NEW_SHOWN, REPLY, admin_client, start
from tests.test_text_turn import send_turn, start_conversation

MEMORY_LLM = "/api/admin/config/memory_llm"
MEMORY_KEY = "sk-memory-key-4321"
NEW_MEMORY = NEW | {"api_key": MEMORY_KEY, "model": "memory-model"}
NEW_MEMORY_SETTINGS = LLMSettings(
    "https://llm.example/v1", MEMORY_KEY, "memory-model", "anthropic", 1024
)
ENV_SETTINGS = LLMSettings("http://llm.invalid/v1", DEPLOYER_KEY, "test-model")
CAT = '{"memories": ["制作人养了一只猫"]}'


@pytest.fixture
def admins(settings: Settings) -> Settings:
    return replace(settings, admins=frozenset({("github", "1001")}))


def with_memory(
    make_client: ClientFactory, background: FakeBackgroundLLM, judge: FakeJudge | None = None
):
    """A client factory for backends with memory on, writing down with `background` as
    `.env` has it; turns need what `judge` says (nothing, by default)."""

    def factory(*args, **kwargs) -> httpx.AsyncClient:
        return make_client(
            *args, retrieval_judge=judge or FakeJudge("nothing"), embedder=FakeEmbedder(),
            reranker=FakeReranker(), background_llm=background, **kwargs,
        )

    return factory


async def settle(client: httpx.AsyncClient) -> list[dict]:
    """The user's memories, once what their turns are writing down is written."""
    res = await client.get("/api/memories")
    assert res.status_code == 200, res.text
    return res.json()


async def test_a_saved_memory_model_writes_down_the_next_turns_memories_until_restored(
    make_client: ClientFactory, admins: Settings, github: FakeIdentityProvider
):
    clients = FakeServiceClients(FakeLLM(REPLY, REPLY, REPLY))
    env_background = FakeBackgroundLLM()
    factory = with_memory(make_client, env_background)
    client = await admin_client(factory, admins, github, clients)
    conversation_id = await start_conversation(client)
    before = (await client.get(CONFIG)).json()["memory_llm"]
    await send_turn(client, conversation_id, "早上好")
    await settle(client)

    saved = await client.put(MEMORY_LLM, json=NEW_MEMORY)
    assert saved.status_code == 200, saved.text
    await send_turn(client, conversation_id, "你好")
    await settle(client)
    restored = await client.delete(MEMORY_LLM)
    assert restored.status_code == 200, restored.text
    await send_turn(client, conversation_id, "再见")
    await settle(client)

    assert before["status"] == "env" and before["follows_chat"] is True
    shown = saved.json()["memory_llm"]
    assert shown["status"] == "overridden" and shown["follows_chat"] is False
    assert shown["effective"]["model"] == "memory-model"
    assert shown["effective"]["api_key_last4"] == "4321"
    assert MEMORY_KEY not in saved.text
    assert restored.json()["memory_llm"] == before
    assert len(env_background.prompts) == 1
    assert clients.memory_keys == [MEMORY_KEY, DEPLOYER_KEY]
    assert clients.llm.keys == [DEPLOYER_KEY] * 3  # the chat model is untouched
    assert clients.memory_opened == [NEW_MEMORY_SETTINGS, ENV_SETTINGS]


async def test_unless_set_apart_the_memory_model_follows_the_chat_model_saved(
    make_client: ClientFactory, admins: Settings, github: FakeIdentityProvider
):
    clients = FakeServiceClients(FakeLLM(REPLY, [CAT]))
    env_background = FakeBackgroundLLM()
    factory = with_memory(make_client, env_background)
    client = await admin_client(factory, admins, github, clients)
    conversation_id = await start_conversation(client)

    saved = await client.put("/api/admin/config/chat_llm", json=NEW)
    await send_turn(client, conversation_id, "我养了一只猫")
    memories = await settle(client)

    memory = saved.json()["memory_llm"]
    assert memory["status"] == "env" and memory["follows_chat"] is True
    assert memory["effective"] == NEW_SHOWN
    assert [m["text"] for m in memories] == ["制作人养了一只猫"]
    assert clients.llm.keys == [NEW["api_key"], NEW["api_key"]]
    assert env_background.prompts == []


async def test_a_memory_model_set_apart_in_env_does_not_follow_the_chat_model(
    make_client: ClientFactory, admins: Settings, github: FakeIdentityProvider
):
    clients = FakeServiceClients(FakeLLM(REPLY))
    env_background = FakeBackgroundLLM()
    factory = with_memory(make_client, env_background)
    apart = replace(admins, background_llm=replace(ENV_SETTINGS, model="background-model"))
    client = await admin_client(factory, apart, github, clients)
    conversation_id = await start_conversation(client)

    saved = await client.put("/api/admin/config/chat_llm", json=NEW)
    await send_turn(client, conversation_id, "我养了一只猫")
    await settle(client)

    memory = saved.json()["memory_llm"]
    assert memory["follows_chat"] is False
    assert memory["effective"]["model"] == "background-model"
    assert len(env_background.prompts) == 1
    assert clients.llm.keys == [NEW["api_key"]]


async def test_a_memory_model_replaced_while_writing_down_is_closed_once_written(
    make_client: ClientFactory, admins: Settings, github: FakeIdentityProvider
):
    clients = FakeServiceClients(FakeLLM(REPLY))
    gate = asyncio.Event()
    clients.background = FakeBackgroundLLM(CAT, gate=gate)
    client = await admin_client(
        with_memory(make_client, FakeBackgroundLLM()), admins, github, clients
    )
    conversation_id = await start_conversation(client)
    assert (await client.put(MEMORY_LLM, json=NEW_MEMORY)).status_code == 200
    await send_turn(client, conversation_id, "我养了一只猫")  # written down after the turn

    other = NEW_MEMORY | {"api_key": "sk-other-key-9999"}
    assert (await client.put(MEMORY_LLM, json=other)).status_code == 200
    closed_while_writing = list(clients.closed)
    gate.set()
    memories = await settle(client)

    assert closed_while_writing == []
    assert [m["text"] for m in memories] == ["制作人养了一只猫"]
    assert clients.closed == [NEW_MEMORY_SETTINGS]


async def until(done: Callable[[], object]) -> None:
    """Wait, a while at most, for `done` to come true, as what a call let go of closes."""
    for _ in range(100):
        if done():
            return
        await asyncio.sleep(0.02)


def backend_of(client: httpx.AsyncClient) -> Backend:
    return client._transport.app.state.backend  # pyright: ignore[reportAttributeAccessIssue]


TTS = "/api/admin/config/tts"
STT = "/api/admin/config/stt"
NEW_FISH = "new-fish-key-0001"
NEW_DASHSCOPE = "new-dashscope-key-0002"


async def test_speech_saved_during_a_call_holds_from_the_next_call(
    make_client: ClientFactory,
    admins: Settings,
    github: FakeIdentityProvider,
    speech: FakeSpeech,
    browser: Browser,
):
    speech.regions[NEW_DASHSCOPE] = "singapore"
    clients = FakeServiceClients(FakeLLM(REPLY, REPLY))
    client = await admin_client(make_client, admins, github, clients)
    conversation_id = await start_conversation(client)
    await browser.call(client, conversation_id=conversation_id)
    await browser.connect()
    assert browser.pc_id is not None

    tts = await client.put(TTS, json={"api_key": NEW_FISH, "model": "s1"})
    stt = await client.put(STT, json={"provider": "bailian", "api_key": NEW_DASHSCOPE})
    assert tts.status_code == 200, tts.text
    assert stt.status_code == 200, stt.text
    await speech.stts[-1].hear("早上好")
    await browser.turn()
    await browser.close()
    await until_gone(client, browser.pc_id)
    async with open_browser() as again:
        await again.call(client, conversation_id=conversation_id)
        await again.connect()

    assert [(t.api_key, t.model) for t in speech.ttss] == [
        (DEPLOYER_FISH_KEY, DEFAULT_FISH_AUDIO_MODEL), (NEW_FISH, "s1")
    ]
    assert [s.key for s in speech.stts] == [
        SttKey("soniox", DEPLOYER_SONIOX_KEY), SttKey("bailian", NEW_DASHSCOPE, "singapore")
    ]
    assert speech.checked == [("tts", NEW_FISH), ("bailian", NEW_DASHSCOPE)]
    shown = stt.json()
    assert shown["tts"]["effective"] == {"api_key_last4": "0001", "model": "s1"}
    assert shown["stt"]["effective"] == {
        "provider": "bailian", "soniox_api_key_last4": DEPLOYER_SONIOX_KEY[-4:],
        "dashscope_api_key_last4": "0002", "region": "singapore",
    }
    assert NEW_FISH not in stt.text and NEW_DASHSCOPE not in stt.text


async def test_a_speech_key_that_fails_its_try_is_not_saved(
    make_client: ClientFactory, admins: Settings, github: FakeIdentityProvider, speech: FakeSpeech
):
    speech.rejects[NEW_FISH] = "401 invalid fish key"
    speech.rejects[NEW_DASHSCOPE] = "InvalidApiKey"
    client = await admin_client(make_client, admins, github, FakeServiceClients())

    tts = await client.put(TTS, json={"api_key": NEW_FISH, "model": "s1"})
    stt = await client.put(STT, json={"provider": "bailian", "api_key": NEW_DASHSCOPE})
    no_key = await client.put(STT, json={"provider": "bailian"})

    for res, said in ((tts, "401 invalid fish key"), (stt, "InvalidApiKey"), (no_key, "key")):
        assert res.status_code == 422, said
        assert said in res.json()["detail"], said
    shown = (await client.get(CONFIG)).json()
    assert shown["tts"]["status"] == shown["stt"]["status"] == "env"


async def test_a_speech_override_that_fails_as_the_server_starts_falls_back_to_env(
    make_client: ClientFactory, admins: Settings, github: FakeIdentityProvider, speech: FakeSpeech
):
    first = await admin_client(make_client, admins, github, FakeServiceClients())
    assert (await first.put(TTS, json={"api_key": NEW_FISH, "model": "s1"})).status_code == 200

    speech.rejects[NEW_FISH] = "401 key revoked"
    restarted = await admin_client(make_client, admins, github, FakeServiceClients())
    await start(restarted)
    lease = backend_of(restarted).config.lease()
    lease.release()

    shown = (await restarted.get(CONFIG)).json()["tts"]
    assert shown["status"] == "failed" and "401 key revoked" in shown["failure"]
    assert (lease.keys.tts, lease.keys.tts_model) == (DEPLOYER_FISH_KEY, DEFAULT_FISH_AUDIO_MODEL)


JUDGE = "/api/admin/config/judge"
JUDGE_THRESHOLDS = "/api/admin/config/judge_thresholds"
JEV_KEY = "env-jev-key-1111"
CF_TOKEN = "cf-token-2222"
CLOUDFLARE = {
    "provider": "cloudflare", "api_key": CF_TOKEN, "model": "clef-flash",
    "account_id": "account-1", "emotion_timeout": 1.5,
}


@pytest.fixture
def judged(admins: Settings) -> Settings:
    """Retrieval and emotions judged by Jev, as `.env` has it."""
    return replace(admins, judge=JevSettings(JEV_KEY))


def with_retrieval(make_client: ClientFactory):
    """A client factory for backends that retrieve, with the judge model `.env` has."""

    def factory(*args, **kwargs) -> httpx.AsyncClient:
        return make_client(*args, embedder=FakeEmbedder(), reranker=FakeReranker(), **kwargs)

    return factory


async def test_a_saved_judge_model_judges_the_next_turn_while_a_call_keeps_its_own(
    make_client: ClientFactory,
    judged: Settings,
    github: FakeIdentityProvider,
    speech: FakeSpeech,
    browser: Browser,
):
    clients = FakeServiceClients(FakeLLM(REPLY, REPLY, REPLY))
    client = await admin_client(with_retrieval(make_client), judged, github, clients)
    conversation_id = await start_conversation(client)
    await browser.call(client, conversation_id=conversation_id)
    await browser.connect()
    assert browser.pc_id is not None

    saved = await client.put(JUDGE, json=CLOUDFLARE)
    assert saved.status_code == 200, saved.text
    await speech.stts[-1].hear("早上好")
    await browser.turn()
    await browser.next_server_message("emotion")
    await send_turn(client, conversation_id, "你好")
    asked = list(clients.judge.asked)
    closed_during_call = list(clients.judges_closed)
    await browser.close()
    await until_gone(client, browser.pc_id)
    await until(lambda: clients.judges_closed)

    assert asked == [
        (CF_TOKEN, "check"), (CF_TOKEN, "turn"), (JEV_KEY, "emotion"), (CF_TOKEN, "turn")
    ]
    assert clients.judges_opened == [
        JevSettings(JEV_KEY), CloudflareJudgeSettings(CF_TOKEN, "account-1", "clef-flash")
    ]
    assert closed_during_call == []
    assert clients.judges_closed == [JevSettings(JEV_KEY)]  # once the call was over
    shown = saved.json()["judge"]
    assert shown["status"] == "overridden"
    assert shown["effective"] == {k: v for k, v in CLOUDFLARE.items() if k != "api_key"} | {
        "api_key_last4": "2222"
    }


async def test_a_judge_model_that_fails_its_try_is_not_saved(
    make_client: ClientFactory, judged: Settings, github: FakeIdentityProvider
):
    clients = FakeServiceClients()
    clients.rejects[CF_TOKEN] = "Cloudflare Workers AI 返回 401"
    client = await admin_client(with_retrieval(make_client), judged, github, clients)

    rejected = await client.put(JUDGE, json=CLOUDFLARE)
    keyless = await client.put(JUDGE, json={k: v for k, v in CLOUDFLARE.items() if k != "api_key"})

    assert rejected.status_code == 422 and "返回 401" in rejected.json()["detail"]
    assert keyless.status_code == 422 and "key" in keyless.json()["detail"]
    assert (await client.get(CONFIG)).json()["judge"]["status"] == "env"
    assert clients.judges_closed == [CloudflareJudgeSettings(CF_TOKEN, "account-1", "clef-flash")]


async def test_the_recall_threshold_saved_judges_the_next_turn_until_the_model_changes(
    make_client: ClientFactory, judged: Settings, github: FakeIdentityProvider
):
    clients = FakeServiceClients(FakeLLM(REPLY, REPLY, REPLY))
    clients.judge.retrieval = {"needs_retrieval": 0.1, "recall": 0.6, "about_producer": 0.1}
    client = await admin_client(with_retrieval(make_client), judged, github, clients)
    conversation_id = await start_conversation(client)
    await send_turn(client, conversation_id, "那次比赛怎么样")  # Jev's 0.5: recalled

    saved = await client.put(JUDGE_THRESHOLDS, json={"recall": 0.7, "emotion": 0.5})
    assert saved.status_code == 200, saved.text
    await send_turn(client, conversation_id, "那次比赛怎么样")  # 0.7: not recalled
    changed = await client.put(JUDGE, json={
        "provider": "jev", "model": "typesafe/jev-1.14", "emotion_timeout": 1.5
    })
    assert changed.status_code == 200, changed.text
    await send_turn(client, conversation_id, "那次比赛怎么样")  # Jev's 0.5 again

    offered = [[t.name for t in tools] for tools in clients.llm.tools]
    assert offered == [[], ["recall_story"], []]
    thresholds = saved.json()["judge_thresholds"]
    assert thresholds["status"] == "overridden"
    assert thresholds["env"] == {"recall": 0.5, "emotion": 0.5}
    assert thresholds["effective"] == {"recall": 0.7, "emotion": 0.5}
    assert changed.json()["judge_thresholds"]["status"] == "env"
    assert changed.json()["judge_thresholds"]["model"] == "typesafe/jev-1.14"


RERANK = "/api/admin/config/rerank"


async def test_the_memory_threshold_saved_leaves_out_what_the_next_turn_finds(
    make_client: ClientFactory, admins: Settings, github: FakeIdentityProvider
):
    clients = FakeServiceClients(FakeLLM(REPLY, REPLY, REPLY))
    reranked = replace(admins, rerank=RerankSettings("sk-rerank"))
    factory = with_memory(make_client, FakeBackgroundLLM(CAT), FakeJudge("memories"))
    client = await admin_client(factory, reranked, github, clients)
    conversation_id = await start_conversation(client)
    await send_turn(client, conversation_id, "我养了一只猫")
    await settle(client)

    await send_turn(client, conversation_id, "猫怎么样")
    saved = await client.put(RERANK, json={"references": 0.3, "memories": 0.95})
    assert saved.status_code == 200, saved.text
    await send_turn(client, conversation_id, "猫怎么样")

    found = ["制作人养了一只猫" in prompt[0].content for prompt in clients.llm.prompts]
    assert found == [False, True, False]
    rerank = saved.json()["rerank"]
    assert rerank["model"] == "Qwen/Qwen3-Reranker-0.6B"
    assert rerank["env"] == {"references": 0.3, "memories": 0.01}
    assert rerank["effective"] == {"references": 0.3, "memories": 0.95}


async def test_what_cannot_be_changed_here_is_only_shown_saying_why(
    make_client: ClientFactory, admins: Settings, github: FakeIdentityProvider
):
    client = await admin_client(make_client, admins, github, FakeServiceClients())

    shown = await client.get(CONFIG)
    refused = await client.put("/api/admin/config/secret_key", json={"value": "new"})
    unconfigured = await client.put(JUDGE, json=CLOUDFLARE)

    read_only = {item["name"]: item for item in shown.json()["read_only"]}
    assert set(read_only) == {
        "admins", "secret_key", "oauth", "domain", "webrtc", "backup", "paths", "embedding"
    }
    assert all(item["why"] for item in read_only.values())
    assert read_only["admins"]["value"] == ["github:1001"]
    assert read_only["secret_key"]["value"] is True
    assert admins.secret_key and admins.secret_key not in shown.text
    assert refused.status_code == 403 and "服务器" in refused.json()["detail"]
    assert unconfigured.status_code == 409
    assert "unavailable" in shown.json()["judge"]

