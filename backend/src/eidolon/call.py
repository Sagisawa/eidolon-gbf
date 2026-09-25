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
from typing import Literal

from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
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
from eidolon.store import Conversation

log = logging.getLogger(__name__)

Quality = Literal["low", "standard", "high"]

_SAMPLE_RATES: dict[Quality, int] = {"low": 16000, "standard": 24000, "high": 44100}
"""Call quality is the sample rate the character's voice is synthesised at."""


@dataclass(frozen=True)
class Call:
    """A call the browser asked for: which conversation, and how it wants the audio."""

    conversation: Conversation
    character: Character
    muted: bool
    quality: Quality


CallStarter = Callable[[SmallWebRTCConnection, Call], Awaitable[None]]
"""Starts serving a call on a freshly negotiated connection, without waiting for it to end."""


def voice_calls(settings: Settings, engine: ConversationEngine) -> CallStarter | None:
    """Serves calls with Soniox and Fish Audio; None until both are configured."""
    soniox_key, fish_key = settings.soniox_api_key, settings.fish_audio_api_key
    if not soniox_key or not fish_key:
        return None
    running: set[asyncio.Task] = set()

    async def start(connection: SmallWebRTCConnection, call: Call) -> None:
        task = asyncio.create_task(_serve(connection, call, engine, soniox_key, fish_key))
        running.add(task)  # keep a reference until the call ends
        task.add_done_callback(running.discard)

    return start


async def _serve(
    connection: SmallWebRTCConnection,
    call: Call,
    engine: ConversationEngine,
    soniox_key: str,
    fish_key: str,
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
        settings=FishAudioTTSService.Settings(voice=call.character.voice_id),
    )
    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            UserTurnProcessor(user_turn_strategies=ExternalUserTurnStrategies()),
            CallTurns(engine, call),
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

    A `mute` client message decides whether later replies are voiced at all. An
    interruption (the user starts talking) stops voicing the reply in progress;
    the reply still completes and is recorded, as the browser shows it in full.
    """

    def __init__(self, engine: ConversationEngine, call: Call) -> None:
        super().__init__()
        self._engine = engine
        self._call = call
        self._muted = call.muted
        self._inputs: asyncio.Queue[tuple[str, bool]] = asyncio.Queue()
        self._worker: asyncio.Task | None = None
        self._voicing = False

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, StartFrame):
            await self.push_frame(frame, direction)
            self._worker = self.create_task(self._take_turns())
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
        if text.strip():
            self._inputs.put_nowait((text.strip(), self._muted))

    def _handle_client_message(self, frame: RTVIClientMessageFrame) -> None:
        data = frame.data if isinstance(frame.data, dict) else {}
        if frame.type == "user-text" and isinstance(data.get("text"), str):
            self._take_up(data["text"][:2000])
        elif frame.type == "mute" and isinstance(data.get("muted"), bool):
            self._muted = data["muted"]

    async def _take_turns(self) -> None:
        while True:
            text, muted = await self._inputs.get()
            try:
                await self._turn(text, voiced=not muted)
            finally:
                self._inputs.task_done()

    async def _turn(self, text: str, voiced: bool) -> None:
        await self._send({"type": "user", "text": text})
        self._voicing = voiced
        await self.push_frame(LLMFullResponseStartFrame())
        try:
            async for event in self._engine.turn(self._call.conversation, text):
                if isinstance(event, TurnDone):
                    await self._send({"type": "done", "message": asdict(event.message)})
                    continue
                await self._send({"type": "delta", **asdict(event)})
                if event.lang == "ja" and self._voicing:
                    await self.push_frame(TextFrame(event.text))
        except Exception:
            log.exception("call turn failed in conversation %s", self._call.conversation.id)
            await self._send({"type": "error", "message": "角色暂时无法回复，请稍后再试。"})
        finally:
            await self.push_frame(LLMFullResponseEndFrame())

    async def _send(self, message: dict) -> None:
        await self.push_frame(RTVIServerMessageFrame(data=message))

    async def _stop_worker(self) -> None:
        if self._worker is not None:
            await self.cancel_task(self._worker)
            self._worker = None
