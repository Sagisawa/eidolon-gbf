// The conversation page for one character: opening her conversation (or starting a new
// one), its log, the text turn under way, the call and how the call layer is shown, kept
// outside React so the page only renders a snapshot and passes on clicks.

import {
  ApiError,
  type CallEvent,
  type Conversation,
  type Message,
  SPEAKING,
  type Segment,
  type SegmentEmotion,
  type SegmentPlaying,
  type Speaking,
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
import { CALM, type StandDirection } from "@/lib/standAnimations";

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
  /** Which segment of which of her replies in this call her voice last started playing; null
   * until it has started. */
  playing: Omit<SegmentPlaying, "type"> | null;
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
  /** What went wrong in the conversation open: a turn failed, a new conversation could not
   * be started. Why it could not be opened at all is in `conversation`. */
  failure: Failure | null;
  /** How her stand should look (spec「立绘指令」); calm outside a call. It follows the call
   * while the call layer is collapsed too. */
  stand: StandDirection;
};

type State = Omit<Snapshot, "entries" | "line"> & {
  log: ConversationLog;
  /** How many entries there were when the call connected: her lines from there on are its. */
  callFrom: number;
  /** Her voice is playing in the call. Her mouth moves with it, unless it is text only. */
  voicing: boolean;
  /** The user is speaking in the call; she looks at them. */
  userSpeaking: boolean;
  /** The user interrupted her by typing while she spoke: once her voice stops she looks at
   * them, until she speaks again. */
  interruptedByTyping: boolean;
  /** Which of her replies in the call the subtitles are of; null until one has started. */
  shownReply: number | null;
  /** The segment she is saying, which her mood follows: the one her voice last started
   * playing, or in text only the one last shown. `over` once it has been said: her voice
   * stopped (until it starts again), or the next turn was taken up. Null until one starts. */
  saying: { reply: number; segment: number; over: boolean } | null;
};

const IDLE: Omit<Snapshot, "entries" | "line"> = {
  conversation: { status: "opening" },
  call: { phase: "idle" },
  collapsed: false,
  pickingMic: false,
  hearing: "",
  playing: null,
  micMuted: false,
  micId: "",
  micNotice: null,
  busy: false,
  draft: "",
  textOnly: false,
  failure: null,
  stand: CALM,
};

