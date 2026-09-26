"""Shared memory, driven through the text turn API: the background model writes down in
Chinese what the user tells a character; every character of that user's retrieves it,
labelled with the character it was told to, and never any other user's."""

import json
from datetime import UTC, datetime

import httpx
import pytest

from eidolon.config import LLMSettings, Settings
from tests.conftest import Admin, ClientFactory, IssuedKey
from tests.fakes import FakeBackgroundLLM, FakeEmbedder, FakeJudge, FakeLLM, FakeReranker
from tests.test_text_turn import send_turn, start_conversation

REPLY = ["<ja>はいっ</ja><zh>好的</zh>"]
CAT = "制作人家里养了一只叫小白的猫"
TRIP = "制作人10月3日要去北海道出差"


def memorized(*texts: str) -> str:
    return json.dumps({"memories": list(texts)}, ensure_ascii=False)


def memories_section(system: str) -> str:
    return system[system.index("# 关于制作人的记忆") :] if "# 关于制作人的记忆" in system else ""


def fixed_clock() -> datetime:
    return datetime(2026, 9, 25, 3, 0, tzinfo=UTC)


@pytest.fixture
def friend_key(admin: Admin) -> IssuedKey:
    admin.create_user("friend")
    return admin.issue_key("friend")


def as_user(client: httpx.AsyncClient, key: IssuedKey) -> httpx.AsyncClient:
    client.headers["Authorization"] = f"Bearer {key.secret}"
    return client


async def turn(client: httpx.AsyncClient, conversation_id: str, text: str) -> None:
    events = await send_turn(client, conversation_id, text)
    assert events[-1]["type"] == "done", events[-1]


async def test_what_the_user_told_mano_reaches_kogane_as_hearsay(make_client: ClientFactory):
    llm, background = FakeLLM(REPLY, REPLY), FakeBackgroundLLM(memorized(CAT))
    client = make_client(
        llm, jev=FakeJudge(), embedder=FakeEmbedder(), reranker=FakeReranker("猫"),
        background_llm=background,
    )

    await turn(client, await start_conversation(client, "mano"), "我家的猫叫小白哦")
    await turn(client, await start_conversation(client, "kogane"), "你知道我家的猫吗？")

    kogane = llm.prompts[-1]
    memories = memories_section(kogane[0].content)
    assert CAT in memories
    line = next(line for line in memories.splitlines() if CAT in line)
    assert "櫻木真乃" in line and "转述" in line
    # A new conversation carries only what memory retrieves, not the earlier conversation.
    assert [m.role for m in kogane] == ["system", "user"]


async def test_a_memory_told_to_the_character_herself_is_not_hearsay(
    make_client: ClientFactory,
):
    llm = FakeLLM(REPLY, REPLY)
    client = make_client(
        llm, jev=FakeJudge(), embedder=FakeEmbedder(), reranker=FakeReranker("猫"),
        background_llm=FakeBackgroundLLM(memorized(CAT)),
    )

    await turn(client, await start_conversation(client, "mano"), "我家的猫叫小白哦")
    await turn(client, await start_conversation(client, "mano"), "你还记得我家的猫吗？")

    line = next(line for line in memories_section(llm.prompts[-1][0].content).splitlines()
                if CAT in line)
    assert "对你说的" in line
    assert "转述" not in line


async def test_one_users_memories_never_reach_another_user(
    make_client: ClientFactory, producer_key: IssuedKey, friend_key: IssuedKey
):
    llm, reranker = FakeLLM(REPLY, REPLY, REPLY), FakeReranker("猫")
    client = make_client(
        llm, jev=FakeJudge(), embedder=FakeEmbedder(), reranker=reranker,
        background_llm=FakeBackgroundLLM(memorized(CAT), memorized("制作人喜欢狗")),
    )

    await turn(as_user(client, producer_key), await start_conversation(client, "mano"), "我家的猫叫小白")
    await turn(as_user(client, friend_key), await start_conversation(client, "mano"), "我喜欢狗")
    await turn(as_user(client, friend_key), await start_conversation(client, "kogane"), "你知道我家的猫吗？")

    friend = llm.prompts[-1][0].content
    assert CAT not in friend
    assert "制作人喜欢狗" in memories_section(friend)
    assert not any(CAT in doc for doc in reranker.calls[-1][1])


async def test_the_background_model_reads_the_exchange_and_what_is_already_remembered(
    make_client: ClientFactory,
):
    background = FakeBackgroundLLM(memorized(CAT), memorized(CAT, TRIP))
    llm = FakeLLM(REPLY, REPLY, REPLY)
    client = make_client(
        llm, jev=FakeJudge(), embedder=FakeEmbedder(), reranker=FakeReranker("北海道"),
        background_llm=background, clock=fixed_clock,
    )
    conversation_id = await start_conversation(client, "mano")

    await turn(client, conversation_id, "我家的猫叫小白哦")
    await turn(client, conversation_id, "下周六我要去北海道出差")
    await turn(client, await start_conversation(client, "kogane"), "北海道のこと、知っとる？")

    first, second = ("\n".join(m.content for m in p) for p in background.prompts[:2])
    assert "我家的猫叫小白哦" in first and "櫻木真乃" in first
    assert "2026年9月25日" in first  # so relative dates can be written down as dates
    assert "下周六我要去北海道出差" in second
    assert CAT in second  # already remembered, so it is not written down again

    # Written down twice, remembered once, dated the day it was told.
    memories = memories_section(llm.prompts[-1][0].content)
    assert memories.count(CAT) == 1 and memories.count(TRIP) == 1
    assert "（2026年9月25日，制作人对櫻木真乃说的" in memories


