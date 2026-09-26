"""Voice calls: a thin Pipecat pipeline around the conversation engine.

    browser mic → Soniox (speech to text, zh/ja) → CallTurns → Fish Audio → browser speaker
                                                      ↓
                                     subtitles and the transcript, over the data channel

Pipecat's own LLM services and context aggregators are not used: every utterance,
spoken or typed during the call, goes through the same conversation engine as a
text turn and lands in the same conversation record.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Literal

from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    EndWorkerFrame,
    Frame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    StartFrame,
    TextFrame,
    TranscriptionFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineWorker, ProcessorUnusablePolicy
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.frameworks.rtvi.frames import (
    RTVIClientMessageFrame,
    RTVIServerMessageFrame,
)
from pipecat.services.fish.tts import FishAudioTTSService
from pipecat.services.soniox.stt import SonioxSTTService
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.turns.user_turn_processor import UserTurnProcessor
from pipecat.turns.user_turn_strategies import ExternalUserTurnStrategies
from pipecat.workers.runner import WorkerRunner

from eidolon.characters import Character
from eidolon.config import Settings
from eidolon.engine import ConversationEngine, TurnDone
from eidolon.reply_format import SegmentDelta
from eidolon.store import Conversation

log = logging.getLogger(__name__)

Quality = Literal["low", "standard", "high"]

_SAMPLE_RATES: dict[Quality, int] = {"low": 16000, "standard": 24000, "high": 44100}
"""Call quality is the sample rate the character's speech is synthesised at. It does not
change the network traffic: WebRTC always sends Opus at 48 kHz."""


@dataclass(frozen=True)
class Call:
    """A call the browser asked for: which conversation, how it wants the audio, and the
    time zone its device reports."""

    conversation: Conversation
    character: Character
    muted: bool
    quality: Quality
    device_timezone: str | None = None


@dataclass(frozen=True)
class CallLimits:
    """How long one call may last and how many turns it may take; None is no limit. Once
    either is reached, the reply in progress is finished and the call hangs up."""

    duration: timedelta | None = None
    turns: int | None = None


CallStarter = Callable[[SmallWebRTCConnection, Call], Awaitable[None]]
"""Starts serving a call on a freshly negotiated connection, without waiting for it to end."""


def serve_calls(settings: Settings, engine: ConversationEngine) -> CallStarter | None:
    """Serves calls with Soniox and Fish Audio; None until both are configured."""
    soniox_key, fish_key = settings.soniox_api_key, settings.fish_audio_api_key
    if not soniox_key or not fish_key:
        return None
    fish_model = settings.fish_audio_model
    usage = settings.usage_limits
    limits = CallLimits(
        timedelta(minutes=usage.call_minutes) if usage.call_minutes else None,
        usage.turns_per_call,
    )
    running: set[asyncio.Task] = set()

    async def start(connection: SmallWebRTCConnection, call: Call) -> None:
        task = asyncio.create_task(
            _serve(connection, call, engine, limits, soniox_key, fish_key, fish_model)
        )
        running.add(task)  # keep a reference until the call ends
        task.add_done_callback(running.discard)

    return start


async def _serve(
    connection: SmallWebRTCConnection,
    call: Call,
    engine: ConversationEngine,
    limits: CallLimits,
    soniox_key: str,
    fish_key: str,
    fish_model: str,
) -> None:
    sample_rate = _SAMPLE_RATES[call.quality]
    transport = SmallWebRTCTransport(
        connection,
        TransportParams(
            audio_in_enabled=True, audio_out_enabled=True, audio_out_sample_rate=sample_rate
        ),
    )
    # Soniox decides where an utterance ends; the turn processor turns its proposals
    # into interruptions of the character's voice.
    stt = SonioxSTTService(
        api_key=soniox_key,
        vad_force_turn_endpoint=False,
        settings=SonioxSTTService.Settings(language_hints=[Language.ZH, Language.JA]),
    )
    tts = FishAudioTTSService(
        api_key=fish_key,
        sample_rate=sample_rate,
        settings=FishAudioTTSService.Settings(voice=call.character.voice_id, model=fish_model),
    )
    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            UserTurnProcessor(user_turn_strategies=ExternalUserTurnStrategies()),
            CallTurns(engine, call, limits),
            tts,
            transport.output(),
        ]
    )
    # A service that can no longer work (say, a rejected API key) ends the call
    # instead of leaving the user talking into silence.
    worker = PipelineWorker(pipeline, processor_unusable_policy=ProcessorUnusablePolicy.CANCEL)

    @transport.event_handler("on_client_disconnected")
    async def hang_up(transport: SmallWebRTCTransport, connection: SmallWebRTCConnection) -> None:
        await worker.cancel()

    try:
        await WorkerRunner(handle_sigint=False).run(worker)
    except Exception:
        log.exception("call in conversation %s failed", call.conversation.id)
    finally:
        await connection.disconnect()  # lets the browser know the call is over


class CallTurns(FrameProcessor):
    """Takes turns in the conversation for the call, one utterance at a time.

    Utterances come from speech recognition (a final transcription) or from text
    typed during the call (a `user-text` client message). Each goes through the
    conversation engine; the reply's Japanese is sent on as text for TTS, and the
    browser gets the same events as a text turn (`user`, `delta`, `done` or
    `error`) as server messages, which carry the subtitles.

    A `mute` client message decides whether replies from then on are voiced at all. An
    interruption (the user starts talking) stops voicing the reply in progress;
    the reply still completes and is recorded, as the browser shows it in full.

    When the call reaches its limits, the browser gets an `ended` message saying why,
    and the call ends once the last reply has been voiced; what is said after that is
    not taken up.
    """

    def __init__(
        self, engine: ConversationEngine, call: Call, limits: CallLimits = CallLimits()
    ) -> None:
        super().__init__()
        self._engine = engine
        self._call = call
        self._limits = limits
        self._muted = call.muted
        self._inputs: asyncio.Queue[str | None] = asyncio.Queue()  # None: time is up
        self._worker: asyncio.Task | None = None
        self._timer: asyncio.Task | None = None
        self._voicing = False
        self._time_up: str | None = None  # why the call is over, once time is up
        self._ended = False

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, StartFrame):
            await self.push_frame(frame, direction)
            self._worker = self.create_task(self._take_turns())
            if self._limits.duration is not None:
                self._timer = self.create_task(self._time(self._limits.duration))
        elif isinstance(frame, TranscriptionFrame):
            self._take_up(frame.text)
        elif isinstance(frame, RTVIClientMessageFrame):
            self._handle_client_message(frame)
        elif isinstance(frame, InterruptionFrame):
            self._voicing = False
            await self.push_frame(frame, direction)
        elif isinstance(frame, EndFrame):
            await self._inputs.join()  # a graceful end lets queued turns finish
            await self._stop_worker()
            await self.push_frame(frame, direction)
        elif isinstance(frame, CancelFrame):
            await self._stop_worker()
            await self.push_frame(frame, direction)
        else:
            await self.push_frame(frame, direction)

    def _take_up(self, text: str) -> None:
        if text.strip() and not self._ended:
            self._inputs.put_nowait(text.strip())

    def _handle_client_message(self, frame: RTVIClientMessageFrame) -> None:
        data = frame.data if isinstance(frame.data, dict) else {}
        if frame.type == "user-text" and isinstance(data.get("text"), str):
            self._take_up(data["text"])
        elif frame.type == "mute" and isinstance(data.get("muted"), bool):
            self._muted = data["muted"]

    async def _take_turns(self) -> None:
        turns = 0
        while True:
            text = await self._inputs.get()
            try:
                if self._ended:
                    continue
                if self._time_up is not None:
                    await self._end(self._time_up)
                    continue
                assert text is not None
                if await self._turn(text, voiced=not self._muted):
                    turns += 1
                if self._limits.turns is not None and turns >= self._limits.turns:
                    await self._end(f"这次通话已经说了 {turns} 轮了")
            finally:
                self._inputs.task_done()

    async def _time(self, duration: timedelta) -> None:
        await asyncio.sleep(duration.total_seconds())
        self._time_up = f"这次通话已经满 {duration / timedelta(minutes=1):g} 分钟了"
        self._inputs.put_nowait(None)  # wakes the worker, after the turn in progress

    async def _end(self, reason: str) -> None:
        """Hang up, once what is already on its way to TTS has been voiced."""
        self._ended = True
        await self._send({"type": "ended", "message": f"{reason}，先挂断啦。想接着聊可以重新拨打。"})
        await self.push_frame(EndWorkerFrame(reason=reason))

    async def _turn(self, text: str, voiced: bool) -> bool:
        """Take one turn; whether it succeeded."""
        self._voicing = voiced
        succeeded = False
        await self.push_frame(LLMFullResponseStartFrame())
        try:
            async for event in self._engine.turn(
                self._call.conversation, text, self._call.device_timezone
            ):
                await self._send(asdict(event))
                if isinstance(event, SegmentDelta) and event.lang == "ja" and self._voicing:
                    await self.push_frame(TextFrame(event.text))
                succeeded = isinstance(event, TurnDone)
        finally:
            await self.push_frame(LLMFullResponseEndFrame())
        return succeeded

    async def _send(self, message: dict) -> None:
        await self.push_frame(RTVIServerMessageFrame(data=message))

    async def _stop_worker(self) -> None:
        if self._timer is not None:
            await self.cancel_task(self._timer)
            self._timer = None
        if self._worker is not None:
            await self.cancel_task(self._worker)
            self._worker = None
