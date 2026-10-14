"""What changes from turn to turn goes after the history, and the history the chat model
reads is cut back in steps, so each turn's prompt opens as the one before it did and the
service can cache all of it but the end (ADR-0020)."""

from dataclasses import replace

import pytest

from eidolon.config import Settings
from eidolon.llm import ChatMessage
from eidolon.reply_format import FORMAT_INSTRUCTIONS
from tests.conftest import ClientFactory
from tests.fakes import (
    FakeBackgroundLLM,
    FakeClock,
    FakeEmbedder,
    FakeJudge,
    FakeLLM,
    FakeReranker,
    FakeServiceClients,
    context_of,
)
from tests.test_text_turn import send_turn, start_conversation

PROFILE = {
    "form_of_address": "小林",
    "gender": "female",
    "timezone": "Asia/Tokyo",
    "birthday": {"month": 5, "day": 3},
}


def reply(n: int) -> list[str]:
    return [f"<ja>返事{n}</ja><zh>回复{n}</zh>"]


def shape(prompt: list[ChatMessage]) -> list[tuple[str, str]]:
    """What the model reads of `prompt`, without what marks a part for caching."""
    return [(m.role, m.content) for m in prompt]


async def test_what_changes_each_turn_comes_after_the_history(make_client: ClientFactory):
    llm = FakeLLM(reply(1), reply(2))
    client = make_client(llm)
    await client.put("/api/profile", json=PROFILE)
    conversation = await start_conversation(client)

    await send_turn(client, conversation, "第1句")
    await send_turn(client, conversation, "第2句")

    shared, producer, *rest = llm.prompts[-1]
    assert shared.cache_breakpoint and shared.content.endswith(FORMAT_INSTRUCTIONS)
    assert producer.role == "system"
    assert "小林" in producer.content and "5月3日" in producer.content
    assert "现在是" not in producer.content
    assert [m.role for m in rest] == ["user", "assistant", "system", "user"]
    assert rest[-2].content.startswith("# 此刻\n现在是 ")
    assert "现在是" not in "".join(m.content for m in rest if m.role != "system")


async def test_a_turn_opens_as_the_turn_before_it_did(make_client: ClientFactory):
    """The previous turn's prompt, but for what changes each turn and what the user said,
    is how the next one opens: the service's cache of it carries over."""
    clock = FakeClock()
    background = FakeBackgroundLLM(
        '{"memories": ["制作人养了一只猫"]}', '{"memories": ["制作人在学吉他"]}'
    )
    llm = FakeLLM(reply(1), reply(2), reply(3))
    client = make_client(
        llm, clock=clock, clients=FakeServiceClients(), background_llm=background,
        retrieval_judge=FakeJudge(answer="memories"), embedder=FakeEmbedder(),
        reranker=FakeReranker(),
    )
    await client.put("/api/profile", json=PROFILE)
    conversation = await start_conversation(client)

    for n in range(1, 4):
        await send_turn(client, conversation, f"第{n}句")
        clock.advance(minutes=3)

    assert "制作人养了一只猫" in context_of(llm.prompts[1])  # what changes does change
    for before, after in zip(llm.prompts, llm.prompts[1:], strict=False):
        opening = shape(before[:-2])
        assert shape(after[: len(opening)]) == opening
        assert context_of(before) != context_of(after)


@pytest.mark.parametrize(
    ("before", "carried"),
    # At least 4 turns back; once there are 6, back to 4, and so on every 2.
    [(3, 3), (4, 4), (5, 5), (6, 4), (7, 5), (8, 4)],
)
async def test_the_history_is_cut_back_in_steps(
    make_client: ClientFactory, settings: Settings, before: int, carried: int
):
    llm = FakeLLM(*[reply(n) for n in range(1, before + 2)])
    client = make_client(llm, settings=replace(settings, history_turns=4))
    conversation = await start_conversation(client)

    for n in range(1, before + 2):
        await send_turn(client, conversation, f"第{n}句")

    said = [m.content for m in llm.prompts[-1] if m.role == "user"]
    assert said == [f"第{n}句" for n in range(before - carried + 1, before + 2)]


async def test_with_one_turn_the_history_steps_by_one(
    make_client: ClientFactory, settings: Settings
):
    llm = FakeLLM(*[reply(n) for n in range(1, 4)])
    client = make_client(llm, settings=replace(settings, history_turns=1))
    conversation = await start_conversation(client)

    for n in range(1, 4):
        await send_turn(client, conversation, f"第{n}句")

    assert [m.content for m in llm.prompts[-1] if m.role == "user"] == ["第2句", "第3句"]


async def test_without_a_limit_the_whole_history_is_carried(
    make_client: ClientFactory, settings: Settings
):
    llm = FakeLLM(*[reply(n) for n in range(1, 8)])
    client = make_client(llm, settings=replace(settings, history_turns=None))
    conversation = await start_conversation(client)

    for n in range(1, 8):
        await send_turn(client, conversation, f"第{n}句")

    assert len([m for m in llm.prompts[-1] if m.role == "user"]) == 7

