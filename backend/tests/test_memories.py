"""Memory, driven through the memories module's interface: what a user tells any of the
characters is written down in the background, found again in later turns by every
character of that user's (as hearsay when it was told to someone else, ADR-0002), and
can be listed, deleted and cleared; no user ever reaches another's."""

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from eidolon.characters import Character, load_characters
from eidolon import memory
from eidolon.memory import Memories
from eidolon.store import Conversation, Message, Segment, Store
from tests.conftest import CharacterConfig
from tests.fakes import FakeBackgroundLLM, FakeEmbedder, FakeReranker
from tests.test_shared_memory import CAT, TRIP, memorized

NOW = datetime(2026, 9, 25, 3, 0, tzinfo=UTC)
TZ = "Asia/Shanghai"


class World:
    """A store with users and conversations for the memories module to remember them by."""

    def __init__(self, store: Store, characters: dict[str, Character]) -> None:
        self.store = store
        self.characters = characters
        self.producer = store.create_user("producer").id

    def conversation(self, character_id: str, user_id: str | None = None) -> Conversation:
        return self.store.create_conversation(user_id or self.producer, character_id)

    def reply(self, conversation: Conversation, text: str) -> Message:
        return self.store.add_turn(conversation.id, text, [Segment("はいっ", "好的")])


@pytest.fixture
async def world(tmp_path: Path, characters: CharacterConfig) -> AsyncIterator[World]:
    store = Store(tmp_path / "eidolon.db")
    yield World(store, load_characters(characters.path))
    store.close()


MemoriesFactory = Callable[..., Memories]


@pytest.fixture
async def make_memories(tmp_path: Path, world: World) -> AsyncIterator[MemoriesFactory]:
    """Memories on the world's database; with a background model, embedder and reranker
    unless told otherwise (`off=True`)."""
    made: list[Memories] = []

    def factory(
        *replies: str | Exception,
        off: bool = False,
        background_llm: FakeBackgroundLLM | None = None,
        embedder: FakeEmbedder | None = None,
        reranker: FakeReranker | None = None,
    ) -> Memories:
        memories = (
            Memories(tmp_path / "eidolon.db", world.characters, lambda: NOW)
            if off
            else Memories(
                tmp_path / "eidolon.db", world.characters, lambda: NOW,
                background_llm=background_llm or FakeBackgroundLLM(*replies),
                embedder=embedder or FakeEmbedder(),
                reranker=reranker or FakeReranker("制作人"),
            )
        )
        made.append(memories)
        return memories

    yield factory
    for memories in made:
        await memories.aclose()


async def tell(memories: Memories, world: World, conversation: Conversation, text: str) -> None:
    """Take a turn in which the user says `text`, and write down what it reveals."""
    turn = await memories.begin(conversation, TZ)
    history = world.store.list_messages(conversation.id)
    turn.write_down(history, text, world.reply(conversation, text))


async def find(memories: Memories, conversation: Conversation, text: str) -> str:
    turn = await memories.begin(conversation, TZ)
    return await turn.find(text) or ""


def line_of(section: str, memory: str) -> str:
    return next(line for line in section.splitlines() if memory in line)


async def test_what_the_user_told_mano_reaches_kogane_as_hearsay(
    world: World, make_memories: MemoriesFactory
):
    memories = make_memories(memorized(CAT))

    await tell(memories, world, world.conversation("mano"), "我家的猫叫小白哦")
    section = await find(memories, world.conversation("kogane"), "你知道我家的猫吗？")

    line = line_of(section, CAT)
    assert "櫻木真乃" in line and "转述" in line
    assert "（2026年9月25日，制作人对櫻木真乃说的" in line


async def test_a_memory_told_to_the_character_herself_is_not_hearsay(
    world: World, make_memories: MemoriesFactory
):
    memories = make_memories(memorized(CAT))

    await tell(memories, world, world.conversation("mano"), "我家的猫叫小白哦")
    section = await find(memories, world.conversation("mano"), "你还记得我家的猫吗？")

    line = line_of(section, CAT)
    assert "对你说的" in line
    assert "转述" not in line


