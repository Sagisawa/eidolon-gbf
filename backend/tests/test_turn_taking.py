"""The rules for taking turns during a call (CONTEXT.md「回合」「补充」「打断」「只看文字」),
as `TurnTaking` has them: what `CallTurns` should do next, event by event.

Each case is a call's events, reported as `CallTurns` would, each with what it is told
to do then. Neither Pipecat nor the engine is needed, nor any waiting: how long a
follow-on may take is `CallTurns`'s to time, so here it simply comes to nothing.
"""

from collections.abc import Callable, Sequence

import pytest

from eidolon.turn_taking import (
    ClearVoice,
    Command,
    DropReply,
    QueueTurn,
    Reply,
    StopReply,
    TurnTaking,
    Voice,
    WaitForFollowOn,
)

Event = Callable[[TurnTaking], Sequence[Command]]
Step = tuple[Event, list[Command]]
"""An event, and what `CallTurns` is told to do on it."""


def turn(text: str) -> Event:
    """The next turn is taken up, the user having said `text`."""
    return lambda taking: taking.turn_started(text)


def says(text: str) -> Event:
    """What the user said is transcribed."""
    return lambda taking: taking.user_said(text)


def types(text: str) -> Event:
    """The user sends what they typed."""
    return lambda taking: taking.user_typed(text)


def ja(text: str) -> Event:
    """Some of the reply's Japanese is shown."""
    return lambda taking: taking.reply_delta("ja", text)


def zh(text: str) -> Event:
    """Some of the reply's subtitle is shown."""
    return lambda taking: taking.reply_delta("zh", text)


def text_only(on: bool) -> Event:
    """The user switches text only (「只看文字」) on or off."""
    return lambda taking: taking.text_only_switched(on)


TALKS: Event = TurnTaking.user_started_talking
HEARD: Event = TurnTaking.user_heard
COMPLETE: Event = TurnTaking.segment_complete
RECORDED: Event = TurnTaking.reply_recorded
ENDED: Event = TurnTaking.reply_ended
DROPPED: Event = TurnTaking.reply_dropped
MISSED: Event = TurnTaking.follow_on_missed
VOICE_STARTS: Event = TurnTaking.voice_started
VOICE_STOPS: Event = TurnTaking.voice_stopped
CALL_ENDING: Event = TurnTaking.call_ending

REPLYING: list[Step] = [(turn("早上好"), [Reply("早上好", voiced=True)])]
"""A turn is being replied to, voiced; nothing of the reply is out yet."""
SPEAKING: list[Step] = [*REPLYING, (ja("ほわっ"), [Voice("ほわっ")]), (VOICE_STARTS, [])]
"""The character has started speaking the reply; no segment of it is complete yet."""
INTERRUPTIBLE: list[Step] = [*SPEAKING, (zh("哇"), []), (COMPLETE, [])]
"""The character has started speaking the reply, and it has a complete segment."""
RECORDED_AND_HEARD: list[Step] = [
    *REPLYING, (ja("ほわっ"), [Voice("ほわっ")]), (zh("哇"), []), (COMPLETE, []),
    (RECORDED, []), (ENDED, []), (VOICE_STARTS, []),
]
"""The reply is recorded and over, and its voice is still playing."""


def run(steps: list[Step], *, starts_text_only: bool = False) -> TurnTaking:
    taking = TurnTaking(text_only=starts_text_only)
    for number, (event, commands) in enumerate(steps):
        assert event(taking) == commands, f"step {number}"
    return taking


