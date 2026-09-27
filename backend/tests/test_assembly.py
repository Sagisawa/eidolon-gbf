"""The assembly root: what `build` turns on, given which outside services are at hand.

Retrieval needs Jev, the embedder and the reranker; memory is on only with retrieval,
since only retrieval finds memories again. Turns are taken through the built engine.
"""

import json
from collections.abc import AsyncIterator
from dataclasses import asdict
from datetime import UTC, datetime

import pytest

from eidolon.assembly import Backend, build
from eidolon.config import LLMSettings, Settings
from eidolon.retrieval import RECALL_STORY_TOOL
from tests.fakes import FakeBackgroundLLM, FakeEmbedder, FakeJudge, FakeLLM, FakeReranker

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
REPLY = ["<ja>はいっ</ja><zh>好的</zh>"]
CAT = "制作人家里养了一只叫小白的猫"
ALL = ("jev", "embedder", "reranker")


class Services:
    """Fakes for every outside service retrieval and memory need."""

    def __init__(self) -> None:
        self.chat = FakeLLM(REPLY)
        self.background = FakeBackgroundLLM(json.dumps({"memories": [CAT]}, ensure_ascii=False))
        self.jev = FakeJudge()
        self.embedder = FakeEmbedder()
        self.reranker = FakeReranker("制作人")


@pytest.fixture
async def backends() -> AsyncIterator[list[Backend]]:
    made: list[Backend] = []
    yield made
    for backend in made:
        await backend.aclose()


async def tell_mano(backend: Backend, text: str) -> tuple[str, list[dict]]:
    """Take one turn in a new conversation with Mano; returns its user and events."""
    user = backend.store.create_user("producer")
    conversation = backend.store.create_conversation(user.id, "mano")
    llms = backend.own_keys.for_turn(user.id).llms
    return user.id, [asdict(e) async for e in backend.engine.turn(conversation, text, llms)]


async def test_with_every_service_turns_retrieve_and_remember(
    settings: Settings, backends: list[Backend]
):
    services = Services()
    backend = build(
        settings, chat_llm=services.chat, background_llm=services.background,
        jev=services.jev, embedder=services.embedder, reranker=services.reranker,
        clock=lambda: NOW,
    )
    backends.append(backend)

    user_id, events = await tell_mano(backend, "我家的猫叫小白哦")

    assert events[-1]["type"] == "done"
    assert services.jev.asked == [("mano", "我家的猫叫小白哦")]
    assert services.chat.tools == [[RECALL_STORY_TOOL]]
    assert [m.text for m in await backend.memories.entries(user_id)] == [CAT]


@pytest.mark.parametrize("missing", ALL)
async def test_without_any_one_of_them_retrieval_and_memory_are_off(
    settings: Settings, backends: list[Backend], missing: str
):
    services = Services()
    given = {name: getattr(services, name) for name in ALL if name != missing}
    backend = build(
        settings, chat_llm=services.chat, background_llm=services.background,
        clock=lambda: NOW, **given,
    )
    backends.append(backend)

    user_id, events = await tell_mano(backend, "我家的猫叫小白哦")

    assert events[-1]["type"] == "done"
    assert services.jev.asked == []
    assert services.chat.tools == [[]]  # nothing to recall episodes with
    assert await backend.memories.entries(user_id) == []  # listing still works
    assert services.background.prompts == []  # nothing was written down


def test_the_background_model_is_the_chat_model_unless_configured_apart(settings: Settings):
    chat = LLMSettings("https://chat.example/v1", "chat-key", "chat-model")
    background = LLMSettings("https://chat.example/v1", "chat-key", "cheap-model")

    assert Settings(settings.database_path, settings.characters_path, chat).background_llm == chat
    assert (
        Settings(settings.database_path, settings.characters_path, chat, background).background_llm
        == background
    )
