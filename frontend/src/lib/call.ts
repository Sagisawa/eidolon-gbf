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
  getIceServers,
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

export type Call = {
  /** Say something by typing it; the character answers in the call. */
  sendText: (text: string) => void;
  setMuted: (muted: boolean) => void;
  hangUp: () => Promise<void>;
};

export async function startCall(
  conversationId: string,
  preferences: CallPreferences,
  handlers: CallHandlers,
): Promise<Call> {
  const iceServers = await getIceServers();
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
    sendText: (text) => connected.sendClientMessage("user-text", { text }),
    setMuted: (muted) => connected.sendClientMessage("mute", { muted }),
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