async def test_talk_of_the_users_own_life_retrieves_memories_only(
    make_client: ClientFactory,
):
    llm, reranker = FakeLLM(REPLY, REPLY), FakeReranker("猫")
    jev = FakeJudge(answer="memories")
    client = make_client(
        llm, jev=jev, embedder=FakeEmbedder(), reranker=reranker,
        background_llm=FakeBackgroundLLM(memorized(CAT)),
    )

    await turn(client, await start_conversation(client, "mano"), "我家的猫叫小白哦")
    await turn(client, await start_conversation(client, "kogane"), "我家的猫最近总是半夜叫")

    system = llm.prompts[-1][0].content
    assert CAT in memories_section(system)
    assert "# 回忆与资料" not in system
    assert reranker.calls[-1][1] == [CAT]  # the story corpus and facts are not searched


async def test_irrelevant_memories_stay_out_of_the_prompt(make_client: ClientFactory):
    llm = FakeLLM(REPLY, REPLY)
    client = make_client(
        llm, jev=FakeJudge(), embedder=FakeEmbedder(),
        reranker=FakeReranker("北海道", others=0.001),
        background_llm=FakeBackgroundLLM(memorized(CAT)),
    )

    await turn(client, await start_conversation(client, "mano"), "我家的猫叫小白哦")
    await turn(client, await start_conversation(client, "kogane"), "北海道に行ったことある？")

    assert memories_section(llm.prompts[-1][0].content) == ""


async def test_small_talk_retrieves_no_memories(make_client: ClientFactory):
    llm, embedder = FakeLLM(REPLY, REPLY), FakeEmbedder()
    client = make_client(
        llm, jev=FakeJudge(answer="nothing"), embedder=embedder, reranker=FakeReranker(),
        background_llm=FakeBackgroundLLM(memorized(CAT)),
    )

    await turn(client, await start_conversation(client, "mano"), "我家的猫叫小白哦")
    await turn(client, await start_conversation(client, "kogane"), "早上好")

    assert memories_section(llm.prompts[-1][0].content) == ""
    assert embedder.queries == []
    assert embedder.documents == [CAT]  # embedded as it was written down, not when searched


@pytest.mark.parametrize(
    "failure", [RuntimeError("background model is down"), "好的，我记住了", '{"memories": "猫"}']
)
async def test_a_failed_extraction_leaves_the_conversation_alone(
    make_client: ClientFactory, failure: str | Exception
):
    llm = FakeLLM(REPLY, REPLY)
    client = make_client(
        llm, jev=FakeJudge(), embedder=FakeEmbedder(), reranker=FakeReranker(),
        background_llm=FakeBackgroundLLM(failure),
    )
    conversation_id = await start_conversation(client, "mano")

    await turn(client, conversation_id, "我家的猫叫小白哦")
    await turn(client, conversation_id, "你还记得吗？")

    assert memories_section(llm.prompts[-1][0].content) == ""


async def test_memory_needs_retrieval(make_client: ClientFactory):
    """Without retrieval there is nothing to find memories with, so none are written."""
    background = FakeBackgroundLLM(memorized(CAT))
    client = make_client(FakeLLM(REPLY), background_llm=background)

    await turn(client, await start_conversation(client, "mano"), "我家的猫叫小白哦")

    assert background.prompts == []


def test_the_background_model_is_configured_apart_from_the_chat_model(
    monkeypatch: pytest.MonkeyPatch,
):
    for name in ("BASE_URL", "API_KEY", "MODEL", "PROTOCOL", "MAX_TOKENS"):
        monkeypatch.delenv(f"CHAT_LLM_{name}", raising=False)
        monkeypatch.delenv(f"BACKGROUND_LLM_{name}", raising=False)
    monkeypatch.setenv("CHAT_LLM_BASE_URL", "https://chat.example/v1")
    monkeypatch.setenv("CHAT_LLM_API_KEY", "chat-key")
    monkeypatch.setenv("CHAT_LLM_MODEL", "chat-model")

    # Left unset, it is the chat model...
    settings = Settings.from_env()
    assert settings.background_llm == LLMSettings(
        "https://chat.example/v1", "chat-key", "chat-model"
    )

    # ...and each setting can be changed on its own, say a cheaper model on the same service.
    monkeypatch.setenv("BACKGROUND_LLM_MODEL", "cheap-model")
    settings = Settings.from_env()
    assert settings.background_llm == LLMSettings(
        "https://chat.example/v1", "chat-key", "cheap-model"
    )
    assert settings.chat_llm.model == "chat-model"

