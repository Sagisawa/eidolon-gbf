// The conversation page for one character: opening her conversation (or starting a new
// one), its log, the text turn under way, the call and how the call layer is shown, kept
// outside React so the page only renders a snapshot and passes on clicks.

import {
  ApiError,
  type CallEvent,
  type Conversation,
  type Message,
  type Segment,
  type TurnEvent,
} from "@/lib/api";
import type { Call, CallHandlers, MicInUse } from "@/lib/call";
import { droppedEnd, backendEnd, startFailedEnd, type CallEnd } from "@/lib/callEnd";
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

/**
 * Where the call is (spec「通话状态」):
 * - `dialing`: opening the microphone and connecting; it can only be hung up;
 * - `connected`: the character can hear and speak (CONTEXT.md「接通」), since `since`; it
 *   may last `maxSeconds` (null for no limit);
 * - `ended`: over for a reason other than the user hanging up, shown until dismissed;
 *   a call the user hangs up goes straight back to `idle`.
 */
export type CallState =
  | { phase: "idle" }
  | { phase: "dialing" }
  | { phase: "connected"; since: number; maxSeconds: number | null }
  | { phase: "ended"; end: CallEnd };

/** A call under way: dialing or connected. Leaving the page hangs it up. */
export type LiveCall = Extract<CallState, { phase: "dialing" | "connected" }>;

export function isLive(call: CallState): call is LiveCall {
  return call.phase === "dialing" || call.phase === "connected";
}

export type MicNotice = "fell_back" | "unavailable" | "lost";

/**
 * Whether her conversation is open: `opening` while it is looked up (or started) and its
 * messages loaded; `failed` when that did not work, with the reason in `failure`.
 */
export type OpenStatus = "opening" | "open" | "failed";

export type Snapshot = {
  status: OpenStatus;
  entries: Entry[];
  call: CallState;
  /** The call layer is collapsed onto the conversation. It opens up again when dialing and
   * when the call ends for a reason, so the user sees why. */
  collapsed: boolean;
  /** The list of microphones is open; only while the call is connected. */
  pickingMic: boolean;
  /** What the user is saying in the call so far. */
  hearing: string;
  /** The character's latest line in this call, for the call screen; null until she has one. */
  line: Segment | null;
  /** The microphone is off in the browser (CONTEXT.md「麦克风静音」). */
  micMuted: boolean;
  /** The microphone the call is using; empty for the system default. */
  micId: string;
  /** Something to say about the microphone: the chosen one is not there and the system
   * default is used instead, the one just chosen could not be opened, or it was unplugged
   * and no other one opens. */
  micNotice: MicNotice | null;
  /** A text turn is under way. */
  busy: boolean;
  /** What is in the input box. */
  draft: string;
  /** Show the character's replies as text only (CONTEXT.md「只看文字」). */
  textOnly: boolean;
  /** The page's one error: the conversation could not be opened or started, a turn failed. */
  failure: Failure | null;
};

type State = Omit<Snapshot, "entries" | "line"> & {
  log: ConversationLog;
  /** How many entries there were when the call connected: her lines from there on are its. */
  callFrom: number;
};

const IDLE: Omit<Snapshot, "entries" | "line"> = {
  status: "opening",
  call: { phase: "idle" },
  collapsed: false,
  pickingMic: false,
  hearing: "",
  micMuted: false,
  micId: "",
  micNotice: null,
  busy: false,
  draft: "",
  textOnly: false,
  failure: null,
};

/** What the page shows before a conversation is open. */
export const NOT_OPEN: Snapshot = { ...IDLE, entries: [], line: null };

/** What the conversation needs from outside: the backend, this device's preferences, and
 * the conversation list beside the page. */
export type Ports = {
  /** Her conversations, newest first. */
  listConversations: (characterId: string) => Promise<Conversation[]>;
  createConversation: (characterId: string) => Promise<Conversation>;
  listMessages: (conversationId: string) => Promise<Message[]>;
  /** The conversation list's line for her has changed: a turn was recorded, or a
   * conversation was started. Told even after the page is left. */
  onListChanged: () => void;
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
  /** The time now, in milliseconds; `Date.now` unless a test stops the clock. */
  now?: () => number;
};

export class LiveConversation {
  private state: State;
  private published: Snapshot;
  private listeners = new Set<() => void>();
  private call: Call | null = null;
  /** The call being dialed or under way; a call hung up while dialing is no longer it. */
  private attempt: object | null = null;
  private endedBy: CallEnd | null = null; // why the backend is hanging up
  private disposed = false;
  /** The conversation open; null until it is. */
  private conversationId: string | null = null;
  /** A new conversation is being started: nothing is sent or dialed until it is. */
  private starting = false;

