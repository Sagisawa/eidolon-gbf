"""Voice calls: signalling, and a thin Pipecat pipeline around the conversation engine.

    browser mic → speech to text (zh/ja) → CallTurns → speech synthesis → browser speaker
                                               ↓
                              subtitles and the transcript, over the data channel

`Calls` is all the API sees: it answers the browser's offers, keeps each call to the
user who placed it, counts calls towards the user's limit, and serves each call until it
hangs up. Speech recognition and synthesis are the `Speech` port, Soniox and Fish Audio
in production.

Pipecat's own LLM services and context aggregators are not used: every utterance,
spoken or typed during the call, goes through the same conversation engine as a
text turn and lands in the same conversation record.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Literal, Protocol

from aiortc import RTCIceServer

from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    EndWorkerFrame,
    ErrorFrame,
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
from pipecat.services.stt_service import STTService
from pipecat.services.tts_service import TTSService
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.request_handler import IceCandidate as PipecatIceCandidate
from pipecat.transports.smallwebrtc.request_handler import (
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.turns.user_turn_processor import UserTurnProcessor
from pipecat.turns.user_turn_strategies import ExternalUserTurnStrategies
from pipecat.workers.runner import WorkerRunner

from eidolon.characters import Character
from eidolon.clock import Clock
from eidolon.config import IceServer, Settings
from eidolon.engine import ConversationEngine, TurnDone
from eidolon.reply_format import SegmentDelta
from eidolon.store import Conversation
from eidolon.usage import UsageLimiter, Use

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


CONNECT_TIMEOUT = timedelta(seconds=30)
"""How long a call may take to connect after it is answered; after that it is given up."""


class CallsUnavailable(Exception):
    """Voice calls are not configured."""

    def __init__(self) -> None:
        super().__init__("语音通话尚未配置，请联系管理员")


class CallNotFound(Exception):
    """No such call, or not the user's."""

    def __init__(self) -> None:
        super().__init__("通话不存在")


class CallFailed(Exception):
    """The call could not be set up; it did not count towards the user's limit."""

    def __init__(self) -> None:
        super().__init__("无法建立通话")


@dataclass(frozen=True)
class CallOptions:
    """How the browser wants a new call: muted or not, at what quality, and the time zone
    its device reports."""

    muted: bool = False
    quality: Quality = "standard"
    device_timezone: str | None = None


@dataclass(frozen=True)
class SessionDescription:
    """A WebRTC offer from the browser."""

    sdp: str
    type: str


@dataclass(frozen=True)
class IceCandidate:
    """One of the browser's ICE candidates; an empty `candidate` marks the end of them."""

    candidate: str
    sdp_mid: str
    sdp_mline_index: int


class Speech(Protocol):
    """The outside services a call hears and speaks with."""

    def stt(self) -> STTService:
        """Speech recognition for one call, in Chinese and Japanese."""
        ...

    def tts(self, voice_id: str, sample_rate: int) -> TTSService:
        """Speech synthesis for one call, in the character's voice."""
        ...


@dataclass(frozen=True)
class SonioxFishSpeech:
    """Soniox hears the user; Fish Audio speaks as the character."""

    soniox_key: str
    fish_key: str
    fish_model: str

    @classmethod
    def from_settings(cls, settings: Settings) -> "SonioxFishSpeech | None":
        """None until both services are configured."""
        if not settings.soniox_api_key or not settings.fish_audio_api_key:
            return None
        return cls(settings.soniox_api_key, settings.fish_audio_api_key, settings.fish_audio_model)

    def stt(self) -> STTService:
        # Soniox decides where an utterance ends; the turn processor turns its proposals
        # into interruptions of the character's voice.
        return SonioxSTTService(
            api_key=self.soniox_key,
            vad_force_turn_endpoint=False,
            settings=SonioxSTTService.Settings(language_hints=[Language.ZH, Language.JA]),
        )

    def tts(self, voice_id: str, sample_rate: int) -> TTSService:
        return FishAudioTTSService(
            api_key=self.fish_key,
            sample_rate=sample_rate,
            settings=FishAudioTTSService.Settings(voice=voice_id, model=self.fish_model),
        )


