"""The character's voice, a segment at a time, through Fish Audio.

Fish Audio's live TTS does not say where one segment's audio ends and the next one's
begins, so each segment is voiced in a session of its own, on a connection opened while
the one before is voiced; ahead of each segment's first audio goes a `segment-playing`
message for the browser. Here Fish Audio is a fake speaking its websocket protocol, and
what reaches the transport is logged alongside what Fish Audio is sent.
"""

import asyncio
from typing import Any

import ormsgpack
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    CancelFrame,
    Frame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    OutputTransportMessageFrame,
    TTSAudioRawFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.fish.tts import FishAudioTTSService
from pipecat.tests.utils import SleepFrame, run_test
from websockets.exceptions import ConnectionClosedOK
from websockets.protocol import State

from eidolon.call import FishTTS, SegmentCompleteFrame, SegmentTextFrame

CONNECTION = 0.2
"""How long, in seconds, the fake Fish Audio takes to accept a connection."""
SYNTHESIS = 0.3
"""How long, in seconds, it takes to synthesise what it is sent, a sentence at a time."""


class FakeFish:
    """Stands in for Fish Audio's live TTS, logging what each connection is sent and what
    becomes of it, as "<connection> <what>", connections numbered from 1. With
    `idle_timeout`, it closes a connection sent no text that long after its start."""

    def __init__(self, idle_timeout: float | None = None, refused: tuple[int, ...] = ()) -> None:
        """The attempts to connect numbered (from 1) in `refused` fail; the connections
        made are numbered on their own."""
        self.idle_timeout = idle_timeout
        self.refused = refused
        self.attempts = 0
        self.log: list[str] = []
        self.at: dict[str, float] = {}  # when each entry was first logged
        self.sockets: list[FakeFishSocket] = []

    async def connect(self) -> "FakeFishSocket":
        await asyncio.sleep(CONNECTION)
        self.attempts += 1
        if self.attempts in self.refused:
            self.note("refused")
            raise OSError("connection refused")
        socket = FakeFishSocket(self, len(self.sockets) + 1)
        self.sockets.append(socket)
        self.note(f"{socket.number} connected")
        return socket

    def note(self, entry: str) -> None:
        self.log.append(entry)
        self.at.setdefault(entry, asyncio.get_running_loop().time())

    def of(self, number: int) -> list[str]:
        """What happened to connection `number`."""
        prefix = f"{number} "
        return [entry.removeprefix(prefix) for entry in self.log if entry.startswith(prefix)]


def audio(text: str) -> bytes:
    """The audio the fake synthesises for `text`: the text itself, padded out to a chunk
    big enough to be taken as audio."""
    return text.encode().ljust(2048, b"\0")


class FakeFishSocket:
    """One connection to the fake: a session, started, voicing the text it is sent once it
    is flushed; told to stop, it voices what it still has, finishes and closes."""

    def __init__(self, fish: FakeFish, number: int) -> None:
        self.fish = fish
        self.number = number
        self.state = State.OPEN
        self.transport = self
        self._text = ""
        self._to_voice: asyncio.Queue[str | None] = asyncio.Queue()  # None: stop
        self._to_send: asyncio.Queue[bytes | None] = asyncio.Queue()  # None: closed
        self._voicing = asyncio.create_task(self._voice())
        self._idle: asyncio.Task | None = None

    async def send(self, data: bytes) -> None:
        if self.state is not State.OPEN:
            raise ConnectionClosedOK(None, None)
        message = ormsgpack.unpackb(data)
        event = message["event"]
        if event == "text":
            if self._idle is not None:
                self._idle.cancel()
            self._text += message["text"]
            self._note(f"text {message['text'].strip()}")
            return
        self._note(event)
        if event == "start" and self.fish.idle_timeout is not None:
            self._idle = asyncio.create_task(self._close_when_idle(self.fish.idle_timeout))
        if event in ("flush", "stop") and self._text:
            self._to_voice.put_nowait(self._text)
            self._text = ""
        if event == "stop":
            self._to_voice.put_nowait(None)

    async def _close_when_idle(self, timeout: float) -> None:
        await asyncio.sleep(timeout)
        self._closed()

    async def _voice(self) -> None:
        while (text := await self._to_voice.get()) is not None:
            await asyncio.sleep(SYNTHESIS)
            self._to_send.put_nowait(ormsgpack.packb({"event": "audio", "audio": audio(text)}))
        self._to_send.put_nowait(ormsgpack.packb({"event": "finish", "reason": "stop"}))
        self._note("finished")
        self._closed()

    def __aiter__(self):
        return self._messages()

    async def _messages(self):
        while (message := await self._to_send.get()) is not None:
            yield message

    async def close(self) -> None:
        self.abort()

    def abort(self) -> None:
        self._voicing.cancel()
        self._closed()

    def _closed(self) -> None:
        if self.state is State.OPEN:
            self.state = State.CLOSED
            self._note("closed")
            self._to_send.put_nowait(None)

    def _note(self, what: str) -> None:
        self.fish.note(f"{self.number} {what}")


