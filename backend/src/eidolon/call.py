"""Voice calls: signalling, and a thin Pipecat pipeline around the conversation engine.

    browser mic → speech to text (zh/ja) → CallTurns → speech synthesis → browser speaker
                                               ↓
                              subtitles and the transcript, over the data channel

`Calls` is all the API sees: it answers the browser's offers, keeps each call to the
user who placed it, counts calls towards the user's limit, and serves each call until it
hangs up. Speech recognition and synthesis are the `Speech` port, Soniox and Fish Audio
in production, on whoever's keys `OwnKeys.for_call` says; a failing own key ends the
call saying which. Whether a call counts towards the user's limit, and what the browser is
told when the backend ends it, is `CallOutcome`'s to decide; the call only reports to it.
Whose turn it is during the call, what is a follow-on and what interrupts the character, is
likewise `TurnTaking`'s.

Pipecat's own LLM services and context aggregators are not used: every utterance,
spoken or typed during the call, goes through the same conversation engine as a
text turn and lands in the same conversation record.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Literal, Protocol

import httpx
from aiortc import RTCIceServer

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    CancelFrame,
    EndFrame,
    EndWorkerFrame,
    ErrorFrame,
    Frame,
    InterimTranscriptionFrame,
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
from pipecat.processors.frameworks.rtvi.models import ServerMessage
from pipecat.services.fish.tts import FishAudioTTSService
from pipecat.services.soniox.stt import SonioxSTTService
from pipecat.services.stt_service import STTService
from pipecat.services.tts_service import InterruptibleTTSService, TTSService
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

from eidolon.call_outcome import CallOutcome, EndReason
from eidolon.characters import Character
from eidolon.clock import Clock
from eidolon.config import IceServer, Settings
from eidolon.engine import ConversationEngine, TurnDone
from eidolon.llm import TurnLLMs
from eidolon.own_keys import (
    SERVICE_LABELS,
    CallKeys,
    CallsUnavailable,
    OwnKeyRejected,
    OwnKeys,
    Service,
)
from eidolon.reply_format import SegmentComplete, SegmentDelta, SpeechDelta
from eidolon.store import Conversation, Store
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
from eidolon.usage import UsageLimiter

log = logging.getLogger(__name__)

Quality = Literal["low", "standard", "high"]

_SAMPLE_RATES: dict[Quality, int] = {"low": 16000, "standard": 24000, "high": 44100}
"""Call quality is the sample rate the character's speech is synthesised at. It does not
change the network traffic: WebRTC always sends Opus at 48 kHz."""


@dataclass(frozen=True)
class Call:
    """A call the browser asked for: which conversation, the models its turns run on, how
    it wants the audio, and the time zone its device reports."""

    conversation: Conversation
    character: Character
    llms: TurnLLMs
    muted: bool
    quality: Quality
    device_timezone: str | None = None


@dataclass(frozen=True)
class CallLimits:
    """How long one call may last and how many turns it may take; None is no limit. Once
    either is reached, the reply in progress is finished and the call hangs up."""

    duration: timedelta | None = None
    turns: int | None = None


USER_CHECK_INTERVAL = 5.0
"""How often, in seconds, calls are checked for users banned or deleted since they called,
from the admin command line in another process."""

CONNECT_TIMEOUT = timedelta(seconds=30)
"""How long a call may take to connect after it is answered; after that it is given up."""


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
    """The outside services a call hears and speaks with, on whoever's key is given."""

    def stt(self, api_key: str) -> STTService:
        """Speech recognition for one call, in Chinese and Japanese."""
        ...

    def tts(self, api_key: str, voice_id: str, sample_rate: int) -> TTSService:
        """Speech synthesis for one call, in the character's voice."""
        ...

    async def check(self, service: Service, api_key: str) -> None:
        """Raise OwnKeyRejected saying why, unless `api_key` works for `service`
        ("stt" or "tts")."""
        ...


