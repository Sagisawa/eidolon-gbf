"""Voice calls: signalling, and a thin Pipecat pipeline around the conversation engine.

    browser mic → speech to text (zh/ja) → CallTurns → speech synthesis → browser speaker
                                               ↓
                              subtitles and the transcript, over the data channel

`Calls` is all the API sees: it answers the browser's offers, keeps each call to the
user who placed it, counts calls towards the user's limit, and serves each call until it
hangs up. Speech recognition and synthesis are the `Speech` port, Soniox and Fish Audio
in production, on whoever's keys `OwnKeys.for_call` says; a failing own key ends the
call saying which.

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
from eidolon.llm import TurnLLMs
from eidolon.own_keys import (
    SERVICE_LABELS,
    CallKeys,
    CallsUnavailable,
    OwnKeyFailed,
    OwnKeyRejected,
    OwnKeys,
    Service,
)
from eidolon.reply_format import SegmentComplete, SegmentDelta
from eidolon.store import Conversation, Store
from eidolon.usage import UsageLimiter, Use

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
        return FishAudioTTSService(
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

    def ice_servers(self, user_id: str) -> list[IceServer]:
        """What the browser needs before calling, with TURN credentials of its own. Raises
        CallsUnavailable or OwnKeyFailed, as `OwnKeys.for_call` does, before anything is
        spent on a call that could not start."""
        self._own_keys.for_call(user_id)
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
        """Answer a new call into the user's `conversation` with `character`, on the keys
        `OwnKeys.for_call` says. Raises OverLimit when the user has no calls left this
        hour, unless the call is exempt."""
        keys = self._own_keys.for_call(user_id)
        use = self._usage.take(user_id, "call", exempt=keys.exempt)
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
                connection, call, self._engine, self._speech, keys, self._limits, use
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
            use.give_back()
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
    through the conversation engine to the character's voice."""

    def __init__(
        self,
        connection: SmallWebRTCConnection,
        call: Call,
        engine: ConversationEngine,
        speech: Speech,
        keys: CallKeys,
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
        stt = speech.stt(keys.stt)
        tts = speech.tts(keys.tts, call.character.voice_id, sample_rate)
        own_services: dict[FrameProcessor, Service] = {
            processor: service
            for processor, service in ((stt, "stt"), (tts, "tts"))
            if service in keys.own
        }
        self._told_own_failure = False
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
                if error.processor in own_services and not self._told_own_failure:
                    # Theirs to fix, so they are told, while the call can still say so.
                    self._told_own_failure = True
                    failure = OwnKeyFailed(own_services[error.processor], "通话已结束")
                    connection.send_app_message(
                        ServerMessage(data={"type": "ended", "message": failure.message}).model_dump()
                    )

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


FOLLOW_ON_TIMEOUT = 4.0
"""How long, in seconds since the user was last heard, a follow-on may take to be
transcribed; after that it came to nothing (a cough, say) and the turn is replied to
again as it was. Soniox finalizes what it heard at most 3 s (its longest endpoint delay)
after the last word, and sends no transcription at all when it heard no words."""


class CallTurns(FrameProcessor):
    """Takes turns in the conversation for the call, one at a time.

    What the user says comes from speech recognition (a final transcription) or from
    text typed during the call (a `user-text` client message). Each turn goes through
    the conversation engine; the reply's Japanese is sent on as text for TTS, and the
    browser gets the same events as a text turn (`user`, `delta`, `done` or `error`) as
    server messages, which carry the subtitles.

    Until the reply can be interrupted, what the user says or types is a follow-on: the
    reply is dropped without a trace, what was voiced of it is cut off, and the turn is
    replied to afresh with the follow-on joined on a new line, opening again with
    `user`. The user starting to talk is enough to drop the reply; should what they said
    come to nothing, the turn is replied to again as it was. A reply can be interrupted
    once the character has started speaking it (when not voiced, once its first line is
    shown) and it has a complete segment, or once it is recorded. A reply voiced while
    the last one's voice is still playing has started once its first words are sent.

    After that, the user starting to talk interrupts the character: the reply stops
    being voiced and goes no further, and is recorded with only the segments complete
    by then, which `done` carries; what the user says is the next turn, taken up at
    once. What the user types does not interrupt her and waits for the reply to finish.
    A `mute` client message decides whether replies from then on are voiced at all.

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
        self._bot_speaking = False  # the character's voice is playing
        self._time_up: str | None = None  # why the call is over, once time is up
        self._ended = False
        self.recorded = 0
        """How many turns the call has recorded so far."""
        # The turn in progress:
        self._said: list[str] = []  # what the user said in it, follow-ons included
        self._reply: asyncio.Task | None = None  # the reply being given to it
        self._stop = asyncio.Event()  # set when the user interrupts the reply
        self._spoken = False  # the character has started speaking the reply
        self._sent_to_tts = False  # some of the reply is on its way to TTS
        self._complete = False  # the reply has a complete segment
        self._following_on = False  # a follow-on the user started is not yet transcribed
        self._heard = asyncio.Event()  # the user was heard, while following on

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, StartFrame):
            await self.push_frame(frame, direction)
            self._worker = self.create_task(self._take_turns())
            if self._limits.duration is not None:
                self._timer = self.create_task(self._time(self._limits.duration))
        elif isinstance(frame, TranscriptionFrame):
            await self._take_up(frame.text, spoken=True)
        elif isinstance(frame, InterimTranscriptionFrame):
            self._heard.set()
            await self.push_frame(frame, direction)
        elif isinstance(frame, RTVIClientMessageFrame):
            await self._handle_client_message(frame)
        elif isinstance(frame, InterruptionFrame):
            if self._open_to_follow_ons():
                self._following_on = True
                self._heard.set()
                await self._drop_reply()
            else:  # interrupts the reply in progress, if there is one
                self._voicing = False
                self._stop.set()
            await self.push_frame(frame, direction)
        elif isinstance(frame, BotStartedSpeakingFrame):
            # The voice of a reply dropped just now may start late, but never after the
            # next reply's first words are sent: those take the chat model a while.
            self._bot_speaking = True
            if self._voicing and self._sent_to_tts:
                self._spoken = True
            await self.push_frame(frame, direction)
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_speaking = False
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

    async def _take_up(self, text: str, spoken: bool) -> None:
        text = text.strip()
        if self._ended or not (text or (spoken and self._following_on)):
            return
        if not self._open_to_follow_ons():
            if text:
                self._inputs.put_nowait(text)
            return
        # A follow-on: what the turn is to be replied to changes before the reply is dropped.
        if text:
            self._said.append(text)
        dropped = self._following_on  # when the user was heard starting to talk
        self._following_on = False
        self._heard.set()
        if not dropped:  # typed: nothing has cut off what TTS still holds either
            await self._drop_reply()
            await self.push_frame(InterruptionFrame())

    async def _handle_client_message(self, frame: RTVIClientMessageFrame) -> None:
        data = frame.data if isinstance(frame.data, dict) else {}
        if frame.type == "user-text" and isinstance(data.get("text"), str):
            await self._take_up(data["text"], spoken=False)
        elif frame.type == "mute" and isinstance(data.get("muted"), bool):
            self._muted = data["muted"]

    def _open_to_follow_ons(self) -> bool:
        """Whether there is a turn in progress whose reply cannot be interrupted yet."""
        reply = self._reply
        if reply is None or reply.done() and not reply.cancelled():
            return False
        return not (self._spoken and self._complete)

    async def _drop_reply(self) -> None:
        if self._reply is not None and not self._reply.done():
            await self.cancel_task(self._reply)

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
                await self._turn(text)
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

    async def _turn(self, text: str) -> None:
        """Take one turn, replying afresh after each follow-on."""
        self._said = [text]
        try:
            while True:
                self._spoken = self._sent_to_tts = self._complete = False
                self._stop = asyncio.Event()
                self._reply = self.create_task(
                    self._reply_to("\n".join(self._said), not self._muted, self._stop)
                )
                await asyncio.wait({self._reply})
                if not self._reply.cancelled():
                    return
                await self._follow_on_heard()
        finally:
            await self._drop_reply()  # the call is hanging up
            self._reply = None

    async def _follow_on_heard(self) -> None:
        """Wait until the follow-on the user started is transcribed or comes to nothing."""
        while self._following_on:
            self._heard.clear()
            try:
                await asyncio.wait_for(self._heard.wait(), FOLLOW_ON_TIMEOUT)
            except TimeoutError:
                self._following_on = False

    async def _reply_to(self, text: str, voiced: bool, stop: asyncio.Event) -> None:
        """Reply to what the user said, going no further once `stop` is set. Only a reply
        that is recorded counts as a turn: a rejected, failed or dropped one does not
        count towards the call's limit, an interrupted one does."""
        self._voicing = voiced
        await self.push_frame(LLMFullResponseStartFrame())
        try:
            async for event in self._engine.turn(
                self._call.conversation, text, self._call.llms, self._call.device_timezone,
                stop,
            ):
                if isinstance(event, SegmentComplete):
                    self._complete = True
                    continue
                if isinstance(event, TurnDone):  # recorded by now, so no longer to be dropped
                    self._spoken = True
                    self.recorded += 1
                await self._send(asdict(event))
                if isinstance(event, SegmentDelta):
                    if not self._voicing:
                        self._spoken = True  # its first line is shown
                    elif event.lang == "ja":
                        self._on_its_way_to_tts()
                        await self.push_frame(TextFrame(event.text))
        finally:
            await self.push_frame(LLMFullResponseEndFrame())

    def _on_its_way_to_tts(self) -> None:
        """The reply's first words are sent to TTS: should the voice of the last reply
        still be playing, this one's follows on without starting again."""
        if not self._sent_to_tts:
            self._sent_to_tts = True
            self._spoken = self._bot_speaking

    async def _send(self, message: dict) -> None:
        await self.push_frame(RTVIServerMessageFrame(data=message))

    async def _stop_worker(self) -> None:
        if self._timer is not None:
            await self.cancel_task(self._timer)
            self._timer = None
        if self._worker is not None:
            await self.cancel_task(self._worker)
            self._worker = None