async def test_a_memory_told_to_a_character_since_removed_is_hearsay_from_another_idol(
    tmp_path: Path, world: World, make_memories: MemoriesFactory
):
    earlier = make_memories(memorized(CAT))
    await tell(earlier, world, world.conversation("mano"), "我家的猫叫小白哦")
    await earlier.entries(world.producer)  # written down
    without_mano = {"kogane": world.characters["kogane"]}
    memories = Memories(
        tmp_path / "eidolon.db", without_mano, lambda: NOW, background_llm=FakeBackgroundLLM(),
        embedder=FakeEmbedder(), reranker=FakeReranker("制作人"),
    )

    section = await find(memories, world.conversation("kogane"), "你知道我家的猫吗？")
    [cat] = await memories.entries(world.producer)
    await memories.aclose()

    assert "听事务所的另一位偶像说" in line_of(section, CAT)
    assert (cat.source_character_id, cat.source_character_name) == ("mano", None)


async def test_one_users_memories_never_reach_another_user(
    world: World, make_memories: MemoriesFactory
):
    reranker = FakeReranker("猫")
    memories = make_memories(memorized(CAT), memorized("制作人喜欢狗"), reranker=reranker)
    friend = world.store.create_user("friend").id

    await tell(memories, world, world.conversation("mano"), "我家的猫叫小白")
    await tell(memories, world, world.conversation("mano", friend), "我喜欢狗")
    section = await find(memories, world.conversation("kogane", friend), "你知道我家的猫吗？")

    assert CAT not in section and "制作人喜欢狗" in section
    assert not any(CAT in doc for _, docs in reranker.calls for doc in docs)
    assert [m.text for m in await memories.entries(friend)] == ["制作人喜欢狗"]


async def test_the_background_model_reads_the_exchange_and_what_is_already_remembered(
    world: World, make_memories: MemoriesFactory
):
    background = FakeBackgroundLLM(memorized(CAT), memorized(CAT, TRIP))
    memories = make_memories(background_llm=background)
    conversation = world.conversation("mano")

    await tell(memories, world, conversation, "我家的猫叫小白哦")
    await tell(memories, world, conversation, "下周六我要去北海道出差")
    listed = await memories.entries(world.producer)

    first, second = ("\n".join(m.content for m in p) for p in background.prompts)
    assert "我家的猫叫小白哦" in first and "櫻木真乃" in first
    assert "2026年9月25日" in first  # so relative dates can be written down as dates
    assert "我家的猫叫小白哦" in second and "下周六我要去北海道出差" in second
    assert CAT in second.split("# 制作人和")[0]  # already remembered, not written down again
    # Written down twice, remembered once, newest first.
    assert [m.text for m in listed] == [TRIP, CAT]


async def test_irrelevant_memories_are_not_found(world: World, make_memories: MemoriesFactory):
    memories = make_memories(memorized(CAT), reranker=FakeReranker("北海道", others=0.001))

    await tell(memories, world, world.conversation("mano"), "我家的猫叫小白哦")

    assert await find(memories, world.conversation("kogane"), "北海道に行ったことある？") == ""


async def test_only_the_most_relevant_few_are_found(world: World, make_memories: MemoriesFactory):
    told = [f"制作人喜欢第{i}种点心" for i in range(1, 6)]
    memories = make_memories(memorized(*told))

    await tell(memories, world, world.conversation("mano"), "我喜欢好多点心")
    section = await find(memories, world.conversation("mano"), "你知道我喜欢什么点心吗？")

    assert sum(t in section for t in told) == 3


@pytest.mark.parametrize(
    "failure", [RuntimeError("background model is down"), "好的，我记住了", '{"memories": "猫"}']
)
async def test_a_failed_extraction_writes_nothing_down(
    world: World, make_memories: MemoriesFactory, failure: str | Exception
):
    memories = make_memories(failure)

    await tell(memories, world, world.conversation("mano"), "我家的猫叫小白哦")

    assert await memories.entries(world.producer) == []


async def test_nothing_is_found_while_the_embedder_is_down(
    world: World, make_memories: MemoriesFactory
):
    embedder = FakeEmbedder()
    memories = make_memories(memorized(CAT), embedder=embedder)
    await tell(memories, world, world.conversation("mano"), "我家的猫叫小白哦")
    embedder.down = True

    assert await find(memories, world.conversation("kogane"), "你知道我家的猫吗？") == ""