class InterruptsFirst(InterruptibleTTSService):
    """A websocket TTS whose voice stops as soon as it is interrupted.

    Interrupted while the character speaks, the service reconnects, dropping what it has
    yet to send of the old reply. Pipecat reconnects before passing the interruption on,
    which held up the speaker's stop, and the server messages behind it, for the second
    or so Fish Audio takes; here the interruption is passed on at once and the
    reconnection goes on behind it, with the next reply waiting for it. Mixed in ahead
    of the service: `class FishTTS(InterruptsFirst, FishAudioTTSService)`."""

    _reconnecting: asyncio.Task | None = None

    async def _handle_interruption(self, frame: InterruptionFrame, direction: FrameDirection):
        reconnect = self._bot_speaking or self._tts_started
        self._tts_started = False
        # What InterruptibleTTSService does but for reconnecting, which follows.
        await super(InterruptibleTTSService, self)._handle_interruption(frame, direction)
        if reconnect:
            self._reconnecting = self.create_task(self._reconnect(self._reconnecting))

    async def _reconnect(self, previous: asyncio.Task | None) -> None:
        if previous is not None:
            await asyncio.wait([previous])  # however it ended
        await self._disconnect()
        await self._connect()

    async def _reconnected(self) -> None:
        """Wait until any reconnection is over. Waiting is cut short by the next
        interruption, which must not cut the reconnection short with it; a reconnection
        that failed leaves the service disconnected, to connect when it next speaks."""
        reconnecting = self._reconnecting
        if reconnecting is not None:
            await asyncio.wait([reconnecting])
            if self._reconnecting is reconnecting:  # not reconnecting again since
                self._reconnecting = None

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        await self._reconnected()
        # Mixed in ahead of the service, which implements it.
        async for frame in super().run_tts(text, context_id):  # pyright: ignore[reportAbstractUsage]
            yield frame

    async def flush_audio(self, context_id: str | None = None) -> None:
        await self._reconnected()
        await super().flush_audio(context_id)

    async def stop(self, frame: EndFrame) -> None:
        await self._stop_reconnecting()
        await super().stop(frame)

    async def cancel(self, frame: CancelFrame) -> None:
        await self._stop_reconnecting()
        await super().cancel(frame)

    async def _stop_reconnecting(self) -> None:
        if self._reconnecting is not None:
            await self.cancel_task(self._reconnecting)
            self._reconnecting = None


class FishTTS(InterruptsFirst, FishAudioTTSService):
    """Fish Audio, speaking as the character."""


@dataclass(frozen=True)
class SonioxFishSpeech:
    """Soniox hears the user; Fish Audio speaks as the character."""

    fish_model: str

    SONIOX_MODELS_URL = "https://api.soniox.com/v1/models"
    FISH_CREDIT_URL = "https://api.fish.audio/wallet/self/api-credit"

    def stt(self, api_key: str) -> STTService:
        # Soniox decides where an utterance ends; the turn processor turns its proposals
        # into interruptions of the character's voice.
        return SonioxSTTService(
            api_key=api_key,
            vad_force_turn_endpoint=False,
            settings=SonioxSTTService.Settings(language_hints=[Language.ZH, Language.JA]),
        )

    def tts(self, api_key: str, voice_id: str, sample_rate: int) -> TTSService:
        return FishTTS(
            api_key=api_key,
            sample_rate=sample_rate,
            settings=FishAudioTTSService.Settings(voice=voice_id, model=self.fish_model),
        )

    async def check(self, service: Service, api_key: str) -> None:
        """Asks for something that costs nothing: Soniox's models, Fish Audio's balance."""
        url = self.SONIOX_MODELS_URL if service == "stt" else self.FISH_CREDIT_URL
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=10)) as client:
                res = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
        except httpx.HTTPError as e:
            raise OwnKeyRejected(f"连不上 {httpx.URL(url).host}：{e!r}") from None
        if res.is_error:
            raise OwnKeyRejected(f"{res.status_code} {res.text[:200]}")