FOLLOW_ONS = [
    pytest.param(
        [
            *REPLYING,
            (TALKS, [DropReply()]),
            (DROPPED, [WaitForFollowOn()]),
            (says("在吗"), [Reply("早上好\n在吗", voiced=True)]),
        ],
        id="what is said before she speaks drops the reply and joins the turn on a new line",
    ),
    pytest.param(
        [
            *REPLYING,
            (TALKS, [DropReply()]),
            (says("在吗"), []),
            (DROPPED, [Reply("早上好\n在吗", voiced=True)]),
        ],
        id="a follow-on transcribed before the reply is gone is replied to once it is",
    ),
    pytest.param(
        [
            *REPLYING,
            (ja("ほわっ"), [Voice("ほわっ")]),
            (types("在吗"), [DropReply(), ClearVoice()]),
            (DROPPED, [Reply("早上好\n在吗", voiced=True)]),
        ],
        id="what is typed before she speaks joins the turn and clears what TTS holds",
    ),
    pytest.param(
        [
            (turn("一"), [Reply("一", voiced=True)]),
            (TALKS, [DropReply()]),
            (says("二"), []),
            (DROPPED, [Reply("一\n二", voiced=True)]),
            (types("三"), [DropReply(), ClearVoice()]),
            (DROPPED, [Reply("一\n二\n三", voiced=True)]),
            (TALKS, [DropReply()]),
            (DROPPED, [WaitForFollowOn()]),
            (says("四"), [Reply("一\n二\n三\n四", voiced=True)]),
        ],
        id="any number of follow-ons join the turn",
    ),
    pytest.param(
        [*SPEAKING, (TALKS, [DropReply()])],
        id="speaking but with nothing complete yet she is followed on",
    ),
    pytest.param(
        [
            *REPLYING, (ja("ほわっ"), [Voice("ほわっ")]), (zh("哇"), []), (COMPLETE, []),
            (TALKS, [DropReply()]),
        ],
        id="with a complete segment shown but not heard yet she is followed on",
    ),
    pytest.param(
        [
            *REPLYING,
            (TALKS, [DropReply()]),
            (DROPPED, [WaitForFollowOn()]),
            (MISSED, [Reply("早上好", voiced=True)]),
        ],
        id="a follow-on that comes to nothing has the turn replied to again as it was",
    ),
    pytest.param(
        [
            *REPLYING,
            (TALKS, [DropReply()]),
            (DROPPED, [WaitForFollowOn()]),
            (says("  "), [Reply("早上好", voiced=True)]),
        ],
        id="a follow-on transcribed blank has the turn replied to again as it was",
    ),
    pytest.param(
        [
            *REPLYING,
            (TALKS, [DropReply()]),
            (HEARD, []),
            (DROPPED, [WaitForFollowOn()]),
            (HEARD, [WaitForFollowOn()]),
            (TALKS, [WaitForFollowOn()]),
            (says("在吗"), [Reply("早上好\n在吗", voiced=True)]),
            (MISSED, []),
            (HEARD, []),
        ],
        id="hearing the user again waits afresh for the follow-on",
    ),
    pytest.param(
        [
            *REPLYING,
            (TALKS, [DropReply()]),
            (DROPPED, [WaitForFollowOn()]),
            (types("在吗"), [Reply("早上好\n在吗", voiced=True)]),
        ],
        id="what is typed while waiting for a follow-on is the follow-on",
    ),
    pytest.param(
        [
            *REPLYING,
            (TALKS, [DropReply()]),
            (TALKS, [DropReply()]),
            (DROPPED, [WaitForFollowOn()]),
        ],
        id="starting to talk again while the reply is being dropped drops it all the same",
    ),
]


@pytest.mark.parametrize("steps", FOLLOW_ONS)
def test_follow_ons(steps: list[Step]):
    run(steps)


@pytest.mark.parametrize(
    "steps",
    [
        pytest.param(
            [(turn("早上好"), [Reply("早上好", voiced=False)]), (ja("ほわっ"), []), (TALKS, [DropReply()])],
            id="its first line shown but nothing complete yet",
        ),
        pytest.param(
            [
                (turn("早上好"), [Reply("早上好", voiced=False)]), (ja("ほわっ"), []), (zh("哇"), []),
                (COMPLETE, []), (TALKS, [StopReply()]), (says("在吗"), [QueueTurn("在吗")]),
            ],
            id="its first line shown and a segment complete",
        ),
    ],
)
def test_text_only_a_reply_is_spoken_once_its_first_line_is_shown(steps: list[Step]):
    run(steps, starts_text_only=True)


