// A voice call with the character, over WebRTC to the backend's Pipecat pipeline.
//
// The character's voice arrives as an audio track; everything else (what the
// backend heard, the reply's Japanese and its subtitles) arrives as the same
// events as a text turn, over the data channel.

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
import { Microphone } from "@/lib/microphone";

export type CallHandlers = {
  onEvent: (event: CallEvent) => void;
  /** What the user is saying so far; empty once the utterance is complete. */
  onHearing: (text: string) => void;
  /** The character's speech, to play. */
  onCharacterAudio: (track: MediaStreamTrack) => void;
  /** The call ended without the user hanging up. */
  onDropped: () => void;
};

/** A call that has connected: the character can hear and speak (CONTEXT.md「接通」). */
export type Call = {
  /** How long the call may last, in seconds; null for no limit. */
  maxSeconds: number | null;
  /** On the user's own keys alone, so it does not count towards the hourly limit. */
  exempt: boolean;
  /** Say something by typing it; the character answers in the call. */
  sendText: (text: string) => void;
  /** Whether the character's replies are voiced (CONTEXT.md「只看文字」). */
  setTextOnly: (textOnly: boolean) => void;
  /** Turn the microphone's track on or off in the browser (CONTEXT.md「麦克风静音」). */
  setMicEnabled: (enabled: boolean) => void;
  hangUp: () => Promise<void>;
};

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
    client = new PipecatClient({
      transport: new SmallWebRTCTransport({ iceServers, mediaManager: microphone }),
      enableMic: true,
      enableCam: false,
      callbacks: {
        onServerMessage: (data) => handlers.onEvent(data as CallEvent),
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
    hangUp: async () => {
      hungUp = true;
      await connected.disconnect();
    },
  };
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
