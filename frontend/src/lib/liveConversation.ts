// The conversation page for one character: opening her conversation (or starting a new
// one), its log, the text turn under way, the call and how the call layer is shown, and her
// stand as the call moves it on (by the rules in `standDirection.ts`), kept outside React so
// the page only renders a snapshot and passes on clicks.

import { ApiError, type CallEvent, type Conversation, type Message, type Segment, type TurnEvent } from "@/lib/api";
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
import { CALM, type StandDirection } from "@/lib/standAnimations";
import { directionOf, directStand, startingStand, type StandEvent, type StandState } from "@/lib/standDirection";

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
 * messages loaded, and again while a new conversation is started; `failed` when it could
 * not be opened, saying why. Nothing is sent or dialed unless it is `open`.
 */
export type OpenState = { status: "opening" } | { status: "open" } | { status: "failed"; failure: Failure };

export type Snapshot = {
  conversation: OpenState;
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
  /** A call can be dialed now: `startCall` would. */
  canDial: boolean;
  /** A new conversation can be started now: `startNewConversation` would. */
  canStartNew: boolean;
  /** What went wrong in the conversation open: a turn failed, a new conversation could not
   * be started. Why it could not be opened at all is in `conversation`. */
  failure: Failure | null;
  /** How her stand should look (spec「立绘指令」), by the rules in `standDirection.ts`; calm
   * outside a call. It follows the call while the call layer is collapsed too. */
  stand: StandDirection;
};

type State = Omit<Snapshot, "entries" | "line" | "stand" | "canDial" | "canStartNew"> & {
  log: ConversationLog;
  /** How many entries there were when the call connected: her lines from there on are its. */
  callFrom: number;
  /** Her stand direction, moved on by the call under way. */
  stand: StandState;
};

const IDLE: Omit<State, "log" | "callFrom" | "stand"> = {
  conversation: { status: "opening" },
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
export const NOT_OPEN: Snapshot = {
  ...IDLE,
  entries: [],
  line: null,
  stand: CALM,
  canDial: false,
  canStartNew: false,
};

/** Her voice in a call (`CharacterVoice`): plain or over a phone line, silent in text only. */
export type Voice = {
  /** A call is being dialed, inside the user's click: over the phone line or not. */
  dial: (phoneTexture: boolean) => void;
  /** Her voice has arrived in the call under way. */
  play: (track: MediaStreamTrack) => void;
  setTextOnly: (textOnly: boolean) => void;
  /** The page is left. */
  dispose: () => void;
};

/** What the conversation needs from outside: the backend, this device's preferences, her
 * voice, and the conversation list beside the page. */
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
  voice: Voice;
  /** The time now, in milliseconds; `Date.now` unless a test stops the clock. */
  now?: () => number;
};

export class LiveConversation {
  private state: State;
  private published: Snapshot;
  private listeners = new Set<() => void>();
  private call: Call | null = null;
  /** The dialing of the call under way; null once that call is over, however it ended, or
   * the page is left (see `startCall`). */
  private attempt: object | null = null;
  private endedBy: CallEnd | null = null; // why the backend is hanging up
  private disposed = false;
  /** The conversation open; null until it is. */
  private conversationId: string | null = null;

  /** Opens her newest conversation, or starts one if she has none. */
  constructor(
    private readonly characterId: string,
    private readonly ports: Ports,
  ) {
    const textOnly = ports.preferences.load().muted;
    ports.voice.setTextOnly(textOnly);
    this.state = { ...IDLE, log: emptyLog, callFrom: 0, textOnly, stand: startingStand(textOnly) };
    this.published = toSnapshot(this.state);
    void this.open();
  }

  /** A new object only after an update, as `useSyncExternalStore` needs. */
  snapshot = (): Snapshot => this.published;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  /** The page is left: hang up the call, even one still dialing, and stop her voice. A
   * text turn under way is not stopped; its reply is still recorded, just no longer shown.
   * A conversation still opening is not shown either. */
  dispose(): void {
    this.disposed = true;
    this.attempt = null;
    this.call?.hangUp().catch(() => {});
    this.call = null;
    this.ports.voice.dispose();
  }

