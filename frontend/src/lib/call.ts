// A voice call with the character, over WebRTC to the backend's Pipecat pipeline.
//
// The character's voice arrives as an audio track; everything else (what the
// backend heard, the reply's Japanese and its subtitles) arrives as the same
// events as a text turn, over the data channel, along with who starts and stops
// speaking.

import { PipecatClient, TransportStartError } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";
import {
  ApiError,
  apiHeaders,
  followRedirect,
  getCallSetup,
  json,
  type CallEvent,
} from "@/lib/api";
import type { CallPreferences } from "@/lib/callPreferences";
import { Microphone, type MicInUse } from "@/lib/microphone";

export type { MicInUse };

export type CallHandlers = {
  onEvent: (event: CallEvent) => void;
  /** What the user is saying so far; empty once the utterance is complete. */
  onHearing: (text: string) => void;
  /** The character's speech, to play. */
  onCharacterAudio: (track: MediaStreamTrack) => void;
  /** The call ended without the user hanging up. */
  onDropped: () => void;
  /** The microphone in use was unplugged; the call goes on with the system default in its
   * place, or with no microphone (null) if none could be opened. */
  onMicLost: (now: MicInUse | null) => void;
};

/** A call that has connected: the character can hear and speak (GLOSSARY.md「接通」). */
export type Call = {
  /** How long the call may last, in seconds; null for no limit. */
  maxSeconds: number | null;
  /** On the user's own keys alone, so it does not count towards the hourly limit. */
  exempt: boolean;
  /** Say something by typing it; the character answers in the call. */
  sendText: (text: string) => void;
  /** Whether the character's replies are voiced (GLOSSARY.md「只看文字」). */
  setTextOnly: (textOnly: boolean) => void;
  /** Turn the microphone's track on or off in the browser (GLOSSARY.md「麦克风静音」). */
  setMicEnabled: (enabled: boolean) => void;
  /** The microphone the call connected with. */
  mic: MicInUse;
  /** Send from another microphone without interrupting the call, muted if it was.
   * Fails with MicUnavailable, keeping the one in use, if it cannot be opened. */
  switchMic: (micId: string) => Promise<MicInUse>;
  /** The user hangs up: the backend is told so, for the call's activity record (GLOSSARY
   * 「运行记录」), just before the connection closes. */
  hangUp: () => Promise<void>;
  /** The page is left: the connection just closes. */
  leave: () => Promise<void>;
};

/** How long a hang-up message is given to go out before the connection closing would drop
 * it; the call screen has closed already. */
const HANG_UP_GRACE_MS = 150;

/** Connects a call; resolves once it has connected, on the bot's `bot-ready`. That comes
 * only after the peer connection and its data channel are open, which is when the backend
 * starts counting the call as connected. Fails with MicUnavailable, an ApiError carrying
 * the backend's reason, or an Error when it could not connect. */
export async function startCall(
  conversationId: string,
  preferences: CallPreferences,
  handlers: CallHandlers,
): Promise<Call> {
  const { iceServers, maxCallSeconds, callExempt } = await getCallSetup();
  const microphone = await Microphone.open(preferences.micId);
  let hungUp = false;
  let client: PipecatClient | null = null;
  try {
    const transport = new SmallWebRTCTransport({ iceServers, mediaManager: microphone });
    microphone.onTrackChange = (track) => audioSender(transport).replaceTrack(track);
    microphone.onLost = handlers.onMicLost;
    client = new PipecatClient({
      transport,
      enableMic: true,
      enableCam: false,
      callbacks: {
        onServerMessage: (data) => handlers.onEvent(data as CallEvent),
        onBotStartedSpeaking: () => handlers.onEvent({ type: "bot-started-speaking" }),
        onBotStoppedSpeaking: () => handlers.onEvent({ type: "bot-stopped-speaking" }),
        onUserStartedSpeaking: () => handlers.onEvent({ type: "user-started-speaking" }),
        onUserStoppedSpeaking: () => handlers.onEvent({ type: "user-stopped-speaking" }),
        onUserTranscript: (data) => handlers.onHearing(data.final ? "" : data.text),
        onTrackStarted: (track, participant) => {
          if (!participant?.local && track.kind === "audio") handlers.onCharacterAudio(track);
        },
        onDisconnected: () => {
          if (!hungUp) handlers.onDropped();
        },
      },
    });
    await client.connect({
      webrtcRequestParams: {
        endpoint: "/api/offer",
        headers: apiHeaders(),
        requestData: {
          conversation_id: conversationId,
          muted: preferences.muted,
          quality: preferences.quality,
        },
      },
    });
  } catch (e) {
    hungUp = true;
    await client?.disconnect().catch(() => {});
    await microphone.disconnect();
    throw await explain(e);
  }

  const connected = client;
  return {
    maxSeconds: maxCallSeconds,
    exempt: callExempt,
    sendText: (text) => connected.sendClientMessage("user-text", { text }),
    setTextOnly: (textOnly) => connected.sendClientMessage("mute", { muted: textOnly }),
    setMicEnabled: (enabled) => microphone.enableMic(enabled),
    mic: microphone.inUse,
    switchMic: (micId) => microphone.updateMic(micId),
    hangUp: async () => {
      hungUp = true;
      try {
        connected.sendClientMessage("hang-up", {});
        await new Promise((resolve) => setTimeout(resolve, HANG_UP_GRACE_MS));
      } catch {
        // The connection is gone already: there is no one left to tell.
      }
      await connected.disconnect();
    },
    leave: async () => {
      hungUp = true;
      await connected.disconnect();
    },
  };
}

/** Where the transport sends the microphone from. It exposes no way to swap its track (its
 * own media managers are built in and use this same method), so it is reached from here;
 * replacing a sender's track needs no renegotiation. */
function audioSender(transport: SmallWebRTCTransport): RTCRtpSender {
  const withTransceivers = transport as unknown as { getAudioTransceiver?: () => RTCRtpTransceiver };
  if (!withTransceivers.getAudioTransceiver) throw new Error("the transport cannot switch microphones");
  return withTransceivers.getAudioTransceiver().sender;
}

/** Turn a failed call into an error that says why, in the user's language; sends the browser
 * on when it has to sign in, or agree to the terms, first. */
async function explain(e: unknown): Promise<Error> {
  if (e instanceof TransportStartError && e.cause instanceof Response) {
    followRedirect(e.cause);
    try {
      await json(e.cause); // throws an ApiError carrying the backend's reason
    } catch (reason) {
      if (reason instanceof ApiError) return reason;
    }
  }
  return new Error("无法接通，请稍后再试");
}
