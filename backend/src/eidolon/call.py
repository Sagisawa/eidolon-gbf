"""Voice calls: signalling, and a thin Pipecat pipeline around the conversation engine.

    browser mic → speech to text (zh/ja) → CallTurns → speech synthesis → browser speaker
                                               ↓
                              subtitles and the transcript, over the data channel

`Calls` is all the API sees: it answers the browser's offers, keeps each call to the
user who placed it, lets each call through `Admissions` and serves it until it hangs up.
Speech recognition and synthesis are the `Speech` port, on whoever's keys
`OwnKeys.for_call` says; a failing own key ends the call saying which. Speech recognition
is whichever service the key is for, Soniox or Alibaba Cloud Model Studio (阿里云百炼),
and how long a follow-on may take to be transcribed is that service's. Whether a call
counts towards the user's limit, and what the browser is told when the backend ends it,
is `CallOutcome`'s to decide; the call only reports to it. So is the call's activity
record: each turn of the call has one under it, and its speech recognition and synthesis
are recorded under it by `CallMeter`, which also lays each error in the pipeline at the
door of the service it came from.
Whose turn it is during the call, what is a follow-on and what interrupts the character, is
likewise `TurnTaking`'s.

Pipecat's own LLM services and context aggregators are not used: every utterance,
spoken or typed during the call, goes through the same conversation engine as a
text turn and lands in the same conversation record.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Any, Literal, Protocol

import httpx
import ormsgpack
from aiortc import RTCIceServer
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import ConnectionClosed
from websockets.protocol import State

from pipecat.frames.frames import (
    AggregatedTextFrame,
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    CancelFrame,
    ControlFrame,
    EndFrame,
    EndWorkerFrame,
    ErrorFrame,
    Frame,
    InputAudioRawFrame,
    InterimTranscriptionFrame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    OutputTransportMessageFrame,
    StartFrame,
    TextFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineWorker, ProcessorUnusablePolicy
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.frameworks.rtvi.frames import (
    RTVIClientMessageFrame,
    RTVIServerMessageFrame,
)
from pipecat.processors.frameworks.rtvi.models import ServerMessage
from pipecat.services.ai_service import AIService
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
from pipecat.utils.errors import ErrorCategory
from pipecat.utils.types import assert_given
from pipecat.workers.runner import WorkerRunner

from eidolon.activity import (
    CallEndReason,
    ErrorKind,
    Origin,
    Recording,
    Result,
    error_kind,
    host,
)
from eidolon.admission import Admission, Admissions
from eidolon.bailian import FOLLOW_ON_TIMEOUT as BAILIAN_FOLLOW_ON_TIMEOUT
from eidolon.bailian import REGION_URLS, BailianCheckFailed, BailianSTTService, find_region
from eidolon.billing import Billing
from eidolon.call_outcome import CallLimits, CallOutcome, LimitReached
from eidolon.characters import Character
from eidolon.clock import Clock
from eidolon.config import (
    DEFAULT_BAILIAN_STT_MODEL,
    IceServer,
    Settings,
    SttKey,
    SttProvider,
    UsageLimits,
)
from eidolon.emotion import EmotionJudging, SaidSegment, SegmentToJudge
from eidolon.engine import ConversationEngine, TurnDone, UserSaid
from eidolon.llm import TurnLLMs
from eidolon.own_keys import (
    CallKeys,
    OwnKeyRejected,
    Service,
)
from eidolon.reply_format import SegmentComplete, SegmentDelta, SpeechDelta
from eidolon.store import Conversation, NotFound, Store
from eidolon.turn_outcome import turn_result
from eidolon.turn_taking import (
    ClearVoice,
    Command,
    DropReply,
    FlushVoice,
    QueueTurn,
    Reply,
    StopReply,
    TurnTaking,
    Voice,
    WaitForFollowOn,
)

log = logging.getLogger(__name__)

Quality = Literal["low", "standard", "high"]

_SAMPLE_RATES: dict[Quality, int] = {"low": 16000, "standard": 24000, "high": 44100}
"""Call quality is the sample rate the character's speech is synthesised at. It does not
change the network traffic: WebRTC always sends Opus at 48 kHz."""


@dataclass(frozen=True)
class Call:
    """A call the browser asked for: which conversation, the models its turns run on (the
    user's own, if `own_llm`), how it wants the audio, and the time zone its device
    reports."""

    conversation: Conversation
    character: Character
    llms: TurnLLMs
    muted: bool
    quality: Quality
    device_timezone: str | None = None
    own_llm: bool = False


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


@dataclass(frozen=True)
class Hearing:
    """Speech recognition for one call, and how long, in seconds since the user was last
    heard, a follow-on may take to be transcribed by it; after that it came to nothing (a
    cough, say) and the turn is replied to again as it was."""

    stt: STTService
    follow_on_timeout: float


class Speech(Protocol):
    """The outside services a call hears and speaks with, on whoever's key is given."""

    def stt(self, key: SttKey) -> Hearing:
        """Speech recognition for one call, in Chinese and Japanese, by the service `key`
        is for."""
        ...

    def tts(self, api_key: str, model: str, voice_id: str, sample_rate: int) -> TTSService:
        """Speech synthesis for one call, with `model`, in the character's voice."""
        ...

    async def check_stt(self, provider: SttProvider, api_key: str) -> SttKey:
        """The key as calls are to use it, with the region a DashScope key works in. Raises
        OwnKeyRejected saying why, unless `api_key` works for `provider`."""
        ...

    async def check_tts(self, api_key: str) -> None:
        """Raise OwnKeyRejected saying why, unless `api_key` works for Fish Audio."""
        ...


@dataclass
class SegmentTextFrame(TextFrame):
    """Some of the Japanese of segment `segment` of reply `reply`, delivery cues and all,
    for TTS to voice. Replies are numbered from 1 within the call, segments from 0 within
    the reply."""

    reply: int
    segment: int


@dataclass
class SegmentCompleteFrame(ControlFrame):
    """Segment `segment` of reply `reply` has all its Japanese: TTS is to voice all it
    holds of it now, rather than wait for more."""

    reply: int
    segment: int


def segment_playing(reply: int, segment: int) -> OutputTransportMessageFrame:
    """The `segment-playing` server message, telling the browser her voice has started
    playing segment `segment` of reply `reply`. Queued with the audio, just ahead of the
    segment's first, the transport sends it as that audio starts playing."""
    message = {"type": "segment-playing", "reply": reply, "segment": segment}
    return OutputTransportMessageFrame(message=ServerMessage(data=message).model_dump())


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
        reconnect = self._holds_speech()
        self._tts_started = False
        # What InterruptibleTTSService does but for reconnecting, which follows.
        await super(InterruptibleTTSService, self)._handle_interruption(frame, direction)
        if reconnect:
            self._reconnecting = self.create_task(self._reconnect(self._reconnecting))

    def _holds_speech(self) -> bool:
        """Whether the connection may still hold speech of what is interrupted: the
        character is speaking, or has been given something to say."""
        return self._bot_speaking or self._tts_started

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


FINISH_TIMEOUT = 10.0
"""How long, in seconds, Fish Audio may take to finish a segment once told it has all its
Japanese: to send the rest of its audio, some seconds of it at most. A session that takes
longer is given up, and the rest of the segment with it."""


class FishTTS(InterruptsFirst, FishAudioTTSService):
    """Fish Audio, speaking as the character a segment at a time.

    Fish Audio's audio does not say where one segment ends and the next begins, so each
    segment is voiced in a Fish Audio session of its own (a session of its websocket
    protocol, not the call). Once the segment has all its Japanese, what
    is held of it is sent and the session told to stop; it finishes once Fish Audio has sent
    the last of its audio, and only then does the next segment start, so that ahead of its
    first audio can go its `segment-playing` message (`SegmentTextFrame` says which segment
    the Japanese is of). Starting a session takes a connection a second or more to open, so
    the connection for the next segment is opened while the current one is voiced, and the
    next segment starts on it at once: no pause is heard between them.

    After a reply's last segment, that connection is left open for the next reply: Fish
    Audio keeps an idle one open, and so did the single connection a call had before. It
    is not closed for being idle; the websocket's keepalive pings find it if it drops, and a
    connection found closed as a reply starts is replaced then.

    Interrupted, the service drops its connections, the spare one too, and opens another
    (`InterruptsFirst`); `segment-playing` messages still queued go with the audio they
    were queued with."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._arriving: tuple[int, int] | None = None  # (reply, segment) of the Japanese coming in
        self._voiced: tuple[int, int] | None = None  # (reply, segment) being voiced
        self._announced = False  # its `segment-playing` message is queued
        # The Fish Audio session voicing it, and what receives the session's audio until it
        # has finished:
        self._session: ClientConnection | None = None
        self._receiving: asyncio.Task | None = None
        self._finished = asyncio.Event()
        # The connection the next segment is to start on, open or opening:
        self._spare: asyncio.Task[ClientConnection | None] | None = None

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        if isinstance(frame, SegmentTextFrame):
            self._arriving = (frame.reply, frame.segment)
        elif isinstance(frame, LLMFullResponseStartFrame):
            if self._reconnecting is None or self._reconnecting.done():
                self._keep_spare()  # a reconnection under way opens one of its own
        await super().process_frame(frame, direction)
        if isinstance(frame, SegmentCompleteFrame):
            if self._arriving == (frame.reply, frame.segment):
                await self._send_held_text()
                await self._end_segment()
        elif isinstance(frame, LLMFullResponseEndFrame):
            await self._end_segment()  # should its last segment never have completed

    async def _handle_interruption(self, frame: InterruptionFrame, direction: FrameDirection):
        await super()._handle_interruption(frame, direction)
        self._arriving = self._voiced = None

    def _holds_speech(self) -> bool:
        return super()._holds_speech() or self._session is not None

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        await self._reconnected()
        if self._voiced != self._arriving:  # the first of the next segment's Japanese
            await self._end_segment()
            self._voiced = self._arriving
            self._announced = self._arriving is None  # Japanese under no segment: nothing to say
        if self._session is None or self._finished.is_set():  # or it ended early
            await self._start_session(context_id)
        if self._session is None:  # it could not be opened, and the error is reported
            yield None
            return
        if not self._announced and self._voiced is not None:  # ahead of its first audio
            await self.append_to_audio_context(context_id, segment_playing(*self._voiced))
            self._announced = True
        try:
            await self._session.send(ormsgpack.packb({"event": "text", "text": text}))
            await self.start_tts_usage_metrics(text)
            await self._session.send(ormsgpack.packb({"event": "flush"}))
        except Exception as e:
            yield ErrorFrame(error=f"Unknown error occurred: {e}")
            await self._close_session()  # this sentence is lost; the next opens another
        yield None

    async def flush_audio(self, context_id: str | None = None) -> None:
        """Nothing to do: each sentence is flushed as it is sent, and each segment's
        session told to stop once it has all its Japanese."""

    async def _send_held_text(self) -> None:
        """Send what the sentence aggregator holds back, waiting for what follows."""
        held = await self._text_aggregator.flush()
        if held:
            await self._push_tts_frames(AggregatedTextFrame(held.text, held.type, raw_text=held.text))

    async def _end_segment(self) -> None:
        """Have the segment being voiced finish, once all its audio is in; if it takes
        too long, give up the rest."""
        await self._reconnected()
        if self._session is not None:
            try:
                await self._session.send(ormsgpack.packb({"event": "stop"}))
                await asyncio.wait_for(self._finished.wait(), FINISH_TIMEOUT)
            except ConnectionClosed:
                pass  # it is over already
            except TimeoutError:
                log.warning("Fish Audio did not finish a segment in time; the rest is dropped")
            if self._finished.is_set():  # what received its audio closes it
                self._session = self._receiving = None
            else:
                await self._close_session()
        self._voiced = None

    async def _start_session(self, context_id: str) -> None:
        """Voice the segment in a new session, on the spare connection, whose audio goes to
        the audio context `context_id`; and open the next spare one meanwhile."""
        await self._close_session()
        self._keep_spare()
        spare = self._spare
        assert spare is not None
        await asyncio.wait([spare])
        if self._spare is not spare or spare.cancelled():  # dropped meanwhile
            return
        self._spare = None
        self._keep_spare()
        session = spare.result()
        if session is None:
            return
        self._session = session
        self._finished = asyncio.Event()
        self._receiving = self.create_task(self._receive(session, context_id, self._finished))

    async def _receive(
        self, session: ClientConnection, context_id: str, finished: asyncio.Event
    ) -> None:
        """Take the session's audio into the audio context `context_id` until the session
        finishes, then set `finished` and close it."""
        try:
            async for message in session:
                if not isinstance(message, bytes):
                    continue
                event = ormsgpack.unpackb(message)
                if not isinstance(event, dict):
                    continue
                if event.get("event") == "audio":
                    audio = event.get("audio")
                    if audio and len(audio) > 1024:  # as Pipecat's own receiver has it
                        frame = TTSAudioRawFrame(audio, self.sample_rate, 1, context_id=context_id)
                        await self.append_to_audio_context(context_id, frame)
                        await self.stop_ttfb_metrics()
                elif event.get("event") == "finish":
                    if event.get("reason") == "error":
                        await self.push_error(error_msg="Fish Audio server error during synthesis")
                    break
        except ConnectionClosed as e:
            log.warning("Fish Audio closed a session before it finished: %s", e)
        except Exception as e:
            await self.push_error(error_msg=f"Unknown error occurred: {e}", exception=e)
        finally:
            finished.set()
        await session.close()

    async def _close_session(self) -> None:
        """Close the session, if any, at once, dropping what it has yet to send."""
        receiving, self._receiving = self._receiving, None
        session, self._session = self._session, None
        if receiving is not None:
            await self.cancel_task(receiving)
        if session is not None:
            await session.close()

    def _keep_spare(self) -> None:
        """Have a connection open, or opening, for the next segment to start on, in place
        of one that could not be opened or has closed since."""
        spare = self._spare
        if spare is not None and not spare.done():
            return
        if spare is not None and not spare.cancelled():
            websocket = spare.result()
            if websocket is not None and websocket.state is State.OPEN:
                return
        self._spare = self.create_task(self._open())

    async def _open(self) -> ClientConnection | None:
        """A new connection to Fish Audio, its session started, ready for the text to
        voice; None if it could not be opened, the error having been reported."""
        headers = {"Authorization": f"Bearer {self._api_key}"}
        model = assert_given(self._settings.model)
        if model is not None:
            headers["model"] = model
        request: dict[str, Any] = {
            "text": "",
            "sample_rate": self._fish_sample_rate,
            "latency": self._settings.latency,
            "format": self._output_format,
            "normalize": self._settings.normalize,
            "prosody": {
                "speed": self._settings.prosody_speed,
                "volume": self._settings.prosody_volume,
            },
            "reference_id": self._settings.voice,
        }
        if self._settings.temperature is not None:
            request["temperature"] = self._settings.temperature
        if self._settings.top_p is not None:
            request["top_p"] = self._settings.top_p
        websocket: ClientConnection | None = None
        try:
            websocket = await self._websocket_connect(self._base_url, additional_headers=headers)
            await websocket.send(ormsgpack.packb({"event": "start", "request": request}))
        except asyncio.CancelledError:
            if websocket is not None:
                websocket.transport.abort()
            raise
        except Exception as e:
            await self.push_error(error_msg=f"Unknown error occurred: {e}", exception=e)
            if websocket is not None:
                websocket.transport.abort()
            return None
        return websocket

    async def _connect(self) -> None:
        """Open the connection the next segment is to start on."""
        self._keep_spare()
        assert self._spare is not None
        await asyncio.wait([self._spare])

    async def _disconnect(self) -> None:
        """Drop the connections: the segment being voiced, and the next one's."""
        await self.stop_all_metrics()
        self._voiced = None
        spare, self._spare = self._spare, None
        await self._close_session()
        if spare is None:
            return
        if not spare.done():
            await self.cancel_task(spare)
        elif not spare.cancelled() and (websocket := spare.result()) is not None:
            await websocket.close()


SONIOX_FOLLOW_ON_TIMEOUT = 4.0
"""How long, in seconds, a follow-on may take Soniox to transcribe (see `Hearing`): it
finalizes what it heard at most 3 s (its longest endpoint delay) after the last word, and
sends no transcription at all when it heard no words."""


@dataclass(frozen=True)
class SpeechServices:
    """Soniox or Alibaba Cloud Model Studio, whichever the key is for, hears the user, the
    latter with `bailian_model`, users' own keys too; Fish Audio speaks as the character,
    with the model the call is given (the deployer's, as it connected)."""

    bailian_model: str = DEFAULT_BAILIAN_STT_MODEL

    SONIOX_MODELS_URL = "https://api.soniox.com/v1/models"
    FISH_CREDIT_URL = "https://api.fish.audio/wallet/self/api-credit"

    def stt(self, key: SttKey) -> Hearing:
        # Either decides where an utterance starts and ends; the turn processor turns its
        # proposals into interruptions of the character's voice.
        if key.provider == "bailian":
            bailian = BailianSTTService(
                api_key=key.api_key, model=self.bailian_model, region=key.region
            )
            return Hearing(bailian, BAILIAN_FOLLOW_ON_TIMEOUT)
        soniox = SonioxSTTService(
            api_key=key.api_key,
            vad_force_turn_endpoint=False,
            settings=SonioxSTTService.Settings(language_hints=[Language.ZH, Language.JA]),
        )
        return Hearing(soniox, SONIOX_FOLLOW_ON_TIMEOUT)

    def tts(self, api_key: str, model: str, voice_id: str, sample_rate: int) -> TTSService:
        return FishTTS(
            api_key=api_key,
            sample_rate=sample_rate,
            settings=FishAudioTTSService.Settings(voice=voice_id, model=model),
        )

    async def check_stt(self, provider: SttProvider, api_key: str) -> SttKey:
        """Asks Soniox for something that costs nothing, its models; starts a task on
        DashScope and finishes it at once, sending no audio, in the region the key works
        in (see `bailian.find_region`)."""
        if provider == "bailian":
            try:
                region = await find_region(api_key, self.bailian_model)
            except BailianCheckFailed as e:
                raise OwnKeyRejected(str(e)) from None
            return SttKey("bailian", api_key, region)
        await self._get(self.SONIOX_MODELS_URL, api_key)
        return SttKey("soniox", api_key)

    async def check_tts(self, api_key: str) -> None:
        """Asks for something that costs nothing: Fish Audio's balance."""
        await self._get(self.FISH_CREDIT_URL, api_key)

    @staticmethod
    async def _get(url: str, api_key: str) -> None:
        """Raise OwnKeyRejected saying why, unless `url` answers on `api_key`."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=10)) as client:
                res = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
        except httpx.HTTPError as e:
            raise OwnKeyRejected(f"连不上 {httpx.URL(url).host}：{e!r}") from None
        if res.is_error:
            raise OwnKeyRejected(f"{res.status_code} {res.text[:200]}")


SONIOX_URL = "wss://stt-rt.soniox.com/transcribe-websocket"
FISH_TTS_URL = "wss://api.fish.audio/v1/tts/live"
"""Where Soniox hears and Fish Audio speaks, as Pipecat connects to them."""


def _stt_host(key: SttKey) -> str:
    """The provider the call's speech recognition is, as its service calls are recorded."""
    if key.provider == "bailian":
        return host(REGION_URLS[key.region or "beijing"])
    return host(SONIOX_URL)


def _model(service: AIService) -> str:
    model = service._settings.model
    return model if isinstance(model, str) and model else "unknown"


_CATEGORY_KINDS: dict[ErrorCategory, ErrorKind] = {
    ErrorCategory.AUTHENTICATION: "unauthorized",
    ErrorCategory.AUTHORIZATION: "unauthorized",
    ErrorCategory.QUOTA: "unauthorized",
    ErrorCategory.RATE_LIMIT: "rate_limited",
    ErrorCategory.INVALID_REQUEST: "refused",
    ErrorCategory.CONNECTIVITY: "connection",
    ErrorCategory.SERVER: "server_error",
}


def frame_error_kind(frame: ErrorFrame) -> ErrorKind:
    """What kind of failure an error in the pipeline is: from its exception, or failing
    that, from the category the service gave it, or what it says."""
    if frame.exception is not None and (kind := error_kind(frame.exception)) != "other":
        return kind
    if frame.category in _CATEGORY_KINDS:
        return _CATEGORY_KINDS[frame.category]
    return error_kind(Exception(frame.error))


@dataclass
class _Voicing:
    """Speech synthesis of one reply: since when it was given the reply's first words
    (pipeline clock, ns), how many bytes of them, when its first audio came, and whether
    it failed."""

    started_ns: int
    bytes: int = 0
    first_audio_ns: int | None = None
    error: ErrorKind | None = None


class CallMeter(BaseObserver):
    """A call's speech recognition and synthesis, recorded as service calls under the
    call's activity record, and each error in the pipeline laid on the service it came
    from.

    Speech recognition is a stream as long as the call: one service call, billed for the
    seconds of audio sent to it, with no latency, failed if any of its errors came. Speech
    synthesis is a service call for each reply voiced, from its first words to the next
    reply or interruption: billed for the UTF-8 bytes of Japanese (cues and all) it was
    given, as Fish Audio charges, timed to its first audio, failed if any of its errors
    came meanwhile; one of its errors between replies is a failed service call of its own."""

    def __init__(
        self,
        recording: Recording,
        stt: FrameProcessor,
        stt_origin: Origin,
        tts: FrameProcessor,
        tts_origin: Origin,
    ) -> None:
        super().__init__()
        self._recording = recording
        self._stt, self._stt_origin = stt, stt_origin
        self._tts, self._tts_origin = tts, tts_origin
        self._heard_s = 0.0
        self._stt_error: ErrorKind | None = None
        self._voicing: _Voicing | None = None
        self._closed = False

    async def on_push_frame(self, data: FramePushed) -> None:
        frame = data.frame
        if data.destination is self._stt and isinstance(frame, InputAudioRawFrame):
            self._heard_s += len(frame.audio) / (frame.sample_rate * frame.num_channels * 2)
        elif data.destination is self._tts:
            if isinstance(frame, SegmentTextFrame) and frame.text:
                if self._voicing is None:
                    self._voicing = _Voicing(data.timestamp)
                self._voicing.bytes += len(frame.text.encode())
            elif isinstance(frame, LLMFullResponseStartFrame | InterruptionFrame):
                self._voiced()
        elif data.source is self._tts and isinstance(frame, TTSAudioRawFrame):
            if self._voicing is not None and self._voicing.first_audio_ns is None:
                self._voicing.first_audio_ns = data.timestamp

    def failed(self, error: ErrorFrame) -> None:
        """An error came up the pipeline."""
        kind = frame_error_kind(error)
        if error.processor is self._stt:
            self._stt_error = self._stt_error or kind
        elif error.processor is self._tts:
            if self._voicing is None:
                self._recording.add(self._tts_origin, kind, None, Billing())
            else:
                self._voicing.error = self._voicing.error or kind
                self._voiced()

    def close(self) -> None:
        """The call is over: record what is still being metered."""
        if self._closed:
            return
        self._closed = True
        self._voiced()
        heard = Billing("seconds", round(self._heard_s, 3))
        self._recording.add(self._stt_origin, self._stt_error, None, heard)

    def _voiced(self) -> None:
        voicing, self._voicing = self._voicing, None
        if voicing is None:
            return
        latency = None
        if voicing.first_audio_ns is not None:
            latency = (voicing.first_audio_ns - voicing.started_ns) / 1e6
        billed = Billing("bytes", voicing.bytes)
        self._recording.add(self._tts_origin, voicing.error, latency, billed)


class Calls:
    """The user's voice calls, from signalling to hanging up.

    Each new call is let through by `admissions`, and has a `CallOutcome`, given the
    call's own limits on its time and turns, which, told what happens to the call, decides
    when it has reached its own limits, what the browser is told when the backend ends it,
    and how it turned out, settling the call once it is over. Only the user who placed a
    call can renegotiate it or add ICE candidates to it.
    """

    def __init__(
        self,
        settings: Settings,
        engine: ConversationEngine,
        admissions: Admissions,
        limits: Callable[[], UsageLimits],
        speech: Speech,
        clock: Clock,
        store: Store | None = None,
        emotions: EmotionJudging | None = None,
    ) -> None:
        """Calls last as long, and take as many turns, as `limits` says as each starts.
        With `store`, calls of users banned or deleted meanwhile are hung up; with
        `emotions`, her emotion in each segment is judged, on the deployer's judge model
        whoever's keys the call is on."""
        self._settings = settings
        self._emotions = emotions
        self._engine = engine
        self._admissions = admissions
        self._usage_limits = limits
        self._speech = speech
        self._clock = clock
        self._store = store
        self._webrtc = SmallWebRTCRequestHandler(
            ice_servers=[RTCIceServer(**server) for server in settings.ice_servers]
        )
        self._owners: dict[str, str] = {}  # peer connection id → the user it belongs to
        self._live: set[_LiveCall] = set()
        self._watch: asyncio.Task | None = None  # hangs up banned and deleted users' calls

    def _limits(self) -> CallLimits:
        """A call's own limits, as it connects now: those in effect then hold to its end."""
        limits = self._usage_limits()
        return CallLimits(
            timedelta(minutes=limits.call_minutes) if limits.call_minutes else None,
            limits.turns_per_call,
        )

    def ice_servers(self, user_id: str) -> dict:
        """What the browser needs before calling: ICE servers, with TURN credentials of its
        own; how long a call may last, in seconds (None for no limit); and whether calls on
        the keys the user has now are exempt from the limit. Raises CallsUnavailable or
        OwnKeyFailed, as `Admissions.call_setup` does, before anything is spent on a call
        that could not start."""
        exempt = self._admissions.call_setup(user_id)
        servers: list[IceServer] = list(self._settings.ice_servers)
        if self._settings.turn is not None:
            servers.append(self._settings.turn.credentials(user_id, self._clock()))
        duration = self._limits().duration
        return {
            "iceServers": servers,
            "maxCallSeconds": None if duration is None else int(duration.total_seconds()),
            "callExempt": exempt,
        }

    async def start(
        self,
        user_id: str,
        conversation: Conversation,
        character: Character,
        options: CallOptions,
        offer: SessionDescription,
    ) -> dict:
        """Answer a new call into the user's `conversation` with `character`, let through
        by `Admissions.call`, whose exceptions it raises. Whatever fails before the call is
        served, it never connected; once it is served, it is settled as it ends."""
        admission = self._admissions.call(user_id, character.id)
        outcome = CallOutcome(admission, self._limits())
        return await self._start(
            user_id, conversation, character, options, offer, admission, outcome
        )

    async def _start(
        self,
        user_id: str,
        conversation: Conversation,
        character: Character,
        options: CallOptions,
        offer: SessionDescription,
        admission: Admission[CallKeys],
        outcome: CallOutcome,
    ) -> dict:
        keys = admission.keys
        connections: list[SmallWebRTCConnection] = []
        started: list[_LiveCall] = []

        async def serve(connection: SmallWebRTCConnection) -> None:
            connections.append(connection)

            @connection.event_handler("closed")
            async def forget(connection: SmallWebRTCConnection) -> None:
                self._owners.pop(connection.pc_id, None)

            live = _LiveCall(
                connection, call, self._engine, self._speech, keys, outcome,
                keys.emotions or self._emotions,
            )
            self._live.add(live)
            live.start(on_done=self._live.discard)
            started.append(live)
            if self._store is not None and (self._watch is None or self._watch.done()):
                self._watch = asyncio.create_task(self._hang_up_users_gone())

        try:
            call = Call(
                conversation, character, admission.llms, options.muted, options.quality,
                options.device_timezone, admission.own_llm,
            )
            answer = await self._answer(SmallWebRTCRequest(offer.sdp, offer.type), serve)
        except BaseException:
            if not started:  # once served, the call is settled as it ends
                outcome.set_up_failed()
            raise
        if answer is None or not started:
            if started:
                await started[0].hang_up("failed")
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

    @property
    def in_progress(self) -> int:
        """How many calls there are now, connected or still connecting."""
        return len(self._live)

    async def hang_up(self, user_id: str, reason: CallEndReason = "deleted") -> None:
        """Hang up the user's calls, for `reason`, and wait for them to end; a reply in
        progress is dropped. Unless banned, a user's calls are hung up as they are deleted."""
        await asyncio.gather(
            *(live.hang_up(reason) for live in list(self._live) if live.user_id == user_id)
        )

    async def _hang_up_users_gone(self) -> None:
        """While there are calls, hang up those of users banned or deleted meanwhile (by
        then, their calls were hung up as they were deleted, unless on the command line)."""
        while self._live:
            await asyncio.sleep(USER_CHECK_INTERVAL)
            users = {live.user_id for live in self._live}
            assert self._store is not None
            for user_id in users - self._store.active_users(users):
                try:
                    self._store.get_user(user_id)
                    reason: CallEndReason = "banned"
                except NotFound:
                    reason = "deleted"
                log.info("hanging up the calls of user %s, %s", user_id, reason)
                await self.hang_up(user_id, reason)

    async def aclose(self) -> None:
        """Hang up every call and wait for them to end; a reply in progress is dropped."""
        if self._watch is not None:
            self._watch.cancel()
        await asyncio.gather(*(live.hang_up("shutdown") for live in list(self._live)))
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
        outcome: CallOutcome,
        emotions: EmotionJudging | None,
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
        hearing = speech.stt(keys.stt)
        stt = hearing.stt
        self._stt_provider: SttProvider = keys.stt.provider
        self._turns = CallTurns(engine, call, outcome, hearing.follow_on_timeout, emotions)
        tts = speech.tts(keys.tts, keys.tts_model, call.character.voice_id, sample_rate)
        own_services: dict[FrameProcessor, Service] = {
            processor: service
            for processor, service in ((stt, "stt"), (tts, "tts"))
            if service in keys.own
        }
        self._meter = CallMeter(
            outcome.recording,
            stt, Origin("stt", _stt_host(keys.stt), _model(stt), "stt" in keys.own),
            tts, Origin("tts", host(FISH_TTS_URL), _model(tts), "tts" in keys.own),
        )
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
            pipeline,
            processor_unusable_policy=ProcessorUnusablePolicy.CANCEL,
            observers=[self._meter],
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
            self._meter.failed(error)
            if error.fatal or (error.processor is not None and not error.processor.is_usable):
                processor = error.processor
                self._report_failure(own_services.get(processor) if processor else None)

    @property
    def user_id(self) -> str:
        return self._call.conversation.user_id

    def _report_failure(self, own_service: Service | None = None) -> None:
        """A failing service ends the call. Whatever `CallOutcome` says to tell the browser
        about it is told now, while the call can still say so."""
        message = self._outcome.service_failed(own_service, self._stt_provider)
        if message is not None:
            self._connection.send_app_message(ServerMessage(data=message).model_dump())

    def start(self, on_done: Callable[["_LiveCall"], None]) -> None:
        """Serve the call in the background; `on_done` is told once it has ended."""
        self._task = asyncio.create_task(self._serve())
        self._task.add_done_callback(lambda _: on_done(self))

    async def hang_up(self, reason: CallEndReason) -> None:
        """End the call now, for `reason`, dropping any reply in progress, and wait until
        it has ended."""
        self._hung_up = True
        self._outcome.ended_by(reason)
        await self._worker.cancel()
        if self._task is not None:
            await asyncio.wait({self._task})

    async def _serve(self) -> None:
        try:
            if not self._hung_up:  # hung up before it even started
                await self._run()
        except Exception:
            log.exception("call in conversation %s failed", self._call.conversation.id)
            self._outcome.ended_by("failed")
            self._report_failure()
        finally:
            self._meter.close()
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
            self._outcome.ended_by("failed")
            await self._worker.cancel()
        await running


class CallTurns(FrameProcessor):
    """Takes turns in the conversation for the call, one at a time, as its `TurnTaking`
    has them.

    What the user says comes from speech recognition (a final transcription) or from
    text typed during the call (a `user-text` client message). Each turn goes through
    the conversation engine; the reply's Japanese is sent on as text for TTS, delivery
    cues and all, segment by segment under the reply's number in the call
    (`SegmentTextFrame`, then `SegmentCompleteFrame` once the segment has all of it), and
    the browser gets the same events as a text turn (`user`, `delta`, `done` or `error`) as
    server messages, which carry the subtitles, `user` saying the number of the reply it
    opens. A turn replied to afresh after a follow-on opens again with `user`; an
    interrupted one's `done` carries only the segments complete by then.

    Given `emotions`, each segment of a reply is judged once it is complete, while it is
    voiced, and the browser gets an `emotion` message for it, for her stand; judging goes
    on apart from the reply, which neither waits for it nor, dropped or interrupted, takes
    what is being judged with it. What is left incomplete is not judged.

    Which of what the user says or types is a follow-on and which interrupts the
    character, when a reply is dropped, stopped or replied to afresh, and what of it is
    voiced, is `TurnTaking`'s to decide: the frames coming through, `mute` client
    messages and how each reply is getting on are reported to it as they happen, and what
    it says to do is done straight away. How long a follow-on may take to be transcribed,
    `follow_on_timeout` seconds since the user was last heard, as long as the call's speech
    recognition needs (`Hearing`), is timed here.

    The call's limits, and what the browser is told when it reaches them, are its
    `CallOutcome`'s; here they are only reported and asked about. Its time limit
    (`CallOutcome.time_limit`) is timed from when the call connects (`connected`), as the
    call screen's clock does, and reported once it is up; each recorded turn is reported
    too. Once a turn is over, and when its time is up, the outcome is asked whether the call
    has reached its limits; if it has, the browser gets the `ended` message it hands back,
    if any, and the call ends once the last reply has been voiced; what is said after that
    is not taken up.
    """

    def __init__(
        self,
        engine: ConversationEngine,
        call: Call,
        outcome: CallOutcome,
        follow_on_timeout: float,
        emotions: EmotionJudging | None = None,
    ) -> None:
        super().__init__()
        self._engine = engine
        self._call = call
        self._outcome = outcome
        self._follow_on_timeout = follow_on_timeout
        self._emotions = emotions
        self._judging: set[asyncio.Task] = set()  # segments' emotions being judged
        self._turns = TurnTaking(text_only=call.muted)
        self._inputs: asyncio.Queue[str | None] = asyncio.Queue()  # None: wakes it, once time is up
        self._worker: asyncio.Task | None = None
        self._timer: asyncio.Task | None = None
        self._started = False  # the pipeline has started, so tasks can be created
        self._connected = False  # the browser has connected: the time limit runs
        # The turn in progress:
        self._turn_over = asyncio.Event()  # set once its reply is over
        self._reply: asyncio.Task | None = None  # the reply being given to it
        self._stop = asyncio.Event()  # set to have the reply go no further
        self._waiting: asyncio.Task | None = None  # times the follow-on waited for
        self._recording: Recording | None = None  # its activity record
        self._result: Result | None = None  # how it turned out, once it has

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
            if self._recording is not None:
                self._recording.spoke()  # her voice began to play
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
        """The browser has connected (GLOSSARY.md「接通」): the call's time starts running,
        and the call's `CallOutcome` is told."""
        self._outcome.connected()
        self._connected = True
        self._start_timer()

    def _start_timer(self) -> None:
        duration = self._outcome.time_limit
        if duration is None or not (self._started and self._connected) or self._timer is not None:
            return
        self._timer = self.create_task(self._time(duration))

    async def _handle_client_message(self, frame: RTVIClientMessageFrame) -> None:
        data = frame.data if isinstance(frame.data, dict) else {}
        if frame.type == "user-text" and isinstance(data.get("text"), str):
            await self._carry_out(self._turns.user_typed(data["text"]))
        elif frame.type == "mute" and isinstance(data.get("muted"), bool):
            await self._carry_out(self._turns.text_only_switched(data["muted"]))
        elif frame.type == "hang-up":  # the browser closes the connection next
            self._outcome.ended_by("hung_up")

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
                    case Reply(text=text, number=number):
                        self._start_reply(text, number, after)
                    case Voice(text=text, reply=reply, segment=segment):
                        await self.push_frame(SegmentTextFrame(text, reply, segment))
                    case FlushVoice(reply=reply, segment=segment):
                        await self.push_frame(SegmentCompleteFrame(reply, segment))
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
                if text is not None:
                    await self._turn(text)
                limit = self._outcome.limit_reached()
                if limit is not None:
                    await self._end(limit)
            finally:
                self._inputs.task_done()

    async def _time(self, duration: timedelta) -> None:
        await asyncio.sleep(duration.total_seconds())
        self._outcome.time_up()
        self._inputs.put_nowait(None)  # wakes the worker, after the turn in progress

    async def _end(self, limit: LimitReached) -> None:
        """Hang up, once what is already on its way to TTS has been voiced, telling the
        browser why as `CallOutcome` says, unless it has been told already."""
        await self._carry_out(self._turns.call_ending())
        if limit.ended is not None:
            await self._send(limit.ended)
        await self.push_frame(EndWorkerFrame(reason=limit.why))

    async def _turn(self, text: str) -> None:
        """Take one turn, replied to afresh after each follow-on, until its reply is over;
        its activity record says how the last reply to it turned out (one dropped for a
        follow-on is not recorded apart), or how the call ending before it was over leaves it."""
        self._turn_over = asyncio.Event()
        recording = self._recording = self._outcome.turn_begun(self._call.own_llm)
        self._result = None
        try:
            await self._carry_out(self._turns.turn_started(text))
            await self._turn_over.wait()
        finally:  # the call may be hanging up
            self._stop_waiting()
            reply, self._reply = self._reply, None
            if reply is not None and not reply.done():
                await self.cancel_task(reply)
            recording.finish(self._result or self._outcome.turn_cut_short())
            self._recording = None

    def _start_reply(self, text: str, number: int, after: asyncio.Event | None = None) -> None:
        """Reply to `text`, as reply `number`, once `after` is set, if given."""
        self._stop_waiting()
        self._stop = asyncio.Event()
        self._reply = self.create_task(
            self._reply_to(text, number, self._stop, after, self._recording)
        )

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
        self._waiting = self.create_task(self._time_follow_on())

    async def _time_follow_on(self) -> None:
        """Tell `TurnTaking` the follow-on came to nothing, once `follow_on_timeout` has
        passed without it."""
        await asyncio.sleep(self._follow_on_timeout)
        self._waiting = None
        await self._carry_out(self._turns.follow_on_missed())

    def _stop_waiting(self) -> None:
        """Stop waiting for a follow-on, if waiting: it is no longer awaited."""
        if self._waiting is not None:
            self._waiting.cancel()
            self._waiting = None

    async def _reply_to(
        self,
        text: str,
        number: int,
        stop: asyncio.Event,
        after: asyncio.Event | None,
        recording: Recording | None,
    ) -> None:
        """Reply to what the user said, as reply `number` of the call, once `after` is set,
        if given, going no further once `stop` is set. Only a reply that is recorded counts
        as a turn: a rejected, failed or dropped one does not count towards the call's
        limit, an interrupted one does. Once it is over, recorded or not, so is the turn; a dropped one is not over,
        but gone, which whoever dropped it reports. Its service calls are recorded under
        the turn's `recording`, which is told how it turned out."""
        if after is not None:
            await after.wait()
        await self.push_frame(LLMFullResponseStartFrame())
        ja: dict[int, str] = {}  # each segment's Japanese so far, cues and all
        zh: dict[int, str] = {}  # and its subtitle
        try:
            with recording.current() if recording is not None else nullcontext():
                await self._reply_events(text, number, stop, ja, zh, recording)
        except Exception:  # the turn is over all the same, rather than the call stuck in it
            log.exception("reply in conversation %s failed", self._call.conversation.id)
        finally:
            await self.push_frame(LLMFullResponseEndFrame())
        await self._carry_out(self._turns.reply_ended())
        self._turn_over.set()

    async def _reply_events(
        self,
        text: str,
        number: int,
        stop: asyncio.Event,
        ja: dict[int, str],
        zh: dict[int, str],
        recording: Recording | None,
    ) -> None:
        """Carry out each event of the reply, as `_reply_to` says. The turn is told how it
        turned out as a text turn is, and, when the reply is only shown, that the
        character began to speak as its first words appear (「开口」)."""
        async for event in self._engine.turn(
            self._call.conversation, text, self._call.llms, self._call.device_timezone, stop
        ):
            if isinstance(event, SegmentComplete):
                await self._carry_out(self._turns.segment_complete(event.segment))
                if not stop.is_set():
                    self._judge_emotion(text, number, event.segment, ja, zh)
                continue
            if isinstance(event, SpeechDelta):  # the Japanese just shown, cues and all
                ja[event.segment] = ja.get(event.segment, "") + event.text
                await self._carry_out(self._turns.reply_delta("ja", event.text, event.segment))
                continue
            if isinstance(event, TurnDone):  # told before any await: no longer to be dropped
                await self._carry_out(self._turns.reply_recorded())
                self._outcome.turn_recorded()
            if (result := turn_result(event)) is not None:
                self._result = result
            message = asdict(event)
            if isinstance(event, UserSaid):
                message["reply"] = number
            await self._send(message)
            if isinstance(event, SegmentDelta):
                if recording is not None and not self._turns.voicing:
                    recording.spoke()
                if event.lang == "zh":
                    zh[event.segment] = zh.get(event.segment, "") + event.text
                    await self._carry_out(
                        self._turns.reply_delta("zh", event.text, event.segment)
                    )

    def _judge_emotion(
        self, said: str, reply: int, segment: int, ja: dict[int, str], zh: dict[int, str]
    ) -> None:
        """Have the emotion of segment `segment` of reply `reply` judged, the user having
        said `said`, and sent once it is, from what the reply's segments are (`ja`, `zh`)."""
        if self._emotions is None:
            return
        question = SegmentToJudge(
            self._call.character,
            said,
            [SaidSegment(ja.get(s, ""), zh.get(s, "")) for s in range(segment)],
            SaidSegment(ja.get(segment, ""), zh.get(segment, "")),
        )
        with self._outcome.recording.current():  # judged for the call, not the turn
            judging = self.create_task(
                self._send_emotion(self._emotions, reply, segment, question)
            )
        self._judging.add(judging)
        judging.add_done_callback(self._judging.discard)

    async def _send_emotion(
        self, emotions: EmotionJudging, reply: int, segment: int, question: SegmentToJudge
    ) -> None:
        message = await emotions.message(reply, segment, question)
        if message is not None:
            await self._send(message)

    async def _send(self, message: dict) -> None:
        await self.push_frame(RTVIServerMessageFrame(data=message))

    async def _stop_worker(self) -> None:
        for judging in list(self._judging):
            await self.cancel_task(judging)
        if self._timer is not None:
            await self.cancel_task(self._timer)
            self._timer = None
        if self._worker is not None:
            await self.cancel_task(self._worker)
            self._worker = None