class Calls:
    """The user's voice calls, from signalling to hanging up.

    A new call counts towards the user's limit when it is offered, and is given back
    unless it connects: a call that closes or times out before connecting, or that ends
    on a failing voice service before any turn is recorded, was not connected. Only the
    user who placed a call can renegotiate it or add ICE candidates to it.
    """

    def __init__(
        self,
        settings: Settings,
        engine: ConversationEngine,
        usage: UsageLimiter,
        speech: Speech | None,
        clock: Clock,
    ) -> None:
        self._settings = settings
        self._engine = engine
        self._usage = usage
        self._speech = speech
        self._clock = clock
        limits = settings.usage_limits
        self._limits = CallLimits(
            timedelta(minutes=limits.call_minutes) if limits.call_minutes else None,
            limits.turns_per_call,
        )
        self._webrtc = SmallWebRTCRequestHandler(
            ice_servers=[RTCIceServer(**server) for server in settings.ice_servers]
        )
        self._owners: dict[str, str] = {}  # peer connection id → the user it belongs to
        self._live: set[_LiveCall] = set()

    def ice_servers(self, user_id: str) -> list[IceServer]:
        """What the browser needs before calling, with TURN credentials of its own."""
        self._require_speech()
        servers = list(self._settings.ice_servers)
        if self._settings.turn is not None:
            servers.append(self._settings.turn.credentials(user_id, self._clock()))
        return servers

    async def start(
        self,
        user_id: str,
        conversation: Conversation,
        character: Character,
        options: CallOptions,
        offer: SessionDescription,
    ) -> dict:
        """Answer a new call into the user's `conversation` with `character`. Raises
        OverLimit when the user has no calls left this hour."""
        speech = self._require_speech()
        use = self._usage.take(user_id, "call")
        call = Call(conversation, character, options.muted, options.quality, options.device_timezone)
        connections: list[SmallWebRTCConnection] = []
        started: list[_LiveCall] = []

        async def serve(connection: SmallWebRTCConnection) -> None:
            connections.append(connection)

            @connection.event_handler("closed")
            async def forget(connection: SmallWebRTCConnection) -> None:
                self._owners.pop(connection.pc_id, None)

            live = _LiveCall(connection, call, self._engine, speech, self._limits, use)
            self._live.add(live)
            live.start(on_done=self._live.discard)
            started.append(live)

        answer = await self._answer(SmallWebRTCRequest(offer.sdp, offer.type), serve)
        if answer is None or not started:
            if started:
                await started[0].hang_up()
            elif connections:  # the pipeline could not be built; Pipecat only logs why
                await connections[0].disconnect()
            use.give_back()
            raise CallFailed()
        self._owners[answer["pc_id"]] = user_id
        return answer

    async def renegotiate(
        self, user_id: str, pc_id: str, offer: SessionDescription, restart: bool = False
    ) -> dict:
        """Renegotiate one of the user's calls, possibly on a fresh peer connection; free."""
        self._require_speech()
        self._require_owner(user_id, pc_id)
        request = SmallWebRTCRequest(offer.sdp, offer.type, pc_id, restart)
        answer = await self._answer(request, _no_new_connection)
        if answer is None:
            raise CallFailed()
        self._owners[answer["pc_id"]] = user_id
        return answer

    async def add_candidates(
        self, user_id: str, pc_id: str, candidates: Sequence[IceCandidate]
    ) -> None:
        """Take ICE candidates the browser trickles in for one of the user's calls."""
        self._require_owner(user_id, pc_id)
        patch = SmallWebRTCPatchRequest(
            pc_id,
            [PipecatIceCandidate(c.candidate, c.sdp_mid, c.sdp_mline_index) for c in candidates],
        )
        await self._webrtc.handle_patch_request(patch)

    async def hang_up(self, user_id: str) -> None:
        """Hang up the user's calls and wait for them to end; a reply in progress is dropped."""
        await asyncio.gather(
            *(live.hang_up() for live in list(self._live) if live.user_id == user_id)
        )

    async def aclose(self) -> None:
        """Hang up every call and wait for them to end; a reply in progress is dropped."""
        await asyncio.gather(*(live.hang_up() for live in list(self._live)))
        await self._webrtc.close()

    async def _answer(
        self,
        request: SmallWebRTCRequest,
        serve: Callable[[SmallWebRTCConnection], Awaitable[None]],
    ) -> dict | None:
        try:
            return await self._webrtc.handle_web_request(request, serve)
        except Exception:
            log.exception("could not set up a call")
            return None

    def _require_speech(self) -> Speech:
        if self._speech is None:
            raise CallsUnavailable()
        return self._speech

    def _require_owner(self, user_id: str, pc_id: str) -> None:
        if self._owners.get(pc_id) != user_id:
            raise CallNotFound()


async def _no_new_connection(connection: SmallWebRTCConnection) -> None:
    """A renegotiation reuses the call's connection; the call is already being served."""