class Calls:
    """The user's voice calls, from signalling to hanging up.

    Each new call has a `CallOutcome`, which takes it from the user's limit when it is
    offered and, told what happens to the call, decides whether it is given back and what
    the browser is told when the backend ends it. Only the user who placed a call can
    renegotiate it or add ICE candidates to it.
    """

    def __init__(
        self,
        settings: Settings,
        engine: ConversationEngine,
        usage: UsageLimiter,
        speech: Speech,
        clock: Clock,
        own_keys: OwnKeys,
        store: Store | None = None,
    ) -> None:
        """With `store`, calls of users banned or deleted meanwhile are hung up."""
        self._settings = settings
        self._engine = engine
        self._usage = usage
        self._speech = speech
        self._clock = clock
        self._own_keys = own_keys
        self._store = store
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
        self._watch: asyncio.Task | None = None  # hangs up banned and deleted users' calls

    def ice_servers(self, user_id: str) -> dict:
        """What the browser needs before calling: ICE servers, with TURN credentials of its
        own; how long a call may last, in seconds (None for no limit); and whether calls on
        the keys the user has now are exempt from the limit. Raises CallsUnavailable or
        OwnKeyFailed, as `OwnKeys.for_call` does, before anything is spent on a call that
        could not start."""
        keys = self._own_keys.for_call(user_id)
        servers: list[IceServer] = list(self._settings.ice_servers)
        if self._settings.turn is not None:
            servers.append(self._settings.turn.credentials(user_id, self._clock()))
        duration = self._limits.duration
        return {
            "iceServers": servers,
            "maxCallSeconds": None if duration is None else int(duration.total_seconds()),
            "callExempt": keys.exempt,
        }

    async def start(
        self,
        user_id: str,
        conversation: Conversation,
        character: Character,
        options: CallOptions,
        offer: SessionDescription,
    ) -> dict:
        """Answer a new call into the user's `conversation` with `character`, on the keys
        `OwnKeys.for_call` says. Raises OverLimit when the user has no calls left this
        hour, unless the call is exempt."""
        keys = self._own_keys.for_call(user_id)
        outcome = CallOutcome(self._usage, user_id, keys.exempt)
        call = Call(
            conversation, character, keys.llms, options.muted, options.quality,
            options.device_timezone,
        )
        connections: list[SmallWebRTCConnection] = []
        started: list[_LiveCall] = []

        async def serve(connection: SmallWebRTCConnection) -> None:
            connections.append(connection)

            @connection.event_handler("closed")
            async def forget(connection: SmallWebRTCConnection) -> None:
                self._owners.pop(connection.pc_id, None)

            live = _LiveCall(
                connection, call, self._engine, self._speech, keys, self._limits, outcome
            )
            self._live.add(live)
            live.start(on_done=self._live.discard)
            started.append(live)
            if self._store is not None and (self._watch is None or self._watch.done()):
                self._watch = asyncio.create_task(self._hang_up_users_gone())

        answer = await self._answer(SmallWebRTCRequest(offer.sdp, offer.type), serve)
        if answer is None or not started:
            if started:
                await started[0].hang_up()
            elif connections:  # the pipeline could not be built; Pipecat only logs why
                await connections[0].disconnect()
            outcome.set_up_failed()
            raise CallFailed()
        self._owners[answer["pc_id"]] = user_id
        return answer

    async def renegotiate(
        self, user_id: str, pc_id: str, offer: SessionDescription, restart: bool = False
    ) -> dict:
        """Renegotiate one of the user's calls, possibly on a fresh peer connection; free."""
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

    async def _hang_up_users_gone(self) -> None:
        """While there are calls, hang up those of users banned or deleted meanwhile."""
        while self._live:
            await asyncio.sleep(USER_CHECK_INTERVAL)
            users = {live.user_id for live in self._live}
            assert self._store is not None
            for user_id in users - self._store.active_users(users):
                log.info("hanging up the calls of user %s, banned or deleted", user_id)
                await self.hang_up(user_id)

    async def aclose(self) -> None:
        """Hang up every call and wait for them to end; a reply in progress is dropped."""
        if self._watch is not None:
            self._watch.cancel()
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

    def _require_owner(self, user_id: str, pc_id: str) -> None:
        if self._owners.get(pc_id) != user_id:
            raise CallNotFound()


async def _no_new_connection(connection: SmallWebRTCConnection) -> None:
    """A renegotiation reuses the call's connection; the call is already being served."""


