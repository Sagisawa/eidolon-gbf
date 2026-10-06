// Why a call ended other than by the user hanging up, and whether it counted towards the
// hourly limit (GLOSSARY.md「限额」「接通」). The backend names its reasons in the `ended`
// message; the rest are told apart here.

import { ApiError, type BackendEndReason, type CallEvent } from "@/lib/api";

/**
 * The backend's reasons (it never really connected; a voice service failed, or the connection
 * broke, after it connected; its time or turn limit; an own key failed), and two told apart
 * here: the user has no calls left this hour, or the browser would not let the call use the
 * microphone (or there is none).
 */
export type EndReason = BackendEndReason | "over_limit" | "mic_denied";

export type CallEnd = {
  reason: EndReason;
  /** What the backend said beyond the reason (when the user can call again, which key
   * failed, why calls are unavailable); null when the reason says it all. */
  detail: string | null;
  /** Whether the call counted towards the hourly limit. */
  counts: boolean;
};

/** The microphone could not be opened for a call. */
export class MicUnavailable extends Error {}

/** Statuses of a call the backend refuses: no calls left this hour, one of the user's own
 * keys fails. */
const OVER_LIMIT = 429;
const OWN_KEY_FAILED = 409;

/** A call that could not start. None of them count: it was refused, or it never connected. */
export function startFailedEnd(e: unknown): CallEnd {
  if (e instanceof MicUnavailable) return { reason: "mic_denied", detail: null, counts: false };
  if (!(e instanceof ApiError)) return { reason: "not_connected", detail: null, counts: false };
  const reason =
    e.status === OVER_LIMIT ? "over_limit" : e.status === OWN_KEY_FAILED ? "own_key" : "not_connected";
  return { reason, detail: e.message, counts: false };
}

/** The backend hung up and said why. Only a failing own key needs its words: they say which. */
export function backendEnd(event: Extract<CallEvent, { type: "ended" }>): CallEnd {
  return {
    reason: event.reason,
    detail: event.reason === "own_key" ? event.message : null,
    counts: event.counts,
  };
}

/** The connection broke with no word from the backend. The call had connected, so it counts
 * unless it was on the user's own keys alone. */
export function droppedEnd(exempt: boolean): CallEnd {
  return { reason: "dropped", detail: null, counts: !exempt };
}