  /** Opens her newest conversation, or starts one if she has none. */
  constructor(
    private readonly characterId: string,
    private readonly ports: Ports,
  ) {
    this.state = { ...IDLE, log: emptyLog, callFrom: 0, textOnly: ports.preferences.load().muted };
    this.published = toSnapshot(this.state);
    void this.open();
  }

  /** A new object only after an update, as `useSyncExternalStore` needs. */
  snapshot = (): Snapshot => this.published;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  /** The page is left: hang up the call, even one still dialing. A text turn under way
   * is not stopped; its reply is still recorded, just no longer shown. A conversation
   * still opening is not shown either. */
  dispose(): void {
    this.disposed = true;
    this.attempt = null;
    this.call?.hangUp().catch(() => {});
    this.call = null;
  }

  /** Leave this conversation for a new, empty one. Not over a text turn or a call. */
  async startNewConversation(): Promise<void> {
    if (!this.ready() || this.state.busy || isLive(this.state.call)) return;
    this.starting = true;
    this.update({ failure: null });
    try {
      const conversation = await this.started();
      this.opened(conversation.id, [], { call: { phase: "idle" } });
    } catch (e) {
      this.update({ failure: toFailure(e) });
    } finally {
      this.starting = false;
    }
  }

  setDraft(draft: string): void {
    this.update({ draft: draft.slice(0, MAX_INPUT_LENGTH) });
  }

