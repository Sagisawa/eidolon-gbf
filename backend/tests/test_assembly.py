"""The assembly root: what `build` turns on, given which outside services are at hand.

Retrieval needs the judge model, the embedder and the reranker; memory is on only with
retrieval, since only retrieval finds memories again. Turns are taken through the built
engine.
"""

import json
from collections.abc import AsyncIterator
from dataclasses import asdict, replace
from datetime import UTC, datetime

import httpx
import pytest

import eidolon.assembly
from eidolon.assembly import Backend, build
from eidolon.config import CloudflareJudgeSettings, LLMSettings, Settings
from eidolon.emotion import SaidSegment, SegmentToJudge
from eidolon.judge import open_judge
from eidolon.retrieval import RECALL_STORY_TOOL
from tests.fakes import FakeBackgroundLLM, FakeEmbedder, FakeJudge, FakeLLM, FakeReranker
from tests.test_cloudflare_judge import URL, envelope
from tests.test_retrieval_services import Handler, client

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
REPLY = ["<ja>はいっ</ja><zh>好的</zh>"]
CAT = "制作人家里养了一只叫小白的猫"
ALL = ("retrieval_judge", "embedder", "reranker")


class Services:
    """Fakes for every outside service retrieval and memory need."""

    def __init__(self) -> None:
        self.chat = FakeLLM(REPLY)
        self.background = FakeBackgroundLLM(json.dumps({"memories": [CAT]}, ensure_ascii=False))
        self.retrieval_judge = FakeJudge()
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
        retrieval_judge=services.retrieval_judge, embedder=services.embedder, reranker=services.reranker,
        clock=lambda: NOW,
    )
    backends.append(backend)

    user_id, events = await tell_mano(backend, "我家的猫叫小白哦")

    assert events[-1]["type"] == "done"
    assert services.retrieval_judge.asked == [("mano", "我家的猫叫小白哦")]
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
    assert services.retrieval_judge.asked == []
    assert services.chat.tools == [[]]  # nothing to recall episodes with
    assert await backend.memories.entries(user_id) == []  # listing still works
    assert services.background.prompts == []  # nothing was written down


def answering_every_question(requests: list[dict]) -> Handler:
    """Workers AI answering whatever it is asked: no to each yes-or-no question, the first
    option of each choice."""

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append({"url": str(request.url), **body})
        answers = {}
        for name, question in body["questions"].items():
            if question["type"] == "noul":
                answers[name] = {"type": "noul", "noul": 0.1}
            else:
                first, *others = question["criteria"]
                answers[name] = {"type": "choice", "choice": first, "probabilities": {
                    first: 0.9, **{o: 0.1 / len(others) for o in others}
                }}
        return httpx.Response(200, json=envelope(answers))

    return handle


async def test_cloudflare_chosen_judges_both_what_turns_need_and_her_emotions(
    settings: Settings, backends: list[Backend], monkeypatch: pytest.MonkeyPatch
):
    requests: list[dict] = []
    monkeypatch.setattr(
        eidolon.assembly, "open_judge",
        lambda s: open_judge(s, client(answering_every_question(requests))),
    )
    services = Services()
    backend = build(
        replace(settings, judge=CloudflareJudgeSettings("cf-token", "acc-id")),
        chat_llm=services.chat, background_llm=services.background,
        embedder=services.embedder, reranker=services.reranker, clock=lambda: NOW,
    )
    backends.append(backend)

    await tell_mano(backend, "早上好")
    assert backend.emotions is not None
    said = SegmentToJudge(backend.characters["mano"], "早上好", [], SaidSegment("おはよう！", "早上好！"))
    await backend.emotions.message(1, 0, said)

    assert [(r["url"], set(r["questions"])) for r in requests] == [
        (URL, {"needs_retrieval", "recall", "about_producer"}), (URL, {"emotion", "nod"})
    ]


def test_the_background_model_is_the_chat_model_unless_configured_apart(settings: Settings):
    chat = LLMSettings("https://chat.example/v1", "chat-key", "chat-model")
    background = LLMSettings("https://chat.example/v1", "chat-key", "cheap-model")

    assert Settings(settings.database_path, settings.characters_path, chat).background_llm == chat
    assert (
        Settings(settings.database_path, settings.characters_path, chat, background).background_llm
        == background
    )