INTERRUPTIONS = [
    pytest.param(
        [
            *INTERRUPTIBLE,
            (TALKS, [StopReply()]),
            (ja("今日"), []),
            (says("在吗"), [QueueTurn("在吗")]),
        ],
        id="what is said stops the reply, which is voiced no further, and is the next turn",
    ),
    pytest.param(
        [*INTERRUPTIBLE, (TALKS, [StopReply()]), (says("  "), [])],
        id="an interruption that comes to nothing takes no turn",
    ),
    pytest.param(
        [*INTERRUPTIBLE, (types("在吗"), [StopReply(), ClearVoice(), QueueTurn("在吗")])],
        id="what is typed stops the reply, clears her voice and is the next turn",
    ),
    pytest.param(
        [
            *REPLYING, (ja("ほわっ"), [Voice("ほわっ")]), (zh("哇"), []), (COMPLETE, []),
            (RECORDED, []),
            (TALKS, [StopReply()]),
            (ENDED, []),
            (says("在吗"), [QueueTurn("在吗")]),
        ],
        id="once the reply is recorded she has spoken",
    ),
    pytest.param(
        [*RECORDED_AND_HEARD, (types("在吗"), [ClearVoice(), QueueTurn("在吗")])],
        id="what is typed while a recorded reply is still heard stops her voice",
    ),
    pytest.param(
        [*RECORDED_AND_HEARD, (TALKS, []), (says("在吗"), [QueueTurn("在吗")])],
        id="what is said between replies is the next turn",
    ),
    pytest.param(
        [
            *INTERRUPTIBLE,
            (types("在吗"), [StopReply(), ClearVoice(), QueueTurn("在吗")]),
            (RECORDED, []),
            (ENDED, []),
            (turn("在吗"), [Reply("在吗", voiced=True)]),
            (types("还在吗"), [DropReply(), ClearVoice()]),
            (DROPPED, [Reply("在吗\n还在吗", voiced=True)]),
        ],
        id="of two sent straight after each other the first interrupts, the second follows on",
    ),
]


@pytest.mark.parametrize("steps", INTERRUPTIONS)
def test_interruptions(steps: list[Step]):
    run(steps)


@pytest.mark.parametrize(
    "steps",
    [
        pytest.param(
            [
                *REPLYING,
                (ja("ほわっ"), [Voice("ほわっ")]),
                (types("在吗"), [DropReply(), ClearVoice()]),
                (DROPPED, [Reply("早上好\n在吗", voiced=True)]),
                (VOICE_STARTS, []),
                (VOICE_STOPS, []),
                (ja("ほわっ"), [Voice("ほわっ")]),
                (zh("哇"), []),
                (COMPLETE, []),
                (TALKS, [DropReply()]),
            ],
            id="the voice of a dropped reply starting late does not count for the next",
        ),
        pytest.param(
            [
                *REPLYING, (ja("ほわっ"), [Voice("ほわっ")]), (zh("哇"), []), (COMPLETE, []),
                (TALKS, [DropReply()]),
                (VOICE_STARTS, []),
                (DROPPED, [WaitForFollowOn()]),
                (says("在吗"), [Reply("早上好\n在吗", voiced=True)]),
            ],
            id="the voice of a reply being dropped starting late does not make it spoken",
        ),
        pytest.param(
            [
                *RECORDED_AND_HEARD,
                (turn("在吗"), [Reply("在吗", voiced=True)]),
                (ja("今日も"), [Voice("今日も")]),
                (zh("今天也"), []),
                (COMPLETE, []),
                (TALKS, [StopReply()]),
            ],
            id="a reply voiced while the last one is still heard is spoken once it is on its way",
        ),
        pytest.param(
            [
                *RECORDED_AND_HEARD,
                (VOICE_STOPS, []),
                (turn("在吗"), [Reply("在吗", voiced=True)]),
                (ja("今日も"), [Voice("今日も")]),
                (zh("今天也"), []),
                (COMPLETE, []),
                (TALKS, [DropReply()]),
            ],
            id="a reply voiced once the last one has been heard waits for her voice to start",
        ),
    ],
)
def test_when_the_character_starts_speaking(steps: list[Step]):
    run(steps)


def test_switching_to_text_only_leaves_the_reply_in_progress_voiced():
    run([
        *REPLYING,
        (text_only(True), []),
        (ja("ほわっ"), [Voice("ほわっ")]),
        (RECORDED, []),
        (ENDED, []),
        (turn("在吗"), [Reply("在吗", voiced=False)]),
        (ja("今日も"), []),
        (text_only(False), []),
        (ja("今日も"), []),
        (RECORDED, []),
        (ENDED, []),
        (turn("还在吗"), [Reply("还在吗", voiced=True)]),
    ])


def test_blank_input_is_not_taken_up():
    run([(says("  "), []), (types(""), []), *REPLYING, (types(" "), []), (says(""), [])])


def test_once_the_call_is_ending_nothing_is_taken_up_and_her_last_reply_stays_voiced():
    taking = run([
        *RECORDED_AND_HEARD,
        (CALL_ENDING, []),
        (TALKS, []),
        (says("在吗"), []),
        (types("还在吗"), []),
        (turn("在吗"), []),
    ])

    assert taking.ending