  /** Send what is in the input box as a text turn. */
  async submit(): Promise<void> {
    const text = this.state.draft.trim();
    const conversationId = this.conversationId;
    // One exchange at a time: not over a text turn, nor into a call still dialing.
    if (!text || !this.ready() || !conversationId || this.state.busy || this.state.call.phase === "dialing")
      return;
    this.update({ draft: "", failure: null });
    if (this.call) {
      // The call takes it up like speech; its reply arrives as call events.
      this.call.sendText(text);
      return;
    }
    this.apply({ type: "submitted", text, at: this.stamp() }, { busy: true });

    let failure: Failure | null = null;
    let done = false;
    try {
      for await (const event of this.ports.sendTurn(conversationId, text)) {
        this.turnEvent(event);
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

  /** Call the character, from idle or from the end of the last call. Not over a text turn. */
  async startCall(): Promise<void> {
    const conversationId = this.conversationId;
    if (!this.ready() || !conversationId || this.state.busy || isLive(this.state.call)) return;
    const attempt = {};
    this.attempt = attempt;
    this.endedBy = null;
    this.update({ call: { phase: "dialing" }, micMuted: false, failure: null });
    let started: Call;
    try {
      started = await this.ports.startCall(conversationId, this.ports.preferences.load(), {
        onEvent: (event) => this.onCallEvent(event),
        onHearing: (hearing) => this.update({ hearing }),
        onCharacterAudio: this.ports.onCharacterAudio,
        onDropped: () => {
          // Dropped while dialing: startCall fails, and that says why.
          if (this.call !== started) return;
          this.ended(this.endedBy ?? droppedEnd(started.exempt));
        },
        onMicLost: (now) => {
          if (this.call !== started) return;
          this.update(now ? micInUse(now) : { micId: "", micNotice: "lost" });
        },
      });
    } catch (e) {
      if (this.attempt === attempt) this.ended(startFailedEnd(e));
      return;
    }
    if (this.attempt !== attempt) {
      // Hung up, or the page left, while dialing: nothing else will hang this one up.
      await started.hangUp().catch(() => {});
      return;
    }
    this.call = started;
    this.update({
      call: { phase: "connected", since: this.now(), maxSeconds: started.maxSeconds },
      callFrom: this.state.log.entries.length,
      ...micInUse(started.mic),
    });
  }

  /** The user hangs up, dialing or connected: the call screen just closes. */
  async hangUp(): Promise<void> {
    if (!isLive(this.state.call)) return;
    const ending = this.call;
    this.attempt = null;
    this.ended(null);
    await ending?.hangUp().catch(() => {});
  }

  /** Leave the end of the last call. */
  dismissEnd(): void {
    if (this.state.call.phase === "ended") this.update({ call: { phase: "idle" } });
  }

  /** Collapse the call layer onto the conversation, while the call is under way. */
  collapse(): void {
    if (isLive(this.state.call) && !this.state.collapsed) this.update({ collapsed: true });
  }

  expand(): void {
    if (this.state.collapsed) this.update({ collapsed: false });
  }

  /** Open the list of microphones to switch to; only while the call is connected. */
  openMicPicker(): void {
    if (this.state.call.phase === "connected" && !this.state.pickingMic) this.update({ pickingMic: true });
  }

  closeMicPicker(): void {
    if (this.state.pickingMic) this.update({ pickingMic: false });
  }

  /** Mic mute: the microphone's track only, in the browser; typing still goes to the call. */
  toggleMic(): void {
    if (!this.call) return;
    const micMuted = !this.state.micMuted;
    this.call.setMicEnabled(!micMuted);
    this.update({ micMuted });
  }

  /** Switch the call to another microphone; it becomes the default for later calls too.
   * If it cannot be opened, the call keeps the one in use and the default is not changed. */
  async switchMic(micId: string): Promise<void> {
    const call = this.call;
    if (!call) return;
    let mic: MicInUse;
    try {
      mic = await call.switchMic(micId);
    } catch {
      if (this.call === call) this.update({ micNotice: "unavailable" });
      return;
    }
    this.ports.preferences.save({ micId });
    if (this.call === call) this.update(micInUse(mic));
  }

  /** Text only: kept in the preferences, and told to the call under way. */
  toggleTextOnly(): void {
    const textOnly = !this.state.textOnly;
    this.ports.preferences.save({ muted: textOnly });
    this.call?.setTextOnly(textOnly);
    this.update({ textOnly });
  }

  private onCallEvent(event: CallEvent): void {
    if (event.type === "ended") {
      this.endedBy = backendEnd(event);
      return;
    }
    if (event.type === "user") this.turnEvent(event, { hearing: "" });
    else if (event.type === "error")
      this.turnEvent(event, { failure: { message: event.message, signedOut: false } });
    else this.turnEvent(event);
  }

  /** Moves the log on by an event of a turn, typed or spoken in a call. */
  private turnEvent(event: TurnEvent, change: Partial<State> = {}): void {
    this.apply(event.type === "user" ? { ...event, at: this.stamp() } : event, change);
    // Recorded: the list's line for her now ends with it, even if the page has been left.
    if (event.type === "done") this.ports.onListChanged();
  }

  private async open(): Promise<void> {
    let conversation: Conversation;
    let messages: Message[];
    try {
      const [newest] = await this.ports.listConversations(this.characterId);
      conversation = newest ?? (await this.started());
      messages = await this.ports.listMessages(conversation.id);
    } catch (e) {
      this.update({ status: "failed", failure: toFailure(e) });
      return;
    }
    if (!this.disposed) this.opened(conversation.id, messages, { status: "open" });
  }

  /** Starts a conversation with her. The list shows it at once, even if the page has been
   * left meanwhile: it is there in the backend all the same. */
  private async started(): Promise<Conversation> {
    const conversation = await this.ports.createConversation(this.characterId);
    this.ports.onListChanged();
    return conversation;
  }

  /** Shows this conversation and its messages from now on. */
  private opened(conversationId: string, messages: Message[], change: Partial<State>): void {
    this.conversationId = conversationId;
    this.apply({ type: "loaded", messages }, { ...change, callFrom: messages.length });
  }

  /** A conversation is open and not being left for a new one. */
  private ready(): boolean {
    return this.state.status === "open" && !this.starting;
  }

  /** The time now, as the log dates entries. */
  private stamp(): string {
    return new Date(this.now()).toISOString();
  }

  /** The call is over, hung up (no `end`) or not; a reply it cut off is not recorded. */
  private ended(end: CallEnd | null): void {
    this.call = null;
    this.apply(
      { type: "interrupted" },
      {
        call: end ? { phase: "ended", end } : { phase: "idle" },
        hearing: "",
        micMuted: false,
        micId: "",
        micNotice: null,
      },
    );
  }

  private now(): number {
    return (this.ports.now ?? Date.now)();
  }

  /** Moves the log on by one action, along with any other change. */
  private apply(action: LogAction, change: Partial<State> = {}): void {
    this.update({ ...change, log: conversationLog(this.state.log, action) });
  }

  private update(change: Partial<State>): void {
    if (this.disposed) return;
    const next = { ...this.state, ...change };
    // Dialing, and a call ending for a reason, open the call layer up again: the user sees
    // the call, or why it ended. The microphone list is only for a connected call.
    if (next.call !== this.state.call && (next.call.phase === "dialing" || next.call.phase === "ended"))
      next.collapsed = false;
    if (next.call.phase !== "connected") next.pickingMic = false;
    this.state = next;
    this.published = toSnapshot(this.state);
    for (const listener of this.listeners) listener();
  }
}

function micInUse(mic: MicInUse): Pick<State, "micId" | "micNotice"> {
  return { micId: mic.id, micNotice: mic.fellBack ? "fell_back" : null };
}

function toSnapshot({ log, callFrom, ...rest }: State): Snapshot {
  return { ...rest, entries: log.entries, line: latestLine(log.entries.slice(callFrom)) };
}

/** The last line she has begun to say among these entries. */
function latestLine(entries: Entry[]): Segment | null {
  for (let i = entries.length - 1; i >= 0; i--) {
    const entry = entries[i];
    if (entry.kind !== "character") continue;
    const line = entry.segments.findLast((segment) => segment.ja);
    if (line) return line;
  }
  return null;
}