  /** Leave this conversation for a new, empty one, with an empty input box. Not over a
   * text turn or a call. It is opening until the new one is started; if that fails, this
   * one stays open. */
  async startNewConversation(): Promise<void> {
    if (!isFree(this.state)) return;
    this.update({ conversation: { status: "opening" }, failure: null });
    try {
      const conversation = await this.createConversation();
      this.showConversation(conversation.id, [], { call: { phase: "idle" }, draft: "" });
    } catch (e) {
      this.update({ conversation: { status: "open" }, failure: toFailure(e) });
    }
  }

  setDraft(draft: string): void {
    this.update({ draft: draft.slice(0, MAX_INPUT_LENGTH) });
  }

  /** Send what is in the input box as a text turn. */
  async submit(): Promise<void> {
    const text = this.state.draft.trim();
    const conversationId = this.openConversationId();
    // One exchange at a time: not over a text turn, nor into a call still dialing.
    if (!text || !conversationId || this.state.busy || this.state.call.phase === "dialing") return;
    this.update({ draft: "", failure: null });
    if (this.call) {
      // The call takes it up like speech; its reply arrives as call events. Typed while she
      // speaks, it interrupts her.
      this.call.sendText(text);
      const stand = this.directed({ type: "typed" });
      if (stand !== this.state.stand) this.update({ stand });
      return;
    }
    this.apply({ type: "submitted", text, at: this.isoNow() }, { busy: true });

    let failure: Failure | null = null;
    let done = false;
    try {
      for await (const event of this.ports.sendTurn(conversationId, text)) {
        this.applyTurnEvent(event);
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

  /**
   * Call the character, from idle or from the end of the last call. Not over a text turn.
   * Call it inside the user's click, before anything is awaited: her voice is told here,
   * and only then may it start its audio context (browsers keep one started outside a
   * user gesture suspended).
   *
   * This dialing is the call under way until it ends, however it ends: hung up, dropped
   * (with or without the backend saying why), failed to connect, or the page left. Once it
   * is not, the call's messages are too late and change nothing: not the log, the failure,
   * why the call ended, what is being heard, the microphone, her stand, her voice, or the
   * list. That rule is kept here alone, in the gate every handler given to the call goes
   * through; the handlers behind it do not ask again.
   */
  async startCall(): Promise<void> {
    const conversationId = this.openConversationId();
    if (!conversationId || !isFree(this.state)) return;
    // Read once: the phone texture her voice is told is the one the call is given.
    const preferences = this.ports.preferences.load();
    this.ports.voice.dial(preferences.phoneTexture);
    const attempt = {};
    this.attempt = attempt;
    this.endedBy = null;
    this.update({ call: { phase: "dialing" }, micMuted: false, failure: null });
    const current = () => this.attempt === attempt;
    // The gate: what the call sends once it is over changes nothing.
    const gated =
      <A extends unknown[]>(handler: (...args: A) => void) =>
      (...args: A): void => {
        if (current()) handler(...args);
      };
    let started: Call;
    try {
      started = await this.ports.startCall(conversationId, preferences, {
        onEvent: gated((event) => this.onCallEvent(event)),
        onHearing: gated((hearing) => this.update({ hearing })),
        onCharacterAudio: gated((track) => this.ports.voice.play(track)),
        onDropped: gated(() => {
          // Dropped while dialing: startCall fails, and that says why.
          if (this.state.call.phase === "dialing") return;
          this.ended(this.endedBy ?? droppedEnd(started.exempt));
        }),
        onMicLost: gated((now) => {
          // Lost while dialing: the call says which microphone it has once it connects.
          if (this.state.call.phase === "dialing") return;
          this.update(now ? micInUse(now) : { micId: "", micNotice: "lost" });
        }),
      });
    } catch (e) {
      if (current()) this.ended(startFailedEnd(e));
      return;
    }
    if (!current()) {
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

  /** Text only: kept in the preferences, and told to her voice and the call under way. */
  toggleTextOnly(): void {
    const textOnly = !this.state.textOnly;
    this.ports.preferences.save({ muted: textOnly });
    this.ports.voice.setTextOnly(textOnly);
    this.call?.setTextOnly(textOnly);
    this.update({ textOnly, stand: this.directed({ type: "text-only", textOnly }) });
  }

  /** An event of the call under way: one that is over never gets here (see `startCall`). */
  private onCallEvent(event: CallEvent): void {
    const stand = this.directed(event);
    switch (event.type) {
      case "ended":
        this.endedBy = backendEnd(event);
        return;
      case "user":
        return this.applyTurnEvent(event, { hearing: "", stand });
      case "error":
        return this.applyTurnEvent(event, { failure: { message: event.message, signedOut: false }, stand });
      case "delta":
      case "done":
        return this.applyTurnEvent(event, { stand });
      default:
        this.update({ stand });
    }
  }

  /** Her stand, moved on by this event (see `standDirection.ts` for how she looks). */
  private directed(event: StandEvent): StandState {
    return directStand(this.state.stand, event);
  }

  /** Moves the log on by an event of a turn, typed or spoken in a call. */
  private applyTurnEvent(event: TurnEvent, change: Partial<State> = {}): void {
    this.apply(event.type === "user" ? { ...event, at: this.isoNow() } : event, change);
    // Recorded: the list's line for her now ends with it, even if the page has been left.
    if (event.type === "done") this.ports.onListChanged();
  }

  /** Opens her newest conversation, or starts one if she has none. */
  private async open(): Promise<void> {
    let conversation: Conversation;
    let messages: Message[];
    try {
      const [newest] = await this.ports.listConversations(this.characterId);
      // The page left: no conversation is started for it.
      if (!newest && this.disposed) return;
      conversation = newest ?? (await this.createConversation());
      messages = await this.ports.listMessages(conversation.id);
    } catch (e) {
      this.update({ conversation: { status: "failed", failure: toFailure(e) } });
      return;
    }
    if (!this.disposed) this.showConversation(conversation.id, messages);
  }

  /** Starts a conversation with her. The list shows it at once, even if the page has been
   * left meanwhile: it is there in the backend all the same. */
  private async createConversation(): Promise<Conversation> {
    const conversation = await this.ports.createConversation(this.characterId);
    this.ports.onListChanged();
    return conversation;
  }

  /** Shows this conversation and its messages from now on: it is open. */
  private showConversation(conversationId: string, messages: Message[], change: Partial<State> = {}): void {
    this.conversationId = conversationId;
    this.apply(
      { type: "loaded", messages },
      { ...change, conversation: { status: "open" }, callFrom: messages.length },
    );
  }

  /** The conversation to send to and call in, or null if none is open: still opening,
   * being left for a new one, or failed to open. */
  private openConversationId(): string | null {
    return this.state.conversation.status === "open" ? this.conversationId : null;
  }

  /** The time now, as the log dates entries. */
  private isoNow(): string {
    return new Date(this.now()).toISOString();
  }

  /** The call is over, hung up (no `end`) or not; a reply it cut off is not recorded. It is
   * no longer the call under way, so whatever it sends from now on is too late (see
   * `startCall`). */
  private ended(end: CallEnd | null): void {
    this.attempt = null;
    this.call = null;
    this.apply(
      { type: "interrupted" },
      {
        call: end ? { phase: "ended", end } : { phase: "idle" },
        hearing: "",
        micMuted: false,
        micId: "",
        micNotice: null,
        stand: this.directed({ type: "call-over" }),
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
    this.state = withCallScreenRules(this.state, { ...this.state, ...change });
    this.published = toSnapshot(this.state);
    for (const listener of this.listeners) listener();
  }
}

/**
 * How the call screen follows the call, from one state to the next: dialing, and a call
 * ending for a reason, open the call layer up again, so the user sees the call or why it
 * ended; the microphone list is only for a connected call.
 */
function withCallScreenRules(before: State, next: State): State {
  const reopens = next.call !== before.call && (next.call.phase === "dialing" || next.call.phase === "ended");
  const collapsed = next.collapsed && !reopens;
  const pickingMic = next.pickingMic && next.call.phase === "connected";
  if (collapsed === next.collapsed && pickingMic === next.pickingMic) return next;
  return { ...next, collapsed, pickingMic };
}

/** Her conversation is open with nothing under way in it, no text turn and no call: a
 * call can be dialed, or a new conversation started (`canDial`, `canStartNew`). */
function isFree(state: State): boolean {
  return state.conversation.status === "open" && !state.busy && !isLive(state.call);
}

function micInUse(mic: MicInUse): Pick<State, "micId" | "micNotice"> {
  return { micId: mic.id, micNotice: mic.fellBack ? "fell_back" : null };
}

function toSnapshot(state: State): Snapshot {
  const { log, callFrom, stand, ...rest } = state;
  const free = isFree(state);
  return {
    ...rest,
    entries: log.entries,
    line: latestLine(log.entries.slice(callFrom)),
    stand: directionOf(stand),
    canDial: free,
    canStartNew: free,
  };
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
