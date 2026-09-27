"""Turns during a voice call, at the Pipecat stage that wraps the conversation engine.

Speech recognition, TTS and the transport are left out: the stage is fed what Soniox
and the browser's data channel would deliver, and what it sends on is inspected where
Fish Audio (text frames) and the browser (server messages) would receive it.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
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

from eidolon import call as call_module
from eidolon.call import Call, CallLimits, CallTurns
from eidolon.assembly import build
from eidolon.config import Settings
from eidolon.engine import MAX_INPUT_LENGTH
from eidolon.store import Store
from tests.conftest import ClientFactory
from tests.fakes import (
    HANG,
    FakeBackgroundLLM,
    FakeEmbedder,
    FakeJudge,
    FakeLLM,
    FakeReranker,
)
from tests.test_text_turn import start_conversation

NOW = datetime(2026, 9, 25, 12, 30, tzinfo=UTC)
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
        self,
        llm: FakeLLM,
        frames: Sequence[Frame],
        *,
        muted: bool = False,
        limits: CallLimits = CallLimits(),
        memory: FakeBackgroundLLM | None = None,
    ) -> tuple[list[str], list[dict]]:
        """Run the frames through; returns the text sent to TTS and the messages sent to the browser."""
        down = await self.run_frames(llm, frames, muted=muted, limits=limits, memory=memory)
        spoken = [f.text for f in down if type(f) is TextFrame]
        messages = [f.data for f in down if isinstance(f, RTVIServerMessageFrame)]
        return spoken, messages

    async def run_frames(
        self,
        llm: FakeLLM,
        frames: Sequence[Frame],
        *,
        muted: bool = False,
        limits: CallLimits = CallLimits(),
        memory: FakeBackgroundLLM | None = None,
    ) -> Sequence[Frame]:
        remembering = {} if memory is None else {
            "background_llm": memory, "jev": FakeJudge(), "embedder": FakeEmbedder(),
            "reranker": FakeReranker(),
        }
        backend = build(self._settings, chat_llm=llm, clock=lambda: NOW, **remembering)
        try:
            mano = backend.characters["mano"]
            llms = backend.own_keys.for_turn(self.conversation.user_id).llms
            call = Call(self.conversation, mano, llms, muted, "standard")
            down, _ = await run_test(CallTurns(backend.engine, call, limits), frames_to_send=frames)
        finally:
            await backend.aclose()
        return down

    async def record(self) -> list[tuple]:
        res = await self._client.get(f"/api/conversations/{self.conversation.id}/messages")
        return [(m["role"], m["text"], m["ja"], m["zh"]) for m in res.json()]

    async def said(self) -> list[str | None]:
        """What the user said in each recorded turn, None for the character's replies."""
        return [row[1] for row in await self.record()]

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


