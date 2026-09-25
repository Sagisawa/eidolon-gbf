"""Turns during a voice call, at the Pipecat stage that wraps the conversation engine.

Speech recognition, TTS and the transport are left out: the stage is fed what Soniox
and the browser's data channel would deliver, and what it sends on is inspected where
Fish Audio (text frames) and the browser (server messages) would receive it.
"""

from collections.abc import Sequence

import httpx
import pytest
from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    TextFrame,
    TranscriptionFrame,
)
from pipecat.processors.frameworks.rtvi.frames import (
    RTVIClientMessageFrame,
    RTVIServerMessageFrame,
)
from pipecat.tests.utils import SleepFrame, run_test

from eidolon.call import Call, CallTurns
from eidolon.characters import load_characters
from eidolon.config import Settings
from eidolon.engine import ConversationEngine
from eidolon.store import Store
from tests.conftest import ClientFactory
from tests.fakes import FakeLLM
from tests.test_text_turn import start_conversation

MANO_REPLY = ["<ja>ほわっ、", "おはようございます！</ja><zh>哇，早上好！</zh><ja>今日も</ja><zh>今天也</zh>"]


class CallUnderTest:
    """One call into a fresh conversation with Mano, and the API to read its record."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient, conversation_id: str):
        self._settings = settings
        self._client = client
        self._store = Store(settings.database_path)
        conversation = self._store.get_conversation(conversation_id)
        assert conversation is not None
        self.conversation = conversation

    async def run(
        self, llm: FakeLLM, frames: Sequence[Frame], *, muted: bool = False
    ) -> tuple[list[str], list[dict]]:
        """Run the frames through; returns the text sent to TTS and the messages sent to the browser."""
        down = await self.run_frames(llm, frames, muted=muted)
        spoken = [f.text for f in down if type(f) is TextFrame]
        messages = [f.data for f in down if isinstance(f, RTVIServerMessageFrame)]
        return spoken, messages

    async def run_frames(
        self, llm: FakeLLM, frames: Sequence[Frame], *, muted: bool = False
    ) -> Sequence[Frame]:
        characters = load_characters(self._settings.characters_path)
        engine = ConversationEngine(self._store, llm, characters)
        call = Call(self.conversation, characters["mano"], muted, "standard")
        down, _ = await run_test(CallTurns(engine, call), frames_to_send=frames)
        return down

    async def record(self) -> list[tuple]:
        res = await self._client.get(f"/api/conversations/{self.conversation.id}/messages")
        return [(m["role"], m["text"], m["ja"], m["zh"]) for m in res.json()]

    def close(self) -> None:
        self._store.close()


@pytest.fixture
async def mano_call(make_client: ClientFactory, settings: Settings):
    client = make_client(FakeLLM())
    under_test = CallUnderTest(settings, client, await start_conversation(client, "mano"))
    yield under_test
    under_test.close()


def one_by_one(*frames: Frame) -> list[Frame]:
    """Space frames out as a person would. Client messages are system frames, which
    otherwise overtake transcriptions still queued in the pipeline."""
    spaced: list[Frame] = []
    for frame in frames:
        spaced += [frame, SleepFrame(0.05)]
    return spaced


def spoken(text: str) -> TranscriptionFrame:
    return TranscriptionFrame(text, "user", "2026-09-25T00:00:00Z", finalized=True)


def typed(text: str) -> RTVIClientMessageFrame:
    return RTVIClientMessageFrame(msg_id="m1", type="user-text", data={"text": text})


def mute(muted: bool) -> RTVIClientMessageFrame:
    return RTVIClientMessageFrame(msg_id="m2", type="mute", data={"muted": muted})


async def test_spoken_turn_is_voiced_in_japanese_with_subtitles_sent_alongside(
    mano_call: CallUnderTest,
):
    spoken_text, messages = await mano_call.run(FakeLLM(MANO_REPLY), [spoken("早上好")])

    assert "".join(spoken_text) == "ほわっ、おはようございます！今日も"
    assert messages[0] == {"type": "user", "text": "早上好"}
    deltas = [(m["segment"], m["lang"], m["text"]) for m in messages if m["type"] == "delta"]
    assert deltas == [
        (0, "ja", "ほわっ、"),
        (0, "ja", "おはようございます！"),
        (0, "zh", "哇，早上好！"),
        (1, "ja", "今日も"),
        (1, "zh", "今天也"),
    ]
    assert messages[-1]["type"] == "done"
    assert messages[-1]["message"]["segments"] == [
        {"ja": "ほわっ、おはようございます！", "zh": "哇，早上好！"},
        {"ja": "今日も", "zh": "今天也"},
    ]
    assert await mano_call.record() == [
        ("user", "早上好", None, None),
        ("character", None, "ほわっ、おはようございます！今日も", "哇，早上好！今天也"),
    ]


async def test_each_reply_is_one_tts_response(mano_call: CallUnderTest):
    down = await mano_call.run_frames(FakeLLM(MANO_REPLY), [spoken("早上好")])

    voiced = [type(f) for f in down if not isinstance(f, RTVIServerMessageFrame)]
    assert voiced == [
        LLMFullResponseStartFrame, TextFrame, TextFrame, TextFrame, LLMFullResponseEndFrame
    ]


async def test_typed_and_spoken_turns_share_the_conversation(mano_call: CallUnderTest):
    llm = FakeLLM(["<ja>はいっ</ja><zh>好的</zh>"], ["<ja>ピーちゃん！</ja><zh>小皮！</zh>"])

    spoken_text, messages = await mano_call.run(llm, one_by_one(spoken("你好"), typed("鸽子叫什么？")))

    assert spoken_text == ["はいっ", "ピーちゃん！"]
    assert [m["text"] for m in messages if m["type"] == "user"] == ["你好", "鸽子叫什么？"]
    assert [(m.role, m.content) for m in llm.prompts[1][1:]] == [
        ("user", "你好"),
        ("assistant", "<ja>はいっ</ja><zh>好的</zh>"),
        ("user", "鸽子叫什么？"),
    ]
    assert [row[:2] for row in await mano_call.record()] == [
        ("user", "你好"),
        ("character", None),
        ("user", "鸽子叫什么？"),
        ("character", None),
    ]


async def test_muted_call_sends_subtitles_but_nothing_to_voice(mano_call: CallUnderTest):
    llm = FakeLLM(["<ja>一</ja><zh>一</zh>"], ["<ja>二</ja><zh>二</zh>"], ["<ja>三</ja><zh>三</zh>"])

    spoken_text, messages = await mano_call.run(
        llm,
        one_by_one(spoken("第一句"), mute(False), spoken("第二句"), mute(True), typed("第三句")),
        muted=True,
    )

    assert spoken_text == ["二"]
    assert [m["message"]["ja"] for m in messages if m["type"] == "done"] == ["一", "二", "三"]


async def test_failed_turn_is_reported_and_the_call_goes_on(mano_call: CallUnderTest):
    llm = FakeLLM(["  "], ["<ja>はいっ</ja><zh>好的</zh>"])  # the first reply is empty

    spoken_text, messages = await mano_call.run(llm, [spoken("在吗"), spoken("在吗？")])

    assert [m["type"] for m in messages if m["type"] in ("error", "done")] == ["error", "done"]
    assert spoken_text == ["はいっ"]
    assert [row[1] for row in await mano_call.record()] == ["在吗？", None]


async def test_blank_input_is_ignored(mano_call: CallUnderTest):
    spoken_text, messages = await mano_call.run(FakeLLM(), [spoken("  "), typed("")])

    assert spoken_text == [] and messages == []
    assert await mano_call.record() == []


async def test_interrupted_reply_stops_being_voiced_but_is_still_recorded(
    mano_call: CallUnderTest,
):
    llm = FakeLLM(["<ja>ほわっ</ja><zh>哇</zh>", "<ja>今日も</ja><zh>今天也</zh>"], delay=0.3)

    spoken_text, messages = await mano_call.run(
        llm, [spoken("早上好"), SleepFrame(0.15), InterruptionFrame()]
    )

    assert spoken_text == ["ほわっ"]
    assert messages[-1]["message"]["ja"] == "ほわっ今日も"