class FishUnderTest(FishTTS):
    """The service, connecting to the fake. There is no transport to say when her voice
    stops playing, so unless `pausing` it does not hold what follows a reply back until
    then."""

    def __init__(self, fish: FakeFish, pausing: bool = False) -> None:
        super().__init__(
            api_key="fish-key",
            sample_rate=16000,
            settings=FishAudioTTSService.Settings(voice="mano-voice", model="s2.1-pro-free"),
        )
        self._pause_frame_processing = pausing
        self.fish = fish

    async def _websocket_connect(self, uri: str, **kwargs: Any) -> Any:
        return await self.fish.connect()


class Speaker(FrameProcessor):
    """Where the transport's output would be: logs the audio, the `segment-playing`
    messages and the interruptions that reach it, into the fake's log."""

    def __init__(self, fish: FakeFish) -> None:
        super().__init__()
        self.fish = fish

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSAudioRawFrame):
            text = frame.audio.rstrip(b"\0").decode()
            self.fish.note(f"audio {text}")
        elif isinstance(frame, OutputTransportMessageFrame):
            data = frame.message["data"]
            assert frame.message["type"] == "server-message" and data["type"] == "segment-playing"
            self.fish.note(f"playing {data['reply']}/{data['segment']}")
        elif isinstance(frame, InterruptionFrame):
            self.fish.note("interrupted")
        await self.push_frame(frame, direction)


async def run(
    *frames: Frame, fish: FakeFish | None = None, hang_up: bool = False, pausing: bool = False
) -> FakeFish:
    """Run the frames through, spaced out, then end the call once Fish Audio has had time
    to voice what it was sent, or, with `hang_up`, cancel it straight away; returns the
    fake, with its log. With `pausing`, the service holds back what follows a reply."""
    fish = fish or FakeFish()
    spaced: list[Frame] = []
    for frame in frames:
        spaced += [frame, SleepFrame(0.05)]
    end = [CancelFrame()] if hang_up else [SleepFrame(SYNTHESIS * 3)]
    async with asyncio.timeout(15):
        await run_test(
            Pipeline([FishUnderTest(fish, pausing), Speaker(fish)]),
            frames_to_send=[*spaced, *end],
            send_end_frame=not hang_up,
        )
    return fish


def heard(fish: FakeFish) -> list[str]:
    """What reached the transport."""
    return [e for e in fish.log if e.startswith(("audio", "playing", "interrupted"))]


def reply(number: int, *segments: list[str]) -> list[Frame]:
    """Reply `number`, its segments' Japanese sentence by sentence, each segment complete."""
    frames: list[Frame] = [LLMFullResponseStartFrame()]
    for segment, sentences in enumerate(segments):
        frames += [SegmentTextFrame(text, number, segment) for text in sentences]
        frames.append(SegmentCompleteFrame(number, segment))
    return [*frames, LLMFullResponseEndFrame()]


async def test_each_segment_is_voiced_in_a_session_of_its_own_announced_as_it_plays():
    fish = await run(*reply(1, ["ほわっ。", "おはよう。"], ["今日も。"]))

    assert heard(fish) == [
        "playing 1/0", "audio ほわっ。", "audio おはよう。", "playing 1/1", "audio 今日も。"
    ]
    assert fish.of(1) == [
        "connected", "start", "text ほわっ。", "flush", "text おはよう。", "flush", "stop",
        "finished", "closed",
    ]
    assert fish.of(2) == [
        "connected", "start", "text 今日も。", "flush", "stop", "finished", "closed"
    ]


async def test_the_next_segments_connection_is_open_before_the_last_one_finishes():
    fish = await run(*reply(1, ["ほわっ。", "おはよう。"], ["今日も。"]))

    assert fish.log.index("2 connected") < fish.log.index("1 finished")
    assert fish.at["2 text 今日も。"] - fish.at["1 finished"] < CONNECTION / 2