async def test_a_deleted_memory_is_found_no_more(world: World, make_memories: MemoriesFactory):
    background = FakeBackgroundLLM(memorized(CAT, TRIP))
    memories = make_memories(background_llm=background)
    await tell(memories, world, world.conversation("mano"), "我家的猫叫小白，下周六去北海道")
    cat = next(m for m in await memories.entries(world.producer) if m.text == CAT)

    assert await memories.delete(world.producer, cat.id)

    assert [m.text for m in await memories.entries(world.producer)] == [TRIP]
    kogane = world.conversation("kogane")
    section = await find(memories, kogane, "你知道我家的猫吗？")
    assert TRIP in section and CAT not in section
    # Nor is the background model told it is still remembered.
    await tell(memories, world, kogane, "对了")
    await memories.entries(world.producer)
    assert CAT not in "\n".join(m.content for m in background.prompts[-1])


async def test_deleting_a_memory_that_is_gone_or_another_users_deletes_nothing(
    world: World, make_memories: MemoriesFactory
):
    memories = make_memories(memorized(CAT))
    friend = world.store.create_user("friend").id
    await tell(memories, world, world.conversation("mano"), "我家的猫叫小白哦")
    [cat] = await memories.entries(world.producer)

    assert not await memories.delete(friend, cat.id)
    await memories.clear(friend)
    assert await memories.entries(world.producer) == [cat]

    assert await memories.delete(world.producer, cat.id)
    assert not await memories.delete(world.producer, cat.id)


async def test_clearing_forgets_everything(world: World, make_memories: MemoriesFactory):
    memories = make_memories(memorized(CAT), memorized(TRIP))
    conversation = world.conversation("mano")
    await tell(memories, world, conversation, "我家的猫叫小白哦")
    await tell(memories, world, conversation, "下周六我要去北海道出差")

    await memories.clear(world.producer)

    assert await memories.entries(world.producer) == []
    assert await find(memories, world.conversation("kogane"), "你知道我家的猫吗？") == ""


async def test_clearing_waits_for_what_is_still_being_written_down(
    world: World, make_memories: MemoriesFactory
):
    """A turn's memories are written in the background; clearing right after the turn
    must not let them turn up afterwards."""
    memories = make_memories(memorized(CAT))
    await tell(memories, world, world.conversation("mano"), "我家的猫叫小白哦")

    await memories.clear(world.producer)

    assert await memories.entries(world.producer) == []


async def test_what_is_written_down_too_slowly_to_wait_for_is_still_forgotten(
    world: World, make_memories: MemoriesFactory, monkeypatch: pytest.MonkeyPatch
):
    """Clearing waits for what is being written down only a while; whatever the turns
    before the clearing write down after that is dropped rather than turning up again."""
    gate = asyncio.Event()
    memories = make_memories(background_llm=FakeBackgroundLLM(memorized(CAT), gate=gate))
    await tell(memories, world, world.conversation("mano"), "我家的猫叫小白哦")
    monkeypatch.setattr(memory, "SETTLE_TIMEOUT", 0.01)

    await memories.clear(world.producer)
    gate.set()  # the background model answers at last
    monkeypatch.setattr(memory, "SETTLE_TIMEOUT", 5.0)

    assert await memories.entries(world.producer) == []


async def test_with_memory_off_turns_neither_find_nor_write_down_but_users_still_manage_theirs(
    world: World, make_memories: MemoriesFactory
):
    """Memories kept while memory was on can still be seen and deleted once it is off."""
    kept = make_memories(memorized(CAT, TRIP))
    await tell(kept, world, world.conversation("mano"), "我家的猫叫小白，下周六去北海道")
    await kept.entries(world.producer)
    memories = make_memories(off=True)

    assert await find(memories, world.conversation("kogane"), "你知道我家的猫吗？") == ""
    await tell(memories, world, world.conversation("kogane"), "我最近在学吉他")
    listed = await memories.entries(world.producer)
    assert [m.text for m in listed] == [TRIP, CAT]  # newest first

    cat = next(m for m in listed if m.text == CAT)
    assert await memories.delete(world.producer, cat.id)
    assert [m.text for m in await memories.entries(world.producer)] == [TRIP]
    await memories.clear(world.producer)
    assert await memories.entries(world.producer) == []


async def test_memories_are_embedded_without_a_title(world: World, make_memories: MemoriesFactory):
    embedder = FakeEmbedder()
    memories = make_memories(memorized(CAT), embedder=embedder)

    await tell(memories, world, world.conversation("mano"), "我家的猫叫小白哦")
    await memories.entries(world.producer)  # written down

    assert embedder.documents == [CAT] and embedder.titles == [None]