class _LiveCall:
    """One call being served on its connection: the pipeline from the browser's microphone
    through the conversation engine to the character's voice. What happens to the call is
    reported to its `CallOutcome`, and any `ended` message that hands back is sent on."""

    def __init__(
        self,
        connection: SmallWebRTCConnection,
        call: Call,
        engine: ConversationEngine,
        speech: Speech,
        keys: CallKeys,
        limits: CallLimits,
        outcome: CallOutcome,
    ) -> None:
        self._connection = connection
        self._call = call
        self._outcome = outcome
        sample_rate = _SAMPLE_RATES[call.quality]
        transport = SmallWebRTCTransport(
            connection,
            TransportParams(
                audio_in_enabled=True, audio_out_enabled=True, audio_out_sample_rate=sample_rate
            ),
        )
        self._turns = CallTurns(engine, call, outcome, limits)
        stt = speech.stt(keys.stt)
        tts = speech.tts(keys.tts, call.character.voice_id, sample_rate)
        own_services: dict[FrameProcessor, Service] = {
            processor: service
            for processor, service in ((stt, "stt"), (tts, "tts"))
            if service in keys.own
        }
        pipeline = Pipeline(
            [
                transport.input(),
                stt,
                UserTurnProcessor(user_turn_strategies=ExternalUserTurnStrategies()),
                self._turns,
                tts,
                transport.output(),
            ]
        )
        # A service that can no longer work (say, a rejected API key) ends the call
        # instead of leaving the user talking into silence.
        self._worker = PipelineWorker(
            pipeline, processor_unusable_policy=ProcessorUnusablePolicy.CANCEL
        )
        self._connected = asyncio.Event()
        self._hung_up = False
        self._task: asyncio.Task | None = None

        @transport.event_handler("on_client_connected")
        async def connected(transport: SmallWebRTCTransport, _: SmallWebRTCConnection) -> None:
            self._connected.set()
            self._turns.connected()

        @transport.event_handler("on_client_disconnected")
        async def hang_up(transport: SmallWebRTCTransport, _: SmallWebRTCConnection) -> None:
            await self._worker.cancel()

        @self._worker.event_handler("on_pipeline_error")
        async def failed(worker: PipelineWorker, error: ErrorFrame) -> None:
            if error.fatal or (error.processor is not None and not error.processor.is_usable):
                processor = error.processor
                self._report_failure(own_services.get(processor) if processor else None)

    @property
    def user_id(self) -> str:
        return self._call.conversation.user_id

    def _report_failure(self, own_service: Service | None = None) -> None:
        """A failing service ends the call. Whatever `CallOutcome` says to tell the browser
        about it is told now, while the call can still say so."""
        message = self._outcome.service_failed(own_service)
        if message is not None:
            self._connection.send_app_message(ServerMessage(data=message).model_dump())

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
            self._report_failure()
        finally:
            self._outcome.settle()
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


FOLLOW_ON_TIMEOUT = 4.0
"""How long, in seconds since the user was last heard, a follow-on may take to be
transcribed; after that it came to nothing (a cough, say) and the turn is replied to
again as it was. Soniox finalizes what it heard at most 3 s (its longest endpoint delay)
after the last word, and sends no transcription at all when it heard no words."""