async def test_a_segment_is_voiced_in_full_once_complete_without_waiting_for_the_next():
    fish = await run(
        LLMFullResponseStartFrame(),
        SegmentTextFrame("ほわっ。", 1, 0),
        SegmentCompleteFrame(1, 0),
        SleepFrame(SYNTHESIS * 3),
        SegmentTextFrame("今日も。", 1, 1),
        SegmentCompleteFrame(1, 1),
        LLMFullResponseEndFrame(),
    )

    assert fish.of(1)[2:5] == ["text ほわっ。", "flush", "stop"]
    assert fish.at["1 finished"] < fish.at["2 text 今日も。"] - SYNTHESIS
    assert heard(fish) == ["playing 1/0", "audio ほわっ。", "playing 1/1", "audio 今日も。"]


async def test_the_connection_left_open_after_a_reply_voices_the_next_with_one_more_opened():
    fish = await run(*reply(1, ["ほわっ。"]), SleepFrame(SYNTHESIS * 2), *reply(2, ["うん。"]))

    assert len(fish.sockets) == 3
    assert fish.of(2) == [
        "connected", "start", "text うん。", "flush", "stop", "finished", "closed"
    ]
    assert fish.of(3) == ["connected", "start", "closed"]  # hung up
    assert heard(fish) == ["playing 1/0", "audio ほわっ。", "playing 2/0", "audio うん。"]


async def test_a_connection_closed_while_left_open_is_replaced_as_the_next_reply_starts():
    fish = await run(
        *reply(1, ["ほわっ。"]),
        SleepFrame(SYNTHESIS * 4),
        *reply(2, ["うん。"]),
        fish=FakeFish(idle_timeout=SYNTHESIS * 2),
    )

    assert fish.of(2) == ["connected", "start", "closed"]  # by Fish Audio, left idle
    assert "text うん。" in fish.of(3)
    assert heard(fish)[-2:] == ["playing 2/0", "audio うん。"]


async def test_a_segment_no_connection_voices_is_not_announced():
    fish = await run(
        *reply(1, ["ほわっ。"], ["今日も。", "ね。"]),
        fish=FakeFish(refused=(2, 3, 4)),  # every connection the second segment tries
    )

    assert fish.log.count("refused") == 3
    assert heard(fish) == ["playing 1/0", "audio ほわっ。"]


async def test_a_segment_is_announced_once_a_connection_voices_it():
    fish = await run(
        *reply(1, ["ほわっ。"], ["今日も。", "ね。"]),
        fish=FakeFish(refused=(2, 3)),  # the second segment's connection, tried again
    )

    assert fish.log.count("refused") == 2  # 今日も is lost
    assert heard(fish) == ["playing 1/0", "audio ほわっ。", "playing 1/1", "audio ね。"]


async def test_an_interruption_stops_her_at_once_and_drops_the_spare_connection_too():
    fish = await run(
        LLMFullResponseStartFrame(),
        SegmentTextFrame("ほわっ。", 1, 0),
        SegmentTextFrame("おはよう。", 1, 0),
        SegmentCompleteFrame(1, 0),  # waits for the segment to finish
        SegmentTextFrame("今日も。", 1, 1),  # waits behind it
        SleepFrame(SYNTHESIS * 0.7),  # ほわっ is in, おはよう is not
        BotStartedSpeakingFrame(),
        InterruptionFrame(),
        LLMFullResponseEndFrame(),
        SleepFrame(CONNECTION * 3),
        *reply(2, ["うん。"]),
    )

    assert heard(fish) == ["playing 1/0", "audio ほわっ。", "interrupted", "playing 2/0", "audio うん。"]
    assert "finished" not in fish.of(1) and fish.of(1)[-1] == "closed"
    assert fish.of(2) == ["connected", "start", "closed"]
    assert fish.log.index("interrupted") < fish.log.index("3 connected")
    assert "text うん。" in fish.of(3)


async def test_hanging_up_while_a_segment_finishes_closes_every_connection_at_once():
    loop = asyncio.get_running_loop()
    started = loop.time()

    fish = await run(
        LLMFullResponseStartFrame(),
        SegmentTextFrame("ほわっ。", 1, 0),
        SegmentCompleteFrame(1, 0),  # waits for the segment to finish
        hang_up=True,
    )

    assert loop.time() - started < CONNECTION + SYNTHESIS
    assert fish.of(1)[-1] == "closed" and "finished" not in fish.of(1)
    await asyncio.sleep(CONNECTION)  # the next segment's connection was still opening
    assert all(socket.state is State.CLOSED for socket in fish.sockets)


async def test_hanging_up_while_her_last_reply_plays_closes_every_connection():
    fish = await run(*reply(1, ["ほわっ。"]), SleepFrame(SYNTHESIS * 2), hang_up=True, pausing=True)

    assert heard(fish) == ["playing 1/0", "audio ほわっ。"]
    assert all(socket.state is State.CLOSED for socket in fish.sockets)