async def test_each_reply_is_one_tts_response(mano_call: CallUnderTest):
    down = await mano_call.run_frames(FakeLLM(MANO_REPLY), [spoken("早上好")])

    voiced = [type(f) for f in down if not isinstance(f, RTVIServerMessageFrame)]
    assert voiced == [
        LLMFullResponseStartFrame, TextFrame, TextFrame, TextFrame, LLMFullResponseEndFrame
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


async def test_blank_input_is_ignored(mano_call: CallUnderTest):
    spoken_text, messages = await mano_call.run(FakeLLM(), [spoken("  "), typed("")])

    assert spoken_text == [] and messages == []
    assert await mano_call.record() == []


INTERRUPTED_REPLY = ["<ja>ほわっ</ja><zh>哇</zh>", "<ja>今日", HANG]
"""A reply with one complete segment, then half of the next, then nothing, ever."""
INTERRUPTIBLE = [SleepFrame(0.1), BotStartedSpeakingFrame(), SleepFrame(0.3)]
"""The character starts speaking, and goes on until the second segment is started."""
INTERRUPTING = [*INTERRUPTIBLE, InterruptionFrame()]
"""The user interrupts her then."""


async def test_an_interruption_stops_the_reply_which_is_recorded_with_its_complete_segments(
    mano_call: CallUnderTest,
):
    memory = FakeBackgroundLLM()

    spoken_text, messages = await mano_call.run(
        FakeLLM(INTERRUPTED_REPLY, delay=0.3), [spoken("早上好"), *INTERRUPTING],
        memory=memory, limits=CallLimits(turns=1),
    )

    assert spoken_text == ["ほわっ", "今日"]
    assert kinds(messages) == ["user", "done", "ended"]  # it counts as a turn
    assert (messages[-2]["message"]["ja"], messages[-2]["message"]["zh"]) == ("ほわっ", "哇")
    assert await mano_call.record() == [
        ("user", "早上好", None, None), ("character", None, "ほわっ", "哇"),
    ]
    assert len(memory.prompts) == 1


async def test_what_interrupts_the_character_is_taken_up_at_once(mano_call: CallUnderTest):
    llm = FakeLLM(INTERRUPTED_REPLY, MANO_REPLY, delay=0.3)

    _, messages = await mano_call.run(
        llm, [spoken("早上好"), *INTERRUPTING, SleepFrame(0.1), spoken("在吗")]
    )

    assert said(messages) == ["早上好", "在吗"]
    assert await mano_call.said() == ["早上好", None, "在吗", None]


async def test_an_interruption_that_comes_to_nothing_takes_no_turn(mano_call: CallUnderTest):
    llm = FakeLLM(INTERRUPTED_REPLY, delay=0.3)

    _, messages = await mano_call.run(
        llm, [spoken("早上好"), *INTERRUPTING, SleepFrame(0.1), spoken("  ")]
    )

    assert kinds(messages) == ["user", "done"]
    assert len(llm.prompts) == 1


async def test_what_is_typed_once_the_reply_can_be_interrupted_interrupts_the_character(
    mano_call: CallUnderTest,
):
    llm = FakeLLM(INTERRUPTED_REPLY, MANO_REPLY, delay=0.3)

    down = await mano_call.run_frames(llm, [spoken("早上好"), *INTERRUPTIBLE, typed("在吗")])

    messages = [f.data for f in down if isinstance(f, RTVIServerMessageFrame)]
    assert said(messages) == ["早上好", "在吗"]
    assert InterruptionFrame in frame_types(down)
    assert await mano_call.record() == [
        ("user", "早上好", None, None), ("character", None, "ほわっ", "哇"),
        ("user", "在吗", None, None),
        ("character", None, "ほわっ、おはようございます！今日も", "哇，早上好！今天也"),
    ]


async def test_what_is_typed_while_a_recorded_reply_is_still_heard_stops_her_voice(
    mano_call: CallUnderTest,
):
    llm = FakeLLM(MANO_REPLY, MANO_REPLY)

    down = await mano_call.run_frames(
        llm, [spoken("早上好"), SleepFrame(0.1), BotStartedSpeakingFrame(), typed("在吗")]
    )

    types = frame_types(down)
    assert InterruptionFrame in types[types.index(LLMFullResponseEndFrame):]
    assert await mano_call.said() == ["早上好", None, "在吗", None]  # the first reply as it was


async def test_what_is_typed_straight_after_interrupting_follows_on_the_new_turn(
    mano_call: CallUnderTest,
):
    llm = FakeLLM(INTERRUPTED_REPLY, SLOW_REPLY, MANO_REPLY, delay=0.3)

    _, messages = await mano_call.run(
        llm,
        [spoken("早上好"), *INTERRUPTIBLE, typed("在吗"), SleepFrame(0.1), typed("还在吗")],
    )

    assert said(messages) == ["早上好", "在吗", "在吗\n还在吗"]
    assert await mano_call.said() == ["早上好", None, "在吗\n还在吗", None]


async def test_what_is_typed_once_the_call_has_ended_leaves_her_last_reply_voiced(
    mano_call: CallUnderTest,
):
    down = await mano_call.run_frames(
        FakeLLM(MANO_REPLY),
        [spoken("早上好"), SleepFrame(0.1), BotStartedSpeakingFrame(), typed("在吗")],
        limits=CallLimits(turns=1),
    )

    assert InterruptionFrame not in frame_types(down)
    assert await mano_call.said() == ["早上好", None]


SLOW_REPLY = ["<ja>ほわっ", "</ja><zh>哇</zh>", "<ja>今日も</ja><zh>今天也</zh>"]
"""A reply slow enough to be followed on: its first segment completes 0.3 s in."""


def said(messages: list[dict]) -> list[str]:
    return [m["text"] for m in messages if m["type"] == "user"]


async def test_what_is_said_before_the_character_speaks_joins_the_turn(mano_call: CallUnderTest):
    llm = FakeLLM(SLOW_REPLY, MANO_REPLY, delay=0.3)
    memory = FakeBackgroundLLM()

    _, messages = await mano_call.run(
        llm,
        [spoken("早上好"), SleepFrame(0.1), InterruptionFrame(), SleepFrame(0.1), spoken("在吗")],
        memory=memory,
    )

    assert said(messages) == ["早上好", "早上好\n在吗"]
    assert kinds(messages) == ["user", "user", "done"]
    assert llm.prompts[-1][-1].content == "早上好\n在吗"
    assert await mano_call.record() == [
        ("user", "早上好\n在吗", None, None),
        ("character", None, "ほわっ、おはようございます！今日も", "哇，早上好！今天也"),
    ]
    assert len(memory.prompts) == 1  # the reply dropped was not written down


async def test_what_is_typed_before_the_character_speaks_joins_the_turn_and_stops_its_voice(
    mano_call: CallUnderTest,
):
    llm = FakeLLM(SLOW_REPLY, MANO_REPLY, delay=0.3)

    down = await mano_call.run_frames(llm, [spoken("早上好"), SleepFrame(0.1), typed("在吗")])

    messages = [f.data for f in down if isinstance(f, RTVIServerMessageFrame)]
    assert said(messages) == ["早上好", "早上好\n在吗"]
    assert await mano_call.said() == ["早上好\n在吗", None]
    voiced = [type(f) for f in down if not isinstance(f, RTVIServerMessageFrame)]
    assert voiced[:4] == [
        LLMFullResponseStartFrame, TextFrame, LLMFullResponseEndFrame, InterruptionFrame
    ]


async def test_any_number_of_follow_ons_join_the_turn(mano_call: CallUnderTest):
    llm = FakeLLM(SLOW_REPLY, SLOW_REPLY, SLOW_REPLY, MANO_REPLY, delay=0.3)

    _, messages = await mano_call.run(
        llm,
        [
            spoken("一"), SleepFrame(0.1), InterruptionFrame(), spoken("二"),
            SleepFrame(0.1), typed("三"),
            SleepFrame(0.1), InterruptionFrame(), SleepFrame(0.1), spoken("四"),
        ],
        limits=CallLimits(turns=1),
    )

    assert said(messages) == ["一", "一\n二", "一\n二\n三", "一\n二\n三\n四"]
    assert kinds(messages)[-2:] == ["done", "ended"]  # only the one turn counted
    assert await mano_call.said() == ["一\n二\n三\n四", None]


@pytest.mark.parametrize(
    "muted, before",
    [
        (False, [SleepFrame(0.1), BotStartedSpeakingFrame()]),  # heard, nothing complete yet
        (True, [SleepFrame(0.1)]),  # muted: the first line is shown, nothing complete yet
        (False, [SleepFrame(0.4)]),  # a complete segment is shown but not heard yet
    ],
    ids=["speaking", "muted", "not heard yet"],
)
async def test_until_the_character_has_spoken_a_complete_segment_the_user_follows_on(
    mano_call: CallUnderTest, muted: bool, before: list[Frame]
):
    llm = FakeLLM(SLOW_REPLY, MANO_REPLY, delay=0.3)

    _, messages = await mano_call.run(
        llm, [spoken("早上好"), *before, InterruptionFrame(), SleepFrame(0.1), spoken("在吗")],
        muted=muted,
    )

    assert said(messages) == ["早上好", "早上好\n在吗"]
    assert await mano_call.said() == ["早上好\n在吗", None]


@pytest.mark.parametrize(
    "muted, before",
    [
        (False, [SleepFrame(0.4), BotStartedSpeakingFrame()]),
        (True, [SleepFrame(0.4)]),
    ],
    ids=["speaking", "muted"],
)
async def test_once_the_character_has_spoken_a_complete_segment_what_is_said_is_a_new_turn(
    mano_call: CallUnderTest, muted: bool, before: list[Frame]
):
    llm = FakeLLM(SLOW_REPLY, MANO_REPLY, delay=0.3)

    _, messages = await mano_call.run(
        llm, [spoken("早上好"), *before, InterruptionFrame(), SleepFrame(0.1), spoken("在吗")],
        muted=muted,
    )

    assert said(messages) == ["早上好", "在吗"]
    assert await mano_call.said() == ["早上好", None, "在吗", None]


async def test_once_the_reply_is_recorded_what_is_said_is_a_new_turn(mano_call: CallUnderTest):
    llm = FakeLLM(MANO_REPLY, MANO_REPLY)

    _, messages = await mano_call.run(
        llm, [spoken("早上好"), SleepFrame(0.1), InterruptionFrame(), SleepFrame(0.1), spoken("在吗")]
    )

    assert said(messages) == ["早上好", "在吗"]


async def test_a_reply_voiced_straight_after_the_last_one_has_been_spoken_once_it_is_on_its_way(
    mano_call: CallUnderTest,
):
    """The character's voice runs on from one reply into the next without starting again."""
    llm = FakeLLM(MANO_REPLY, SLOW_REPLY, MANO_REPLY, delay=0.3)

    _, messages = await mano_call.run(
        llm,
        [
            spoken("早上好"), SleepFrame(0.1), BotStartedSpeakingFrame(),
            SleepFrame(0.4), spoken("在吗"), SleepFrame(0.4),
            InterruptionFrame(), SleepFrame(0.1), spoken("还在吗"),
        ],
    )

    assert said(messages) == ["早上好", "在吗", "还在吗"]


async def test_the_voice_of_a_dropped_reply_starting_late_does_not_count_for_the_next(
    mano_call: CallUnderTest,
):
    llm = FakeLLM(SLOW_REPLY, ["", *SLOW_REPLY], MANO_REPLY, delay=0.3)

    _, messages = await mano_call.run(
        llm,
        [
            spoken("早上好"), SleepFrame(0.1),
            typed("在吗"), BotStartedSpeakingFrame(), BotStoppedSpeakingFrame(),
            SleepFrame(0.8), InterruptionFrame(), SleepFrame(0.1), spoken("还在吗"),
        ],
    )

    assert said(messages) == ["早上好", "早上好\n在吗", "早上好\n在吗\n还在吗"]


@pytest.mark.parametrize(
    "after",
    [[spoken("  ")], []],
    ids=["blank transcription", "nothing at all"],
)
async def test_a_follow_on_that_comes_to_nothing_has_the_turn_replied_to_again(
    mano_call: CallUnderTest, monkeypatch: pytest.MonkeyPatch, after: list[Frame]
):
    monkeypatch.setattr(call_module, "FOLLOW_ON_TIMEOUT", 0.3)
    llm = FakeLLM(SLOW_REPLY, MANO_REPLY, delay=0.3)

    _, messages = await mano_call.run(
        llm, [spoken("早上好"), SleepFrame(0.1), InterruptionFrame(), SleepFrame(0.1), *after]
    )

    assert said(messages) == ["早上好", "早上好"]
    assert await mano_call.said() == ["早上好", None]


def frame_types(frames: Sequence[Frame]) -> list[type[Frame]]:
    return [type(f) for f in frames]


def kinds(messages: list[dict]) -> list[str]:
    return [m["type"] for m in messages if m["type"] != "delta"]


async def test_call_hangs_up_after_its_last_allowed_turn(mano_call: CallUnderTest):
    llm = FakeLLM(MANO_REPLY, MANO_REPLY)

    spoken_text, messages = await mano_call.run(
        llm,
        one_by_one(spoken("早上好"), typed("在吗"), spoken("还在吗")),
        limits=CallLimits(turns=2),
    )

    assert kinds(messages) == ["user", "done", "user", "done", "ended"]
    assert "2 轮" in messages[-1]["message"]
    assert "".join(spoken_text).count("ほわっ") == 2  # the last reply is still voiced
    assert len(await mano_call.record()) == 4


async def test_call_hangs_up_when_time_is_up_once_the_reply_in_progress_is_done(
    mano_call: CallUnderTest,
):
    llm = FakeLLM(MANO_REPLY, delay=0.2)

    _, messages = await mano_call.run(
        llm,
        [spoken("早上好"), SleepFrame(0.6), spoken("还在吗")],
        limits=CallLimits(duration=timedelta(seconds=0.1)),
    )

    assert kinds(messages) == ["user", "done", "ended"]
    assert "分钟" in messages[-1]["message"]
    assert len(await mano_call.record()) == 2


async def test_turns_that_fail_or_are_rejected_do_not_count_and_the_call_goes_on(
    mano_call: CallUnderTest,
):
    llm = FakeLLM(["  "], MANO_REPLY)  # the first reply is empty
    too_long = "啊" * (MAX_INPUT_LENGTH + 1)

    spoken_text, messages = await mano_call.run(
        llm,
        one_by_one(spoken(too_long), typed(too_long), spoken("在吗"), spoken("在吗？")),
        limits=CallLimits(turns=1),
    )

    assert kinds(messages) == ["user", "error"] * 3 + ["user", "done", "ended"]
    assert len(llm.prompts) == 2  # what was too long never reached the model
    assert "".join(spoken_text).count("ほわっ") == 1
    assert await mano_call.said() == ["在吗？", None]

