// The conversation open on the conversation page: its log, the text turn under way and
// the call, kept outside React so the page only renders a snapshot and passes on clicks.

import { ApiError, type CallEvent, type Message, type TurnEvent } from "@/lib/api";
import type { Call, CallHandlers } from "@/lib/call";
import type { CallPreferences } from "@/lib/callPreferences";
import {
  conversationLog,
  emptyLog,
  type ConversationLog,
  type Entry,
  type LogAction,
} from "@/lib/conversationLog";
import { toFailure, type Failure } from "@/lib/failure";

/** The longest message the backend accepts (`MAX_INPUT_LENGTH` in `engine.py`). */
const MAX_INPUT_LENGTH = 2000;

export type CallPhase = "idle" | "connecting" | "active";

export type Snapshot = {
  entries: Entry[];
  phase: CallPhase;
  /** What the user is saying in the call so far. */
  hearing: string;
  /** A text turn is under way. */
  busy: boolean;
  /** What is in the input box. */
  draft: string;
  /** Show the character's replies as text only. */
  muted: boolean;
  failure: Failure | null;
};

type State = Omit<Snapshot, "entries"> & { log: ConversationLog };

const IDLE: Omit<Snapshot, "entries"> = {
  phase: "idle",
  hearing: "",
  busy: false,
  draft: "",
  muted: false,
  failure: null,
};

/** What the page shows before a conversation is open. */
export const NOT_OPEN: Snapshot = { ...IDLE, entries: [] };

/** What the conversation needs from outside: the backend, and this device's preferences. */
export type Ports = {
  startCall: (
    conversationId: string,
    preferences: CallPreferences,
    handlers: CallHandlers,
  ) => Promise<Call>;
  sendTurn: (conversationId: string, text: string) => AsyncIterable<TurnEvent>;
  preferences: {
    load: () => CallPreferences;
    save: (change: Partial<CallPreferences>) => CallPreferences;
  };
  /** The character's speech in a call, to play. */
  onCharacterAudio: (track: MediaStreamTrack) => void;
};

export class LiveConversation {
  private state: State;
  private published: Snapshot;
  private listeners = new Set<() => void>();
  private call: Call | null = null;
  private endReason: string | null = null; // why the backend is hanging up
  private disposed = false;

  constructor(
    private readonly conversationId: string,
    messages: Message[],
    private readonly ports: Ports,
  ) {
    this.state = {
      ...IDLE,
      log: conversationLog(emptyLog, { type: "loaded", messages }),
      muted: ports.preferences.load().muted,
    };
    this.published = toSnapshot(this.state);
  }

  /** A new object only after an update, as `useSyncExternalStore` needs. */
  snapshot = (): Snapshot => this.published;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  /** The page is left: hang up the call, even one still connecting. A text turn under way
   * is not stopped; its reply is still recorded, just no longer shown. */
  dispose(): void {
    this.disposed = true;
    this.call?.hangUp().catch(() => {});
    this.call = null;
  }

  setDraft(draft: string): void {
    this.update({ draft: draft.slice(0, MAX_INPUT_LENGTH) });
  }

  /** Send what is in the input box as a text turn. */
  async submit(): Promise<void> {
    const text = this.state.draft.trim();
    // One exchange at a time: not over a text turn, nor into a call still connecting.
    if (!text || this.state.busy || this.state.phase === "connecting") return;
    this.update({ draft: "", failure: null });
    if (this.call) {
      // The call takes it up like speech; its reply arrives as call events.
      this.call.sendText(text);
      return;
    }
    this.apply({ type: "submitted", text }, { busy: true });

    let failure: Failure | null = null;
    let done = false;
    try {
      for await (const event of this.ports.sendTurn(this.conversationId, text)) {
        this.apply(event);
        if (event.type === "done") done = true;
        // A turn that failed leaves no record and does not count towards the limit.
        if (event.type === "error")
          failure = { message: event.message, signedOut: false, countsTowardLimit: false };
      }
      // Cut off: whether the backend still recorded (and counted) it cannot be told here.
      if (!done && !failure) failure = { message: "回复中断了，请再试一次", signedOut: false };
    } catch (e) {
      failure = toFailure(e);
      // Refused by the backend (over the limit, own key failed, ...): not counted.
      if (e instanceof ApiError) failure.countsTowardLimit = false;
    }
    if (failure) {
      // A failed turn is not recorded: take it back off the log and return the text to the input.
      this.apply({ type: "interrupted" }, { draft: text, failure });
    }
    this.update({ busy: false });
  }

  /** Start a call, or hang up the one under way. */
  async toggleCall(): Promise<void> {
    if (this.call) {
      const ending = this.call;
      this.ended(null);
      await ending.hangUp().catch(() => {});
      return;
    }
    // Not over a text turn; and a call connecting cannot be called off.
    if (this.state.busy || this.state.phase === "connecting") return;
    this.endReason = null;
    this.update({ phase: "connecting", failure: null });
    let started: Call;
    try {
      started = await this.ports.startCall(this.conversationId, this.ports.preferences.load(), {
        onEvent: (event) => this.onCallEvent(event),
        onHearing: (hearing) => this.update({ hearing }),
        onCharacterAudio: this.ports.onCharacterAudio,
        onDropped: () => {
          // Dropped while connecting: startCall fails, and that says why.
          if (this.call !== started) return;
          this.ended({ message: this.endReason ?? "通话已断开", signedOut: false });
        },
      });
    } catch (e) {
      this.update({ phase: "idle", failure: toFailure(e) });
      return;
    }
    if (this.disposed) {
      // Left while connecting: dispose found no call to hang up, so hang this one up now.
      await started.hangUp().catch(() => {});
      return;
    }
    this.call = started;
    this.update({ phase: "active" });
  }

  toggleMute(): void {
    const muted = !this.state.muted;
    this.ports.preferences.save({ muted });
    this.call?.setMuted(muted);
    this.update({ muted });
  }

  private onCallEvent(event: CallEvent): void {
    if (event.type === "ended") {
      this.endReason = event.message;
      return;
    }
    if (event.type === "user") this.apply(event, { hearing: "" });
    else if (event.type === "error")
      this.apply(event, { failure: { message: event.message, signedOut: false } });
    else this.apply(event);
  }

  /** The call is over, hung up or dropped; a reply it cut off is not recorded. */
  private ended(failure: Failure | null): void {
    this.call = null;
    this.apply(
      { type: "interrupted" },
      { phase: "idle", hearing: "", ...(failure && { failure }) },
    );
  }

  /** Moves the log on by one action, along with any other change. */
  private apply(action: LogAction, change: Partial<State> = {}): void {
    this.update({ ...change, log: conversationLog(this.state.log, action) });
  }

  private update(change: Partial<State>): void {
    if (this.disposed) return;
    this.state = { ...this.state, ...change };
    this.published = toSnapshot(this.state);
    for (const listener of this.listeners) listener();
  }
}

function toSnapshot({ log, ...rest }: State): Snapshot {
  return { ...rest, entries: log.entries };
}