/** No one speaking in the call: the stand is as a call starts. */
const QUIET: Pick<State, "voicing" | "userSpeaking" | "interruptedByTyping" | "shownReply" | "saying" | "stand"> = {
  voicing: false,
  userSpeaking: false,
  interruptedByTyping: false,
  shownReply: null,
  saying: null,
  stand: CALM,
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
  /** How many nods she has given, to tell each one from the last. */
  private nods = 0;
  /** Emotions judged for segments she has yet to say in this call, by `reply:segment`. */
  private judged = new Map<string, SegmentEmotion>();
  /** The last segment whose emotion she has shown in this call; null until one. */
  private shown: SegmentEmotion | null = null;

  /** Opens her newest conversation, or starts one if she has none. */
  constructor(
    private readonly characterId: string,
    private readonly ports: Ports,
  ) {
    this.state = { ...IDLE, ...QUIET, log: emptyLog, callFrom: 0, textOnly: ports.preferences.load().muted };
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

  /** Leave this conversation for a new, empty one, with an empty input box. Not over a
   * text turn or a call. It is opening until the new one is started; if that fails, this
   * one stays open. */
  async startNewConversation(): Promise<void> {
    if (!this.openConversationId() || this.state.busy || isLive(this.state.call)) return;
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
      // speaks, it interrupts her, and she looks at the user as her voice stops.
      this.call.sendText(text);
      if (this.state.voicing) this.update({ interruptedByTyping: true });
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

  /** Call the character, from idle or from the end of the last call. Not over a text turn. */
  async startCall(): Promise<void> {
    const conversationId = this.openConversationId();
    if (!conversationId || this.state.busy || isLive(this.state.call)) return;
    const attempt = {};
    this.attempt = attempt;
    this.endedBy = null;
    this.update({ call: { phase: "dialing" }, playing: null, micMuted: false, failure: null });
    let started: Call;
    try {
      started = await this.ports.startCall(conversationId, this.ports.preferences.load(), {
        onEvent: (event) => this.onCallEvent(event, attempt),
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

  private onCallEvent(event: CallEvent, attempt: object): void {
    // Not from a call hung up or dropped, the stand having been cleared with it.
    const current = this.attempt === attempt && isLive(this.state.call);
    if (isSpeaking(event)) {
      if (current) this.onSpeaking(event);
      return;
    }
    if (event.type === "ended") {
      this.endedBy = backendEnd(event);
      return;
    }
    if (event.type === "emotion") {
      if (current) this.onEmotion(event);
      return;
    }
    if (event.type === "segment-playing") {
      this.update({ playing: { reply: event.reply, segment: event.segment } });
      if (current) this.startSaying(event.reply, event.segment);
      return;
    }
    if (event.type === "user") {
      const saying = this.state.saying && { ...this.state.saying, over: true };
      this.applyTurnEvent(event, { hearing: "", shownReply: event.reply ?? null, saying });
    } else if (event.type === "delta") {
      this.applyTurnEvent(event);
      // In text only, a segment is said as its first line shows.
      const { shownReply, textOnly } = this.state;
      if (current && textOnly && shownReply !== null) this.startSaying(shownReply, event.segment);
    } else if (event.type === "error")
      this.applyTurnEvent(event, { failure: { message: event.message, signedOut: false } });
    else this.applyTurnEvent(event);
  }

  /** Who is speaking, for her stand: her mouth moves with her voice; she looks at the user
   * while they speak and nods when they stop. Her voice stops at once when she is
   * interrupted, and the user who interrupted is speaking or has typed. */
  private onSpeaking({ type }: Speaking): void {
    const saying = this.state.saying;
    switch (type) {
      case "bot-started-speaking":
        return this.update({ voicing: true, interruptedByTyping: false, saying: saying && { ...saying, over: false } });
      case "bot-stopped-speaking":
        return this.update({ voicing: false, saying: saying && { ...saying, over: true } });
      case "user-started-speaking":
        return this.update({ userSpeaking: true });
      case "user-stopped-speaking":
        return this.update({ userSpeaking: false, stand: { ...this.state.stand, nod: { kind: "yes", id: ++this.nods } } });
    }
  }

  /** She starts saying segment `segment` of reply `reply`, unless she is past it already:
   * her mood follows it if it has been judged. */
  private startSaying(reply: number, segment: number): void {
    const { saying } = this.state;
    if (saying && !follows({ reply, segment }, saying)) return;
    const emotion = this.judged.get(key(reply, segment));
    for (const [k, earlier] of this.judged) if (!follows(earlier, { reply, segment })) this.judged.delete(k);
    this.update({ saying: { reply, segment, over: false } });
    if (emotion) this.showEmotion(emotion);
  }

  /** A segment's emotion is judged: kept until she says it, taken up at once while she is
   * saying it, and dropped once she has said it. In text only a segment is judged once it is
   * complete, by when the next one often shows: there it is taken up still, until the reply
   * is over, unless a later segment's emotion shows already. */
  private onEmotion(emotion: SegmentEmotion): void {
    const { saying, textOnly } = this.state;
    if (!saying || follows(emotion, saying)) {
      this.judged.set(key(emotion.reply, emotion.segment), emotion);
      return;
    }
    if (saying.over || emotion.reply !== saying.reply) return;
    const current = emotion.segment === saying.segment;
    if (current || (textOnly && (!this.shown || follows(emotion, this.shown)))) this.showEmotion(emotion);
  }

  /** Her mood follows the segment she is saying, but through a calm one it stays as it was,
   * unless the segment opens her reply; a nod or shake of the head goes with it. */
  private showEmotion(judged: SegmentEmotion): void {
    const { emotion, segment, nod } = judged;
    const { stand } = this.state;
    this.shown = judged;
    this.update({
      stand: {
        ...stand,
        mood: emotion === "calm" && segment > 0 ? stand.mood : emotion,
        nod: nod ? { kind: nod, id: ++this.nods } : stand.nod,
      },
    });
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

  /** The call is over, hung up (no `end`) or not; a reply it cut off is not recorded. */
  private ended(end: CallEnd | null): void {
    this.call = null;
    this.judged.clear();
    this.shown = null;
    this.apply(
      { type: "interrupted" },
      {
        call: end ? { phase: "ended", end } : { phase: "idle" },
        hearing: "",
        playing: null,
        micMuted: false,
        micId: "",
        micNotice: null,
        ...QUIET,
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
    this.state = withStandRules(withCallScreenRules(this.state, { ...this.state, ...change }));
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

/** Her mouth moves while her voice plays, but not in text only; she looks at the user while
 * they speak, and once her voice stops after they interrupted her by typing. The direction
 * stays the same object while nothing about it changes. */
function withStandRules(next: State): State {
  const speaking = next.voicing && !next.textOnly;
  const looking = next.userSpeaking || (next.interruptedByTyping && !next.voicing);
  if (speaking === next.stand.speaking && looking === next.stand.looking) return next;
  return { ...next, stand: { ...next.stand, speaking, looking } };
}

function key(reply: number, segment: number): string {
  return `${reply}:${segment}`;
}

/** Whether segment `a` comes after segment `b` in the call. */
function follows(a: Pick<SegmentPlaying, "reply" | "segment">, b: Pick<SegmentPlaying, "reply" | "segment">): boolean {
  return a.reply > b.reply || (a.reply === b.reply && a.segment > b.segment);
}

function isSpeaking(event: CallEvent): event is Speaking {
  return (SPEAKING as readonly string[]).includes(event.type);
}

function micInUse(mic: MicInUse): Pick<State, "micId" | "micNotice"> {
  return { micId: mic.id, micNotice: mic.fellBack ? "fell_back" : null };
}

function toSnapshot({
  log,
  callFrom,
  voicing,
  userSpeaking,
  interruptedByTyping,
  shownReply,
  saying,
  ...rest
}: State): Snapshot {
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
