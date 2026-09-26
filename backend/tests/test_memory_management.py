"""Memory management, driven through the memories API: users see every memory the
characters keep about them, labelled with the character it was told to, and can delete
one or all of them; a deleted memory reaches no prompt again. Nobody sees or touches
another user's memories."""

import asyncio

import httpx
import pytest

from eidolon import memory
from tests.conftest import ClientFactory, IssuedKey
from tests.fakes import FakeBackgroundLLM, FakeEmbedder, FakeJudge, FakeLLM, FakeReranker
from tests.test_shared_memory import (
    CAT,
    REPLY,
    TRIP,
    friend_key,  # noqa: F401 (fixture)
    memories_section,
    memorized,
    turn,
)
from tests.test_text_turn import start_conversation


def memory_client(
    make_client: ClientFactory, llm: FakeLLM, *memories: str, **options: object
) -> httpx.AsyncClient:
    """A client whose background model writes down each of `memories` in turn, one per
    turn, and whose reranker finds every memory relevant."""
    return make_client(
        llm, jev=FakeJudge(), embedder=FakeEmbedder(), reranker=FakeReranker("制作人"),
        background_llm=FakeBackgroundLLM(*(memorized(m) for m in memories)), **options,
    )


async def memories(client: httpx.AsyncClient) -> list[dict]:
    res = await client.get("/api/memories")
    assert res.status_code == 200, res.text
    return res.json()


async def test_lists_every_memory_with_the_character_it_was_told_to(
    make_client: ClientFactory,
):
    client = memory_client(make_client, FakeLLM(REPLY, REPLY), CAT, TRIP)

    await turn(client, await start_conversation(client, "mano"), "我家的猫叫小白哦")
    await turn(client, await start_conversation(client, "kogane"), "下周六我要去北海道出差")

    listed = await memories(client)  # right away: what was just said is already there
    assert [(m["text"], m["source_character_id"], m["source_character_name"])
            for m in listed] == [
        (TRIP, "kogane", "月岡恋鐘"),  # newest first
        (CAT, "mano", "櫻木真乃"),
    ]
    assert all(set(m) == {"id", "text", "source_character_id", "source_character_name",
                          "created_at"} for m in listed)


async def test_a_deleted_memory_reaches_no_prompt(make_client: ClientFactory):
    llm, background = FakeLLM(REPLY, REPLY, REPLY), FakeBackgroundLLM(memorized(CAT, TRIP))
    client = make_client(
        llm, jev=FakeJudge(), embedder=FakeEmbedder(), reranker=FakeReranker("制作人"),
        background_llm=background,
    )
    await turn(client, await start_conversation(client, "mano"), "我家的猫叫小白，下周六去北海道")
    cat = next(m for m in await memories(client) if m["text"] == CAT)

    res = await client.delete(f"/api/memories/{cat['id']}")

    assert res.status_code == 204
    assert [m["text"] for m in await memories(client)] == [TRIP]
    await turn(client, await start_conversation(client, "kogane"), "你知道我家的猫吗？")
    section = memories_section(llm.prompts[-1][0].content)
    assert TRIP in section and CAT not in section
    # Nor is the background model told it is still remembered.
    assert CAT not in "\n".join(m.content for m in background.prompts[-1])


async def test_deleting_a_memory_that_is_gone_is_not_found(make_client: ClientFactory):
    client = memory_client(make_client, FakeLLM(REPLY), CAT)
    await turn(client, await start_conversation(client, "mano"), "我家的猫叫小白哦")
    [cat] = await memories(client)

    assert (await client.delete(f"/api/memories/{cat['id']}")).status_code == 204
    res = await client.delete(f"/api/memories/{cat['id']}")

    assert res.status_code == 404
    assert res.json()["detail"] == "记忆不存在"


async def test_clearing_forgets_everything(make_client: ClientFactory):
    llm = FakeLLM(REPLY, REPLY, REPLY)
    client = memory_client(make_client, llm, CAT, TRIP)
    conversation_id = await start_conversation(client, "mano")
    await turn(client, conversation_id, "我家的猫叫小白哦")
    await turn(client, conversation_id, "下周六我要去北海道出差")

    res = await client.delete("/api/memories")

    assert res.status_code == 204
    assert await memories(client) == []
    await turn(client, await start_conversation(client, "kogane"), "你知道我家的猫吗？")
    assert memories_section(llm.prompts[-1][0].content) == ""


async def test_clearing_waits_for_what_is_still_being_written_down(
    make_client: ClientFactory,
):
    """A turn's memories are written in the background; clearing right after the turn
    must not let them turn up afterwards."""
    client = memory_client(make_client, FakeLLM(REPLY), CAT)
    await turn(client, await start_conversation(client, "mano"), "我家的猫叫小白哦")

    assert (await client.delete("/api/memories")).status_code == 204

    assert await memories(client) == []


async def test_what_is_written_down_too_slowly_to_wait_for_is_still_forgotten(
    make_client: ClientFactory, monkeypatch: pytest.MonkeyPatch
):
    """Clearing waits for what is being written down only a while; whatever the turns
    before the clearing write down after that is dropped rather than turning up again."""
    gate = asyncio.Event()
    client = make_client(
        FakeLLM(REPLY), jev=FakeJudge(), embedder=FakeEmbedder(),
        reranker=FakeReranker("制作人"), background_llm=FakeBackgroundLLM(memorized(CAT), gate=gate),
    )
    await turn(client, await start_conversation(client, "mano"), "我家的猫叫小白哦")
    monkeypatch.setattr(memory, "SETTLE_TIMEOUT", 0.01)

    assert (await client.delete("/api/memories")).status_code == 204
    gate.set()  # the background model answers at last
    monkeypatch.setattr(memory, "SETTLE_TIMEOUT", 5.0)

    assert await memories(client) == []


async def test_users_see_and_touch_only_their_own_memories(
    make_client: ClientFactory, producer_key: IssuedKey, friend_key: IssuedKey  # noqa: F811
):
    producer = memory_client(make_client, FakeLLM(REPLY), CAT, key=producer_key.secret)
    friend = memory_client(make_client, FakeLLM(REPLY), "制作人喜欢狗", key=friend_key.secret)
    await turn(producer, await start_conversation(producer, "mano"), "我家的猫叫小白")
    await turn(friend, await start_conversation(friend, "mano"), "我喜欢狗")
    [cat] = await memories(producer)

    assert [m["text"] for m in await memories(friend)] == ["制作人喜欢狗"]
    res = await friend.delete(f"/api/memories/{cat['id']}")
    assert res.status_code == 404
    assert (await friend.delete("/api/memories")).status_code == 204

    assert [m["text"] for m in await memories(producer)] == [CAT]


async def test_the_memories_api_needs_an_access_key(make_client: ClientFactory):
    client = make_client(FakeLLM(), key=None)

    for method, path in [("GET", "/api/memories"), ("DELETE", "/api/memories"),
                         ("DELETE", "/api/memories/1")]:
        res = await client.request(method, path)
        assert res.status_code == 401, (method, path)


async def test_without_memory_there_is_nothing_to_list(make_client: ClientFactory):
    """Memory is off without retrieval; the page still works, empty."""
    client = make_client(FakeLLM(REPLY))
    await turn(client, await start_conversation(client, "mano"), "我家的猫叫小白哦")

    assert await memories(client) == []
    assert (await client.delete("/api/memories")).status_code == 204