class _LiveCall:
    """One call being served on its connection: the pipeline from the browser's microphone
    through the conversation engine to the character's voice."""

    def __init__(
        self,
        connection: SmallWebRTCConnection,
        call: Call,
        engine: ConversationEngine,
        speech: Speech,
        limits: CallLimits,
        use: Use,
    ) -> None:
        self._connection = connection
        self._call = call
        self._use = use
        sample_rate = _SAMPLE_RATES[call.quality]
        transport = SmallWebRTCTransport(
            connection,
            TransportParams(
                audio_in_enabled=True, audio_out_enabled=True, audio_out_sample_rate=sample_rate
            ),
        )
        self._turns = CallTurns(engine, call, limits)
        pipeline = Pipeline(
            [
                transport.input(),
                speech.stt(),
                UserTurnProcessor(user_turn_strategies=ExternalUserTurnStrategies()),
                self._turns,
                speech.tts(call.character.voice_id, sample_rate),
                transport.output(),
            ]
        )
        # A service that can no longer work (say, a rejected API key) ends the call
        # instead of leaving the user talking into silence.
        self._worker = PipelineWorker(
            pipeline, processor_unusable_policy=ProcessorUnusablePolicy.CANCEL
        )
        self._connected = asyncio.Event()
        self._service_failed = False
        self._hung_up = False
        self._task: asyncio.Task | None = None

        @transport.event_handler("on_client_connected")
        async def connected(transport: SmallWebRTCTransport, _: SmallWebRTCConnection) -> None:
            self._connected.set()

        @transport.event_handler("on_client_disconnected")
        async def hang_up(transport: SmallWebRTCTransport, _: SmallWebRTCConnection) -> None:
            await self._worker.cancel()

        @self._worker.event_handler("on_pipeline_error")
        async def failed(worker: PipelineWorker, error: ErrorFrame) -> None:
            if error.fatal or (error.processor is not None and not error.processor.is_usable):
                self._service_failed = True

    @property
    def user_id(self) -> str:
        return self._call.conversation.user_id

    def start(self, on_done: Callable[["_LiveCall"], None]) -> None:
        """Serve the call in the background; `on_done` is told once it has ended."""
        self._task = asyncio.create_task(self._serve())
        self._task.add_done_callback(lambda _: on_done(self))

    async def hang_up(self) -> None:
        """End the call now, dropping any reply in progress, and wait until it has ended."""
        self._hung_up = True
        await self._worker.cancel()
        if self._task is not None:
            await asyncio.wait({self._task})

    async def _serve(self) -> None:
        try:
            if not self._hung_up:  # hung up before it even started
                await self._run()
        except Exception:
            log.exception("call in conversation %s failed", self._call.conversation.id)
            self._service_failed = True
        finally:
            if not self._connected.is_set() or (
                self._service_failed and self._turns.recorded == 0
            ):
                self._use.give_back()
            await self._connection.disconnect()  # lets the browser know the call is over

    async def _run(self) -> None:
        running = asyncio.create_task(WorkerRunner(handle_sigint=False).run(self._worker))
        connected = asyncio.create_task(self._connected.wait())
        try:
            await asyncio.wait(
                {running, connected},
                timeout=CONNECT_TIMEOUT.total_seconds(),
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            connected.cancel()
        if not self._connected.is_set() and not running.done():
            log.info("call in conversation %s never connected", self._call.conversation.id)
            await self._worker.cancel()
        await running


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
        self.recorded = 0
        """How many turns the call has recorded so far."""

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
        while True:
            text = await self._inputs.get()
            try:
                if self._ended:
                    continue
                if self._time_up is not None:
                    await self._end(self._time_up)
                    continue
                assert text is not None
                await self._turn(text, voiced=not self._muted)
                if self._limits.turns is not None and self.recorded >= self._limits.turns:
                    await self._end(f"这次通话已经说了 {self.recorded} 轮了")
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

    async def _turn(self, text: str, voiced: bool) -> None:
        """Take one turn. Only a turn whose reply is recorded counts as one: a rejected or
        failed turn does not count towards the call's limit."""
        self._voicing = voiced
        await self.push_frame(LLMFullResponseStartFrame())
        try:
            async for event in self._engine.turn(
                self._call.conversation, text, self._call.device_timezone
            ):
                if isinstance(event, TurnDone):  # recorded by now, whatever happens next
                    self.recorded += 1
                await self._send(asdict(event))
                if isinstance(event, SegmentDelta) and event.lang == "ja" and self._voicing:
                    await self.push_frame(TextFrame(event.text))
        finally:
            await self.push_frame(LLMFullResponseEndFrame())

    async def _send(self, message: dict) -> None:
        await self.push_frame(RTVIServerMessageFrame(data=message))

    async def _stop_worker(self) -> None:
        if self._timer is not None:
            await self.cancel_task(self._timer)
            self._timer = None
        if self._worker is not None:
            await self.cancel_task(self._worker)
            self._worker = None