class CallTurns(FrameProcessor):
    """Takes turns in the conversation for the call, one at a time, as its `TurnTaking`
    has them.

    What the user says comes from speech recognition (a final transcription) or from
    text typed during the call (a `user-text` client message). Each turn goes through
    the conversation engine; the reply's Japanese is sent on as text for TTS, delivery
    cues and all, and the browser gets the same events as a text turn (`user`, `delta`, `done` or `error`) as
    server messages, which carry the subtitles. A turn replied to afresh after a
    follow-on opens again with `user`; an interrupted one's `done` carries only the
    segments complete by then.

    Which of what the user says or types is a follow-on and which interrupts the
    character, when a reply is dropped, stopped or replied to afresh, and what of it is
    voiced, is `TurnTaking`'s to decide: the frames coming through, `mute` client
    messages and how each reply is getting on are reported to it as they happen, and what
    it says to do is done straight away. How long a follow-on may take to be transcribed
    (`FOLLOW_ON_TIMEOUT`) is timed here.

    Its time limit runs from when the call connects (`connected`), as the call screen's
    clock does. Each recorded turn is reported to the call's `CallOutcome`. When the call
    reaches its limits, the browser gets the `ended` message the outcome hands back, saying
    why and whether the call counted, and the call ends once the last reply has been voiced;
    what is said after that is not taken up.
    """

    def __init__(
        self,
        engine: ConversationEngine,
        call: Call,
        outcome: CallOutcome,
        limits: CallLimits = CallLimits(),
    ) -> None:
        super().__init__()
        self._engine = engine
        self._call = call
        self._outcome = outcome
        self._limits = limits
        self._turns = TurnTaking(text_only=call.muted)
        self._inputs: asyncio.Queue[str | None] = asyncio.Queue()  # None: time is up
        self._worker: asyncio.Task | None = None
        self._timer: asyncio.Task | None = None
        self._started = False  # the pipeline has started, so tasks can be created
        self._connected = False  # the browser has connected: the time limit runs
        self._time_up: str | None = None  # says the call is over, once time is up
        self._recorded = 0  # turns the call has recorded so far, for its turn limit
        # The turn in progress:
        self._turn_over = asyncio.Event()  # set once its reply is over
        self._reply: asyncio.Task | None = None  # the reply being given to it
        self._stop = asyncio.Event()  # set to have the reply go no further
        self._waiting: asyncio.Task | None = None  # times the follow-on waited for

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, StartFrame):
            await self.push_frame(frame, direction)
            self._worker = self.create_task(self._take_turns())
            self._started = True
            self._start_timer()
        elif isinstance(frame, TranscriptionFrame):
            await self._carry_out(self._turns.user_said(frame.text))
        elif isinstance(frame, InterimTranscriptionFrame):
            await self._carry_out(self._turns.user_heard())
            await self.push_frame(frame, direction)
        elif isinstance(frame, RTVIClientMessageFrame):
            await self._handle_client_message(frame)
        elif isinstance(frame, InterruptionFrame):
            await self._carry_out(self._turns.user_started_talking(), (frame, direction))
        elif isinstance(frame, BotStartedSpeakingFrame):
            await self._carry_out(self._turns.voice_started())
            await self.push_frame(frame, direction)
        elif isinstance(frame, BotStoppedSpeakingFrame):
            await self._carry_out(self._turns.voice_stopped())
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

    def connected(self) -> None:
        """The browser has connected (CONTEXT.md「接通」): the call's time starts running,
        and the call's `CallOutcome` is told."""
        self._outcome.connected()
        self._connected = True
        self._start_timer()

    def _start_timer(self) -> None:
        duration = self._limits.duration
        if duration is None or not (self._started and self._connected) or self._timer is not None:
            return
        self._timer = self.create_task(self._time(duration))

    async def _handle_client_message(self, frame: RTVIClientMessageFrame) -> None:
        data = frame.data if isinstance(frame.data, dict) else {}
        if frame.type == "user-text" and isinstance(data.get("text"), str):
            await self._carry_out(self._turns.user_typed(data["text"]))
        elif frame.type == "mute" and isinstance(data.get("muted"), bool):
            await self._carry_out(self._turns.text_only_switched(data["muted"]))

    async def _carry_out(
        self,
        commands: Sequence[Command],
        passing_on: tuple[Frame, FrameDirection] | None = None,
        after: asyncio.Event | None = None,
    ) -> None:
        """Do what `TurnTaking` says to, in order, then pass on the frame `passing_on`, if
        any; a reply started here holds back until `after` is set, if given. `TurnTaking`
        has moved on by now, so what is reported to it while this waits finds it as it now
        is. A turn replied to afresh once the reply dropped here is gone holds back until
        all that is done: nothing of the new reply goes out before what cuts off the old
        one."""
        cut_off: asyncio.Event | None = None  # set once all that is done
        try:
            for command in commands:
                match command:
                    case DropReply():
                        cut_off = cut_off or asyncio.Event()
                        await self._carry_out(await self._drop_reply(), after=cut_off)
                    case StopReply():
                        self._stop.set()
                    case ClearVoice():
                        await self.push_frame(InterruptionFrame())
                    case Reply(text=text):
                        self._start_reply(text, after)
                    case Voice(text=text):
                        await self.push_frame(TextFrame(text))
                    case WaitForFollowOn():
                        self._wait_for_follow_on()
                    case QueueTurn(text=text):
                        self._inputs.put_nowait(text)
            if passing_on is not None:
                await self.push_frame(*passing_on)
        finally:
            if cut_off is not None:
                cut_off.set()

    async def _take_turns(self) -> None:
        while True:
            text = await self._inputs.get()
            try:
                if self._turns.ending:
                    continue
                if self._time_up is not None:
                    await self._end("duration_limit", self._time_up)
                    continue
                assert text is not None
                await self._turn(text)
                if self._limits.turns is not None and self._recorded >= self._limits.turns:
                    await self._end("turn_limit", f"这次通话已经说了 {self._recorded} 轮了")
            finally:
                self._inputs.task_done()

    async def _time(self, duration: timedelta) -> None:
        await asyncio.sleep(duration.total_seconds())
        self._time_up = f"这次通话已经满 {duration / timedelta(minutes=1):g} 分钟了"
        self._inputs.put_nowait(None)  # wakes the worker, after the turn in progress

    async def _end(self, reason: EndReason, why: str) -> None:
        """Hang up, once what is already on its way to TTS has been voiced, telling the
        browser why as `CallOutcome` says, unless it has been told already."""
        await self._carry_out(self._turns.call_ending())
        message = self._outcome.limit_reached(reason, why)
        if message is not None:
            await self._send(message)
        await self.push_frame(EndWorkerFrame(reason=why))

    async def _turn(self, text: str) -> None:
        """Take one turn, replied to afresh after each follow-on, until its reply is over."""
        self._turn_over = asyncio.Event()
        try:
            await self._carry_out(self._turns.turn_started(text))
            await self._turn_over.wait()
        finally:  # the call may be hanging up
            self._stop_waiting()
            reply, self._reply = self._reply, None
            if reply is not None and not reply.done():
                await self.cancel_task(reply)

    def _start_reply(self, text: str, after: asyncio.Event | None = None) -> None:
        """Reply to `text`, once `after` is set, if given."""
        self._stop_waiting()
        self._stop = asyncio.Event()
        self._reply = self.create_task(self._reply_to(text, self._stop, after))

    async def _drop_reply(self) -> list[Reply | WaitForFollowOn]:
        """Drop the reply in progress and, once it is gone, tell `TurnTaking` so, handing
        back what it says to do then, to be done straight away. Whoever gets here first
        tells it: the reply dropped is gone for the others, who have nothing to do."""
        reply = self._reply
        if reply is None:
            return []
        if not reply.done():
            await self.cancel_task(reply)
        if reply is not self._reply:  # replied to afresh already, or hung up
            return []
        return self._turns.reply_dropped()

    def _wait_for_follow_on(self) -> None:
        """Wait, afresh, for the follow-on the user started to be transcribed."""
        self._stop_waiting()
        self._waiting = self.create_task(self._follow_on_timeout())

    async def _follow_on_timeout(self) -> None:
        """Tell `TurnTaking` the follow-on came to nothing, once `FOLLOW_ON_TIMEOUT` has
        passed without it."""
        await asyncio.sleep(FOLLOW_ON_TIMEOUT)
        self._waiting = None
        await self._carry_out(self._turns.follow_on_missed())

    def _stop_waiting(self) -> None:
        """Stop waiting for a follow-on, if waiting: it is no longer awaited."""
        if self._waiting is not None:
            self._waiting.cancel()
            self._waiting = None

    async def _reply_to(self, text: str, stop: asyncio.Event, after: asyncio.Event | None) -> None:
        """Reply to what the user said, once `after` is set, if given, going no further
        once `stop` is set. Only a reply that is recorded counts as a turn: a rejected,
        failed or dropped one does not count towards the call's limit, an interrupted one
        does. Once it is over, recorded or not, so is the turn; a dropped one is not over,
        but gone, which whoever dropped it reports."""
        if after is not None:
            await after.wait()
        await self.push_frame(LLMFullResponseStartFrame())
        try:
            async for event in self._engine.turn(
                self._call.conversation, text, self._call.llms, self._call.device_timezone,
                stop,
            ):
                if isinstance(event, SegmentComplete):
                    await self._carry_out(self._turns.segment_complete())
                    continue
                if isinstance(event, SpeechDelta):  # the Japanese just shown, cues and all
                    await self._carry_out(self._turns.reply_delta("ja", event.text))
                    continue
                if isinstance(event, TurnDone):  # told before any await: no longer to be dropped
                    await self._carry_out(self._turns.reply_recorded())
                    self._recorded += 1
                    self._outcome.turn_recorded()
                await self._send(asdict(event))
                if isinstance(event, SegmentDelta) and event.lang == "zh":
                    await self._carry_out(self._turns.reply_delta("zh", event.text))
        except Exception:  # the turn is over all the same, rather than the call stuck in it
            log.exception("reply in conversation %s failed", self._call.conversation.id)
        finally:
            await self.push_frame(LLMFullResponseEndFrame())
        await self._carry_out(self._turns.reply_ended())
        self._turn_over.set()

    async def _send(self, message: dict) -> None:
        await self.push_frame(RTVIServerMessageFrame(data=message))

    async def _stop_worker(self) -> None:
        if self._timer is not None:
            await self.cancel_task(self._timer)
            self._timer = None
        if self._worker is not None:
            await self.cancel_task(self._worker)
            self._worker = None
