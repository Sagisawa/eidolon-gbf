// The phone's own sounds around a call (CONTEXT.md「铃声」「接通音」「挂断音」): what to start,
// stop or play once as the call moves from one phase to the next. Playing them is the page's.

import type { CallState } from "@/lib/liveConversation";

type Phase = CallState["phase"];

/** A short tone played once: the connect tone, or the hang-up tone. */
export type Tone = "connect" | "hang-up";

/** The ringback starts looping or stops; a short tone is played once. */
export type CallTones = { ring: "start" | "stop" | null; once: Tone | null };

export function callTones(from: Phase, to: Phase): CallTones {
  if (to === "dialing" && from !== "dialing") return { ring: "start", once: null };
  if (from === "dialing" && to === "connected") return { ring: "stop", once: "connect" };
  if (isLive(from) && !isLive(to)) return { ring: "stop", once: "hang-up" };
  return { ring: null, once: null };
}

function isLive(phase: Phase): boolean {
  return phase === "dialing" || phase === "connected";
}
