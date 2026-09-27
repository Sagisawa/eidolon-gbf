"""The turn protocol, driven through the conversation engine's interface.

Every turn opens with `user` and closes with `done` or `error`, whether it arrives as a
text turn or during a call; the SSE and call tests only cover how each carries it.
"""

from collections.abc import Iterator
from dataclasses import asdict
from datetime import UTC, datetime

import pytest

from eidolon.assembly import build
from eidolon.config import Settings
from eidolon.engine import MAX_INPUT_LENGTH
from eidolon.reply_format import SegmentComplete
from eidolon.store import Conversation, Store
from tests.fakes import FakeLLM

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
REPLY = ["<ja>ほわっ、</ja><zh>哇，</zh>"]


class Turns:
    """A conversation with Mano and the engine that takes its turns."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._store = Store(settings.database_path)
        user = self._store.create_user("producer")
        self.conversation: Conversation = self._store.create_conversation(user.id, "mano")

    async def take(self, llm: FakeLLM, text: str, *, in_house: bool = False) -> list[dict]:
        """Take one turn; returns its events as they go out on the wire, and with
        `in_house` also those that stay on the server."""
        backend = build(self._settings, chat_llm=llm, clock=lambda: NOW)
        try:
            llms = backend.own_keys.for_turn(self.conversation.user_id).llms
            events = [e async for e in backend.engine.turn(self.conversation, text, llms)]
        finally:
            await backend.aclose()
        return [asdict(e) for e in events if in_house or not isinstance(e, SegmentComplete)]

    def record(self) -> list[tuple]:
        return [(m.role, m.text, m.ja) for m in self._store.list_messages(self.conversation.id)]

    def close(self) -> None:
        self._store.close()


@pytest.fixture
def turns(settings: Settings) -> Iterator[Turns]:
    turns = Turns(settings)
    yield turns
    turns.close()


def types(events: list[dict]) -> list[str]:
    return [e["type"] for e in events]


async def test_input_longer_than_the_limit_is_rejected_without_reaching_the_model(turns: Turns):
    llm = FakeLLM(REPLY)

    events = await turns.take(llm, "啊" * (MAX_INPUT_LENGTH + 1))

    assert types(events) == ["user", "error"]
    assert events[-1]["message"] == f"这句话太长了，最多 {MAX_INPUT_LENGTH} 字。"
    assert llm.prompts == []
    assert turns.record() == []


async def test_blank_input_is_rejected_without_reaching_the_model(turns: Turns):
    llm = FakeLLM(REPLY)

    events = await turns.take(llm, " \n\t")

    assert events == [{"type": "user", "text": ""}, {"type": "error", "message": "没有收到要说的话。"}]
    assert llm.prompts == []
    assert turns.record() == []


async def test_a_turn_opens_with_what_the_user_said_and_closes_with_the_recorded_reply(
    turns: Turns,
):
    events = await turns.take(FakeLLM(REPLY), "  早上好\n")

    assert types(events) == ["user", "delta", "delta", "done"]
    assert events[0]["text"] == "早上好"
    assert events[-1]["message"]["ja"] == "ほわっ、"
    assert turns.record() == [("user", "早上好", None), ("character", None, "ほわっ、")]


async def test_a_segment_is_complete_once_its_subtitle_closes_the_next_opens_or_the_model_stops(
    turns: Turns,
):
    llm = FakeLLM(["<ja>一</ja>", "<zh>一</zh>", "<ja>二</ja>", "<ja>三</ja><zh>三"])

    events = await turns.take(llm, "早上好", in_house=True)

    assert [(e["type"], e.get("segment")) for e in events[1:]] == [
        ("delta", 0), ("delta", 0), ("segment-complete", 0),
        ("delta", 1), ("segment-complete", 1),
        ("delta", 2), ("delta", 2), ("segment-complete", 2),
        ("done", None),
    ]


@pytest.mark.parametrize(
    "llm",
    [FakeLLM(), FakeLLM(["  \n"])],  # the model call fails; the model says nothing
    ids=["model fails", "empty reply"],
)
async def test_a_failed_turn_closes_with_an_error_and_leaves_no_record(
    turns: Turns, llm: FakeLLM, caplog: pytest.LogCaptureFixture
):
    events = await turns.take(llm, "在吗")

    assert types(events)[0] == "user"
    assert events[-1] == {"type": "error", "message": "角色暂时无法回复，请稍后再试。"}
    assert turns.record() == []
    assert "turn failed" in caplog.text  # what went wrong stays in the server log
