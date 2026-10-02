import { describe, expect, it } from "vitest";
import { ApiError, type CallEvent, type Conversation, type Message, type TurnEvent } from "@/lib/api";
import type { Call, CallHandlers, MicInUse } from "@/lib/call";
import { MicUnavailable } from "@/lib/callEnd";
import type { CallPreferences } from "@/lib/callPreferences";
import { LiveConversation, type Ports } from "@/lib/liveConversation";
import { CALM, type Emotion } from "@/lib/standAnimations";

/** A call that has connected: records what the conversation asks of it. */
class FakeCall implements Call {
  sent: string[] = [];
  textOnly: boolean[] = [];
  micEnabled: boolean[] = [];
  hangUps = 0;
  /** What each switch asked for; the next one resolves with `switchTo`, or fails if it is null. */
  switches: string[] = [];
  switchTo: MicInUse | null = { id: "", fellBack: false };
  constructor(
    readonly maxSeconds: number | null = 1800,
    readonly exempt = false,
    readonly mic: MicInUse = { id: "", fellBack: false },
  ) {}
  switchMic = async (micId: string) => {
    this.switches.push(micId);
    if (!this.switchTo) throw new Error("could not open it");
    return this.switchTo;
  };
  sendText = (text: string) => void this.sent.push(text);
  setTextOnly = (textOnly: boolean) => void this.textOnly.push(textOnly);
  setMicEnabled = (enabled: boolean) => void this.micEnabled.push(enabled);
  hangUp = async () => void this.hangUps++;
}

/** One `startCall`: it stays dialing until the test says how it ends. */
type Attempt = {
  preferences: CallPreferences;
  handlers: CallHandlers;
  connect: (call: Call) => void;
  fail: (error: Error) => void;
};

const NOW = 1_000_000;

function record(id: string): Conversation {
  return { id, character_id: "hikari", created_at: "2026-09-27T00:00:00Z" };
}

type Options = {
  /** Her conversations, newest first; one, "c1", unless a test says otherwise. */
  conversations?: Conversation[];
  /** The messages recorded in "c1". */
  messages?: Message[];
  turns?: (text: string) => AsyncIterable<TurnEvent>;
  /** Ports a test replaces, to make opening fail or wait. */
  ports?: Partial<Ports>;
};

/** A live conversation over fake ports, not yet open: her conversations and their
 * messages, calls the test connects, scripted text turns, preferences kept in memory,
 * a clock that stands still. */
function opening(options: Options = {}) {
  const attempts: Attempt[] = [];
  const created: string[] = [];
  /** Which conversation each call and text turn went to. */
  const sentTo: string[] = [];
  let listChanged = 0;
  let stored: CallPreferences = { micId: "", quality: "standard", muted: false, phoneTexture: false };
  const ports: Ports = {
    listConversations: async () => options.conversations ?? [record("c1")],
    createConversation: async () => {
      const conversation = record(`new${created.length + 1}`);
      created.push(conversation.id);
      return conversation;
    },
    listMessages: async (conversationId) => (conversationId === "c1" ? (options.messages ?? []) : []),
    onListChanged: () => listChanged++,
    startCall: (conversationId, preferences, handlers) => {
      sentTo.push(conversationId);
      return new Promise((connect, fail) => attempts.push({ preferences, handlers, connect, fail }));
    },
    sendTurn: (conversationId, text) => {
      sentTo.push(conversationId);
      return (options.turns ?? noTurns)(text);
    },
    preferences: {
      load: () => ({ ...stored }),
      save: (change) => (stored = { ...stored, ...change }),
    },
    onCharacterAudio: () => {},
    now: () => NOW,
    ...options.ports,
  };
  const live = new LiveConversation("hikari", ports);
  let published = 0;
  live.subscribe(() => published++);
  return {
    live,
    attempts,
    created,
    sentTo,
    preferences: () => stored,
    published: () => published,
    listChanged: () => listChanged,
  };
}

/** A live conversation over fake ports, once it has opened (or failed to). */
async function conversation(options: Options = {}) {
  const opened = opening(options);
  await settled();
  return opened;
}

/** Lets every promise already settled run on. */
function settled(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

async function* noTurns(): AsyncIterable<TurnEvent> {
  throw new Error("no text turns in this test");
}

/** A text turn whose reply streams these events, then ends. */
function scripted(events: TurnEvent[]): () => AsyncIterable<TurnEvent> {
  return async function* () {
    yield* events;
  };
}

/** A promise the test settles when it is ready. */
function gate(): { gate: Promise<void>; open: () => void } {
  let open = () => {};
  const promise = new Promise<void>((resolve) => (open = resolve));
  return { gate: promise, open };
}

/** Starts a call and lets it connect. */
async function connected(
  live: LiveConversation,
  attempts: Attempt[],
  call = new FakeCall(),
): Promise<FakeCall> {
  const calling = live.startCall();
  attempts[attempts.length - 1].connect(call);
  await calling;
  return call;
}

/** Starts a call that fails to connect with `error`. */
async function failing(live: LiveConversation, attempts: Attempt[], error: Error): Promise<void> {
  const calling = live.startCall();
  attempts[attempts.length - 1].fail(error);
  await calling;
}

function message(
  id: number,
  role: Message["role"],
  text: string,
  createdAt = "2026-09-27T00:00:00Z",
): Message {
  const segments = role === "user" ? [] : [{ ja: text, zh: `（${text}）` }];
  return {
    id,
    role,
    text: role === "user" ? text : null,
    ja: role === "user" ? null : text,
    zh: role === "user" ? null : `（${text}）`,
    segments,
    created_at: createdAt,
  };
}

const history = [message(1, "user", "早上好"), message(2, "character", "おはよう")];

describe("LiveConversation: a call", () => {
  it("dials, then counts from when it connects, with the backend's time limit", async () => {
    const { live, attempts } = await conversation();
    const calling = live.startCall();
    expect(live.snapshot().call).toEqual({ phase: "dialing" });

    attempts[0].connect(new FakeCall(1800));
    await calling;

    expect(live.snapshot().call).toEqual({ phase: "connected", since: NOW, maxSeconds: 1800 });
  });

  it("goes straight back to idle when the user hangs up, taking back the reply cut off", async () => {
    const { live, attempts } = await conversation({ messages: history });
    const call = await connected(live, attempts);
    const { handlers } = attempts[0];
    handlers.onEvent({ type: "user", text: "你好" });
    handlers.onEvent({ type: "delta", segment: 0, lang: "ja", text: "こん" });
    handlers.onHearing("还有");

    await live.hangUp();

    expect(call.hangUps).toBe(1);
    expect(live.snapshot()).toMatchObject({ call: { phase: "idle" }, hearing: "", failure: null });
    expect(live.snapshot().entries.map((e) => e.key)).toEqual(["m1", "m2"]);
  });

  it("can be hung up while dialing: back to idle at once, and hung up once it connects", async () => {
    const { live, attempts } = await conversation();
    const calling = live.startCall();

    await live.hangUp();
    expect(live.snapshot().call).toEqual({ phase: "idle" });
    const call = new FakeCall();
    attempts[0].connect(call);
    await calling;

    expect(call.hangUps).toBe(1);
    expect(live.snapshot().call).toEqual({ phase: "idle" });
  });

  it("shows no end for a call hung up while dialing that then fails", async () => {
    const { live, attempts } = await conversation();
    const calling = live.startCall();
    await live.hangUp();

    attempts[0].fail(new Error("无法接通，请稍后再试"));
    await calling;

    expect(live.snapshot().call).toEqual({ phase: "idle" });
  });

  it("lets a new call be dialed after one hung up while dialing, which does not disturb it", async () => {
    const { live, attempts } = await conversation();
    const first = live.startCall();
    await live.hangUp();
    const second = live.startCall();

    attempts[0].fail(new Error("无法接通，请稍后再试"));
    await first;
    expect(live.snapshot().call).toEqual({ phase: "dialing" });
    attempts[1].connect(new FakeCall());
    await second;
    expect(live.snapshot().call.phase).toBe("connected");
  });

  it.each([
    ["the microphone is refused", new MicUnavailable("denied"), "mic_denied"],
    ["the hour's calls are used up", new ApiError("本小时的通话次数已用完", 429), "over_limit"],
    ["an own key fails", new ApiError("你的语音合成密钥调用失败", 409), "own_key"],
    ["it cannot connect", new Error("无法接通，请稍后再试"), "not_connected"],
  ])("ends saying why, and that it did not count, when %s", async (_, error, reason) => {
    const { live, attempts } = await conversation();

    await failing(live, attempts, error);

    expect(live.snapshot().call).toMatchObject({ phase: "ended", end: { reason, counts: false } });
  });

  it("ends with the backend's reason and word on the limit, taking back the reply cut off", async () => {
    const { live, attempts } = await conversation({ messages: history });
    await connected(live, attempts);
    const { handlers } = attempts[0];
    handlers.onEvent({ type: "ended", reason: "duration_limit", message: "满 30 分钟了", counts: true });
    handlers.onEvent({ type: "user", text: "你好" });
    handlers.onHearing("还有");

    handlers.onDropped();

    expect(live.snapshot()).toMatchObject({
      call: { phase: "ended", end: { reason: "duration_limit", counts: true } },
      hearing: "",
    });
    expect(live.snapshot().entries.map((e) => e.key)).toEqual(["m1", "m2"]);
  });

  it("says a call that drops with no word from the backend counted, unless it was exempt", async () => {
    const { live, attempts } = await conversation();
    await connected(live, attempts, new FakeCall(1800, false));
    attempts[0].handlers.onDropped();
    expect(live.snapshot().call).toMatchObject({ phase: "ended", end: { reason: "dropped", counts: true } });

    await connected(live, attempts, new FakeCall(1800, true));
    attempts[1].handlers.onDropped();
    expect(live.snapshot().call).toMatchObject({ phase: "ended", end: { reason: "dropped", counts: false } });
  });

  it("does not give a new call's drop the reason an earlier call was ended for", async () => {
    const { live, attempts } = await conversation();
    await connected(live, attempts);
    attempts[0].handlers.onEvent({ type: "ended", reason: "turn_limit", message: "说了 20 轮了", counts: true });
    attempts[0].handlers.onDropped();

    await connected(live, attempts);
    attempts[1].handlers.onDropped();

    expect(live.snapshot().call).toMatchObject({ phase: "ended", end: { reason: "dropped" } });
  });

  it("does not give a new call's drop the reason the last call sends too late", async () => {
    const { live, attempts } = await conversation();
    await connected(live, attempts);
    await live.hangUp();
    await connected(live, attempts);

    attempts[0].handlers.onEvent({ type: "ended", reason: "turn_limit", message: "说了 20 轮了", counts: true });
    attempts[1].handlers.onDropped();

    expect(live.snapshot().call).toMatchObject({ phase: "ended", end: { reason: "dropped" } });
  });

  it("leaves a call that drops while dialing to fail to connect", async () => {
    const { live, attempts } = await conversation();
    const calling = live.startCall();

    attempts[0].handlers.onDropped();

    expect(live.snapshot().call).toEqual({ phase: "dialing" });
    attempts[0].fail(new Error("无法接通，请稍后再试"));
    await calling;
    expect(live.snapshot().call).toMatchObject({ phase: "ended", end: { reason: "not_connected" } });
  });

  it("goes back to idle from the end, or dials again", async () => {
    const { live, attempts } = await conversation();
    await failing(live, attempts, new Error("无法接通，请稍后再试"));

    live.dismissEnd();
    expect(live.snapshot().call).toEqual({ phase: "idle" });

    await failing(live, attempts, new Error("无法接通，请稍后再试"));
    void live.startCall();
    expect(live.snapshot().call).toEqual({ phase: "dialing" });
    expect(attempts).toHaveLength(3);
  });

  it("hangs up a call that finishes connecting after the page is left", async () => {
    const { live, attempts, published } = await conversation();
    const calling = live.startCall();

    live.dispose();
    const before = published();
    const call = new FakeCall();
    attempts[0].connect(call);
    await calling;

    expect(call.hangUps).toBe(1);
    expect(published()).toBe(before);
  });

  it("shows no end for a call that fails to connect after the page is left", async () => {
    const { live, attempts } = await conversation();
    const calling = live.startCall();
    live.dispose();
    attempts[0].fail(new Error("无法接通，请稍后再试"));
    await calling;

    expect(live.snapshot().call).toEqual({ phase: "dialing" }); // as it was when the page was left
  });

  it("hangs up the call under way when the page is left", async () => {
    const { live, attempts } = await conversation();
    const call = await connected(live, attempts);

    live.dispose();

    expect(call.hangUps).toBe(1);
  });

  it("stops showing what it is hearing once the backend takes the words up", async () => {
    const { live, attempts } = await conversation();
    await connected(live, attempts);
    const { handlers } = attempts[0];
    handlers.onHearing("你好");
    expect(live.snapshot().hearing).toBe("你好");

    handlers.onEvent({ type: "user", text: "你好" });

    expect(live.snapshot().hearing).toBe("");
    expect(live.snapshot().entries.map((e) => e.kind)).toEqual(["user", "character"]);
  });

  it("shows her latest line in this call, not one from before it", async () => {
    const { live, attempts } = await conversation({ messages: history });
    await connected(live, attempts);
    expect(live.snapshot().line).toBeNull();
    const { handlers } = attempts[0];

    handlers.onEvent({ type: "user", text: "你好" });
    handlers.onEvent({ type: "delta", segment: 0, lang: "ja", text: "こんにちは" });
    expect(live.snapshot().line).toEqual({ ja: "こんにちは", zh: "" });
    handlers.onEvent({ type: "delta", segment: 0, lang: "zh", text: "你好" });
    handlers.onEvent({ type: "delta", segment: 1, lang: "ja", text: "元気？" });

    expect(live.snapshot().line).toEqual({ ja: "元気？", zh: "" });
  });

  it("shows a turn failing in a call while the call goes on", async () => {
    const { live, attempts } = await conversation({ messages: history });
    await connected(live, attempts);
    const { handlers } = attempts[0];
    handlers.onEvent({ type: "user", text: "你好" });

    handlers.onEvent({ type: "error", message: "角色暂时无法回复" });

    expect(live.snapshot()).toMatchObject({
      call: { phase: "connected" },
      failure: { message: "角色暂时无法回复", signedOut: false },
    });
    expect(live.snapshot().entries.map((e) => e.key)).toEqual(["m1", "m2"]);
  });

  it("clears the last failure when a call starts", async () => {
    const { live } = await conversation({
      turns: async function* (): AsyncIterable<TurnEvent> {
        throw new ApiError("本小时的对话次数已用完", 429);
      },
    });
    live.setDraft("你好");
    await live.submit();
    expect(live.snapshot().failure).not.toBeNull();

    void live.startCall();

    expect(live.snapshot().failure).toBeNull();
  });
});

describe("LiveConversation: a call that is over", () => {
  /** How the first call ends, its turn under way; after that its messages come too late. */
  const endings: [string, (live: LiveConversation, attempts: Attempt[]) => Promise<void>][] = [
    ["the user hangs up", (live) => live.hangUp()],
    ["it drops", async (_live, attempts) => attempts[0].handlers.onDropped()],
    [
      "the backend says why, then it drops",
      async (_live, attempts) => {
        attempts[0].handlers.onEvent({ type: "ended", reason: "turn_limit", message: "说了 20 轮了", counts: true });
        attempts[0].handlers.onDropped();
      },
    ],
    [
      "the next call has connected",
      async (live, attempts) => {
        await live.hangUp();
        await connected(live, attempts);
        const next = attempts[1].handlers;
        next.onEvent({ type: "user", text: "再说一次" });
        next.onEvent({ type: "delta", segment: 0, lang: "ja", text: "もう" });
        next.onEvent({ type: "bot-started-speaking" });
        next.onHearing("还有");
        // 下一通进行中的回合：迟到的消息不能撤掉它。
        expect(live.snapshot().entries.at(-1)).toMatchObject({ kind: "character", pending: true });
      },
    ],
  ];

  /** What comes too late from the first call. */
  const late: [string, (handlers: CallHandlers) => void][] = [
    ["what the user said", (h) => h.onEvent({ type: "user", text: "迟到的话" })],
    ["a delta of the reply", (h) => h.onEvent({ type: "delta", segment: 0, lang: "ja", text: "おそい" })],
    ["the reply recorded", (h) => h.onEvent({ type: "done", message: message(9, "character", "おそい") })],
    ["an error", (h) => h.onEvent({ type: "error", message: "角色暂时无法回复" })],
    [
      "the backend saying why it hangs up",
      (h) => h.onEvent({ type: "ended", reason: "duration_limit", message: "满 30 分钟了", counts: true }),
    ],
    ["what the user is saying so far", (h) => h.onHearing("迟到的转写")],
    ["the microphone lost", (h) => h.onMicLost(null)],
    ["the call dropping", (h) => h.onDropped()],
    ["an event only her stand follows", (h) => h.onEvent({ type: "bot-started-speaking" })],
  ];

  it.each(endings.flatMap(([ending, end]) => late.map(([what, send]) => [ending, what, end, send] as const)))(
    "once %s, changes nothing by %s",
    async (_ending, _what, end, send) => {
      const { live, attempts, listChanged } = await conversation({ messages: history });
      await connected(live, attempts);
      const { handlers } = attempts[0];
      handlers.onEvent({ type: "user", text: "你好" });
      handlers.onEvent({ type: "delta", segment: 0, lang: "ja", text: "こん" });
      await end(live, attempts);
      const before = live.snapshot();
      const told = listChanged();

      send(handlers);

      expect(live.snapshot()).toEqual(before);
      expect(listChanged()).toBe(told);
    },
  );
});

describe("LiveConversation: mic mute", () => {
  it("turns the microphone off and on in the browser only", async () => {
    const { live, attempts } = await conversation();
    const call = await connected(live, attempts);

    live.toggleMic();
    expect(live.snapshot().micMuted).toBe(true);
    live.toggleMic();

    expect(live.snapshot().micMuted).toBe(false);
    expect(call.micEnabled).toEqual([false, true]);
    expect(call.textOnly).toEqual([]);
  });

  it("still sends what is typed while the microphone is muted", async () => {
    // CONTEXT.md「麦克风静音」：打字不受影响。
    const { live, attempts } = await conversation();
    const call = await connected(live, attempts);
    live.toggleMic();
    live.setDraft("你好");

    await live.submit();

    expect(call.sent).toEqual(["你好"]);
  });

  it("starts each call with the microphone on", async () => {
    const { live, attempts } = await conversation();
    await connected(live, attempts);
    live.toggleMic();
    await live.hangUp();

    await connected(live, attempts);

    expect(live.snapshot().micMuted).toBe(false);
  });

  it("does nothing until the call has connected", async () => {
    const { live } = await conversation();
    void live.startCall();

    live.toggleMic();

    expect(live.snapshot().micMuted).toBe(false);
  });
});

describe("LiveConversation: switching the microphone", () => {
  it("switches the call to the chosen microphone, which becomes the default for later calls", async () => {
    const { live, attempts, preferences } = await conversation();
    const call = await connected(live, attempts);
    call.switchTo = { id: "usb", fellBack: false };

    await live.switchMic("usb");

    expect(call.switches).toEqual(["usb"]);
    expect(call.hangUps).toBe(0);
    expect(live.snapshot().micId).toBe("usb");
    expect(preferences().micId).toBe("usb");
  });

  it("keeps the microphone muted across a switch", async () => {
    const { live, attempts } = await conversation();
    await connected(live, attempts);
    live.toggleMic();

    await live.switchMic("usb");

    expect(live.snapshot().micMuted).toBe(true);
  });

  it("starts a call on the default microphone, saying which one is in use", async () => {
    const { live, attempts } = await conversation();
    const calling = live.startCall();
    attempts[0].connect(new FakeCall(1800, false, { id: "usb", fellBack: false }));
    await calling;

    expect(attempts[0].preferences.micId).toBe("");
    expect(live.snapshot().micId).toBe("usb");
    expect(live.snapshot().micNotice).toBeNull();
  });

  it("says so when the default microphone is gone and the system default is used", async () => {
    const { live, attempts, preferences } = await conversation();
    await connected(live, attempts, new FakeCall(1800, false, { id: "", fellBack: true }));

    expect(live.snapshot().micId).toBe("");
    expect(live.snapshot().micNotice).toBe("fell_back");
    // Kept: plugged back in, it is used again.
    expect(preferences().micId).toBe("");
  });

  it("says so when the microphone in use is unplugged during the call", async () => {
    const { live, attempts } = await conversation();
    const call = new FakeCall(1800, false, { id: "usb", fellBack: false });
    await connected(live, attempts, call);

    attempts[0].handlers.onMicLost({ id: "", fellBack: true });

    expect(live.snapshot().micId).toBe("");
    expect(live.snapshot().micNotice).toBe("fell_back");
    expect(call.hangUps).toBe(0);
  });

  it("says so when the microphone is unplugged and no other one opens, keeping the call", async () => {
    const { live, attempts } = await conversation();
    const call = await connected(live, attempts, new FakeCall(1800, false, { id: "usb", fellBack: false }));

    attempts[0].handlers.onMicLost(null);

    expect(live.snapshot().micNotice).toBe("lost");
    expect(live.snapshot().call.phase).toBe("connected");
    expect(call.hangUps).toBe(0);
  });

  it("keeps the microphone in use when the chosen one cannot be opened", async () => {
    const { live, attempts, preferences } = await conversation();
    const call = await connected(live, attempts, new FakeCall(1800, false, { id: "usb", fellBack: false }));
    call.switchTo = null;

    await live.switchMic("broken");

    expect(live.snapshot().micId).toBe("usb");
    expect(live.snapshot().micNotice).toBe("unavailable");
    expect(preferences().micId).toBe("");
  });

  it("clears the notice after a switch that works, and when the call is over", async () => {
    const { live, attempts } = await conversation();
    const call = await connected(live, attempts, new FakeCall(1800, false, { id: "", fellBack: true }));
    call.switchTo = { id: "usb", fellBack: false };

    await live.switchMic("usb");
    expect(live.snapshot().micNotice).toBeNull();

    attempts[0].handlers.onMicLost({ id: "", fellBack: true });
    await live.hangUp();
    expect(live.snapshot().micNotice).toBeNull();
  });

  it("does nothing until the call has connected", async () => {
    const { live, preferences } = await conversation();
    void live.startCall();

    await live.switchMic("usb");

    expect(preferences().micId).toBe("");
  });

  it("does not show a switch that finishes after the call is over", async () => {
    const { live, attempts } = await conversation();
    const call = await connected(live, attempts);
    call.switchTo = { id: "usb", fellBack: false };

    const switching = live.switchMic("usb");
    await live.hangUp();
    await switching;

    expect(live.snapshot().call.phase).toBe("idle");
    expect(live.snapshot().micId).toBe("");
  });
});

describe("LiveConversation: text only", () => {
  it("keeps the switch in the preferences and tells the call under way", async () => {
    const { live, attempts, preferences } = await conversation();
    const call = await connected(live, attempts);

    live.toggleTextOnly();

    expect(live.snapshot().textOnly).toBe(true);
    expect(preferences().muted).toBe(true);
    expect(call.textOnly).toEqual([true]);
  });

  it("starts a call with the switch as it is", async () => {
    const { live, attempts } = await conversation();
    live.toggleTextOnly();

    void live.startCall();

    expect(attempts[0].preferences.muted).toBe(true);
  });
});

describe("LiveConversation: typing", () => {
  it("keeps the draft within the 2000 characters the backend accepts", async () => {
    const { live } = await conversation();

    live.setDraft("あ".repeat(2005));

    expect(live.snapshot().draft).toBe("あ".repeat(2000));
  });

  it("records a text turn the backend answers", async () => {
    const { live } = await conversation({
      messages: history,
      turns: scripted([
        { type: "user", text: "你好" },
        { type: "delta", segment: 0, lang: "ja", text: "こんにちは" },
        { type: "done", message: message(4, "character", "こんにちは") },
      ]),
    });
    live.setDraft(" 你好 ");

    await live.submit();

    expect(live.snapshot()).toMatchObject({ draft: "", busy: false, failure: null });
    expect(live.snapshot().entries.at(-1)).toEqual({
      kind: "character",
      key: "m4",
      segments: [{ ja: "こんにちは", zh: "（こんにちは）" }],
      pending: false,
      at: "2026-09-27T00:00:00Z",
    });
  });

  it.each([
    [
      "the backend says it failed",
      scripted([
        { type: "user", text: "你好" },
        { type: "error", message: "角色暂时无法回复" },
      ]),
      "角色暂时无法回复",
    ],
    [
      "the reply stops without being done",
      scripted([
        { type: "user", text: "你好" },
        { type: "delta", segment: 0, lang: "ja", text: "こん" },
      ]),
      "回复中断了，请再试一次",
    ],
    [
      "the request fails",
      async function* (): AsyncIterable<TurnEvent> {
        throw new ApiError("本小时的对话次数已用完", 429);
      },
      "本小时的对话次数已用完",
    ],
  ])("takes back a text turn and returns the text to the input when %s", async (_, turns, why) => {
    const { live } = await conversation({ messages: history, turns });
    live.setDraft("你好");

    await live.submit();

    expect(live.snapshot()).toMatchObject({
      draft: "你好",
      busy: false,
      failure: { message: why, signedOut: false },
    });
    expect(live.snapshot().entries.map((e) => e.key)).toEqual(["m1", "m2"]);
  });

  it.each([
    [
      "the backend says it failed",
      scripted([
        { type: "user", text: "你好" },
        { type: "error", message: "你的 LLM 密钥调用失败：401" },
      ]),
    ],
    [
      "the request is refused",
      async function* (): AsyncIterable<TurnEvent> {
        throw new ApiError("本小时的对话次数已用完", 429);
      },
    ],
  ])("says a text turn does not count towards the limit when %s", async (_, turns) => {
    // CONTEXT.md「限额」「回合」：失败的回合和被拒绝的回合都不计入限额。
    const { live } = await conversation({ messages: history, turns });
    live.setDraft("你好");

    await live.submit();

    expect(live.snapshot().failure?.countsTowardLimit).toBe(false);
  });

  it("does not say whether a text turn counts when its reply just stops", async () => {
    // 连接断了，前端分不清是服务出错还是回复其实已经记下，所以不下结论。
    const { live } = await conversation({
      messages: history,
      turns: scripted([{ type: "user", text: "你好" }]),
    });
    live.setDraft("你好");

    await live.submit();

    expect(live.snapshot().failure).not.toBeNull();
    expect(live.snapshot().failure?.countsTowardLimit).toBeUndefined();
  });

  it("hands what the user types in a call to the call instead of starting a text turn", async () => {
    const { live, attempts } = await conversation({ messages: history });
    const call = await connected(live, attempts);
    live.setDraft("你好");

    await live.submit();

    expect(call.sent).toEqual(["你好"]);
    expect(live.snapshot()).toMatchObject({ draft: "", busy: false });
    expect(live.snapshot().entries.map((e) => e.key)).toEqual(["m1", "m2"]);
  });

  it("sends nothing while a call is dialing, keeping the text in the input", async () => {
    const turns: string[] = [];
    const { live, attempts } = await conversation({
      turns: (text) => {
        turns.push(text);
        return scripted([])();
      },
    });
    const calling = live.startCall();
    live.setDraft("你好");

    await live.submit();
    const call = new FakeCall();
    attempts[0].connect(call);
    await calling;

    expect(turns).toEqual([]);
    expect(call.sent).toEqual([]);
    expect(live.snapshot().draft).toBe("你好");
  });

  it("starts no call while a text turn is under way", async () => {
    const { gate: answered, open: answer } = gate();
    const { live, attempts } = await conversation({
      turns: async function* () {
        yield { type: "user", text: "你好" };
        await answered;
        yield { type: "done", message: message(4, "character", "こんにちは") };
      },
    });
    live.setDraft("你好");
    const sending = live.submit();

    await live.startCall();
    answer();
    await sending;

    expect(attempts).toEqual([]);
    expect(live.snapshot().call).toEqual({ phase: "idle" });
  });

  it("lets a text turn under way finish when the page is left, showing no more of it", async () => {
    const { gate: answered, open: answer } = gate();
    let finished = false;
    const { live, published } = await conversation({
      turns: async function* () {
        yield { type: "user", text: "你好" };
        await answered;
        yield { type: "done", message: message(4, "character", "こんにちは") };
        finished = true;
      },
    });
    live.setDraft("你好");
    const sending = live.submit();

    live.dispose();
    const before = published();
    answer();
    await sending;

    expect(finished).toBe(true);
    expect(published()).toBe(before);
  });
});

describe("LiveConversation: opening", () => {
  it("opens her newest conversation with its messages, leaving the list alone", async () => {
    const { live, listChanged, sentTo } = opening({
      conversations: [record("c1"), record("c0")],
      messages: history,
      turns: scripted([]),
    });
    expect(live.snapshot().conversation).toEqual({ status: "opening" });

    await settled();

    expect(live.snapshot()).toMatchObject({ conversation: { status: "open" }, failure: null });
    expect(live.snapshot().entries.map((e) => e.key)).toEqual(["m1", "m2"]);
    expect(listChanged()).toBe(0);
    live.setDraft("你好");
    await live.submit();
    expect(sentTo).toEqual(["c1"]);
  });

  it("starts a conversation when she has none, which the list then shows", async () => {
    const { live, created, listChanged, sentTo } = await conversation({
      conversations: [],
      turns: scripted([]),
    });

    expect(created).toEqual(["new1"]);
    expect(listChanged()).toBe(1);
    expect(live.snapshot()).toMatchObject({ conversation: { status: "open" }, entries: [] });
    live.setDraft("你好");
    await live.submit();
    expect(sentTo).toEqual(["new1"]);
  });

  it.each([
    ["it cannot be reached", new Error("Failed to fetch"), false],
    ["the browser is signed out", new ApiError("请先登录", 401), true],
  ])("says why it could not open when %s", async (_, error, signedOut) => {
    const { live } = await conversation({
      ports: {
        listConversations: async () => {
          throw error;
        },
      },
    });

    expect(live.snapshot()).toMatchObject({
      conversation: { status: "failed", failure: { message: error.message, signedOut } },
      // Not an error of the conversation open: that one has none.
      failure: null,
    });
  });

  it("sends nothing and dials nothing before it is open", async () => {
    const { gate: listed, open: list } = gate();
    const { live, attempts, sentTo } = opening({
      ports: {
        listConversations: async () => {
          await listed;
          return [record("c1")];
        },
      },
    });

    live.setDraft("你好");
    await live.submit();
    await live.startCall();

    expect(sentTo).toEqual([]);
    expect(attempts).toEqual([]);
    expect(live.snapshot().call).toEqual({ phase: "idle" });
    list();
  });

  it("shows nothing more once the page is left while it is opening", async () => {
    const { gate: listed, open: list } = gate();
    const { live, published } = opening({
      messages: history,
      ports: {
        listConversations: async () => {
          await listed;
          return [record("c1")];
        },
      },
    });

    live.dispose();
    const before = published();
    list();
    await settled();

    expect(published()).toBe(before);
    expect(live.snapshot().conversation).toEqual({ status: "opening" });
  });

  it("still tells the list about a conversation it started when the page is left meanwhile", async () => {
    // 对话已经在后端建好了，列表里她那一行应该跟着变；页面上不再有任何更新。
    const { gate: made, open: make } = gate();
    let creating = 0;
    const { live, published, listChanged } = opening({
      conversations: [],
      ports: {
        createConversation: async () => {
          creating++;
          await made;
          return record("new1");
        },
      },
    });
    await settled();
    expect(creating).toBe(1);

    live.dispose();
    const before = published();
    make();
    await settled();

    expect(listChanged()).toBe(1);
    expect(published()).toBe(before);
  });

  it("starts no conversation once the page is left before her conversations are listed", async () => {
    const { gate: listed, open: list } = gate();
    const { live, created, listChanged } = opening({
      ports: {
        listConversations: async () => {
          await listed;
          return [];
        },
      },
    });

    live.dispose();
    list();
    await settled();

    expect(created).toEqual([]);
    expect(listChanged()).toBe(0);
  });
});

describe("LiveConversation: a new conversation", () => {
  it("starts a new conversation with an empty log, which the list then shows", async () => {
    const { live, created, listChanged, sentTo } = await conversation({
      messages: history,
      turns: scripted([]),
    });

    await live.startNewConversation();

    expect(created).toEqual(["new1"]);
    expect(live.snapshot()).toMatchObject({ conversation: { status: "open" }, entries: [], failure: null });
    expect(listChanged()).toBe(1);
    live.setDraft("你好");
    await live.submit();
    expect(sentTo).toEqual(["new1"]);
  });

  it("clears the input box for the new conversation", async () => {
    const { live } = await conversation({ messages: history });
    live.setDraft("还没发出去的话");

    await live.startNewConversation();

    expect(live.snapshot().draft).toBe("");
  });

  it("is opening again while the new conversation is started, sending and dialing nothing", async () => {
    const { gate: made, open: make } = gate();
    const { live, attempts, sentTo } = await conversation({
      messages: history,
      turns: scripted([]),
      ports: {
        createConversation: async () => {
          await made;
          return record("new1");
        },
      },
    });

    const starting = live.startNewConversation();
    expect(live.snapshot().conversation).toEqual({ status: "opening" });
    live.setDraft("你好");
    await live.submit();
    await live.startCall();
    expect(sentTo).toEqual([]);
    expect(attempts).toEqual([]);

    make();
    await starting;
    expect(live.snapshot().conversation).toEqual({ status: "open" });
  });

  it("counts her lines in a call from the start of the new conversation", async () => {
    const { live, attempts } = await conversation({ messages: history });
    await live.startNewConversation();
    await connected(live, attempts);

    attempts[0].handlers.onEvent({ type: "user", text: "你好" });
    attempts[0].handlers.onEvent({ type: "delta", segment: 0, lang: "ja", text: "こんにちは" });

    expect(live.snapshot().line).toEqual({ ja: "こんにちは", zh: "" });
  });

  it("keeps the conversation open and says why when a new one cannot be started", async () => {
    const { live, listChanged } = await conversation({
      messages: history,
      ports: {
        createConversation: async () => {
          throw new Error("Failed to fetch");
        },
      },
    });

    live.setDraft("你好");
    await live.startNewConversation();

    expect(live.snapshot()).toMatchObject({
      conversation: { status: "open" },
      draft: "你好",
      failure: { message: "Failed to fetch", signedOut: false },
    });
    expect(live.snapshot().entries.map((e) => e.key)).toEqual(["m1", "m2"]);
    expect(listChanged()).toBe(0);
  });

  it("does not start one over a text turn or a call", async () => {
    const { gate: answered, open: answer } = gate();
    const { live, attempts, created } = await conversation({
      turns: async function* () {
        yield { type: "user", text: "你好" };
        await answered;
        yield { type: "done", message: message(4, "character", "こんにちは") };
      },
    });
    live.setDraft("你好");
    const sending = live.submit();
    await live.startNewConversation();
    answer();
    await sending;

    await connected(live, attempts);
    await live.startNewConversation();

    expect(created).toEqual([]);
  });
});

describe("LiveConversation: the list", () => {
  it("is told once a text turn is recorded, not when it is sent", async () => {
    const { gate: answered, open: answer } = gate();
    const { live, listChanged } = await conversation({
      turns: async function* () {
        yield { type: "user", text: "你好" };
        yield { type: "delta", segment: 0, lang: "ja", text: "こん" };
        await answered;
        yield { type: "done", message: message(4, "character", "こんにちは") };
      },
    });
    live.setDraft("你好");

    const sending = live.submit();
    await settled();
    expect(listChanged()).toBe(0);
    answer();
    await sending;

    expect(listChanged()).toBe(1);
  });

  it("is told once for each turn recorded in a call", async () => {
    const { live, attempts, listChanged } = await conversation();
    await connected(live, attempts);
    const { handlers } = attempts[0];

    handlers.onEvent({ type: "user", text: "你好" });
    handlers.onEvent({ type: "delta", segment: 0, lang: "ja", text: "こん" });
    expect(listChanged()).toBe(0);
    handlers.onEvent({ type: "done", message: message(4, "character", "こんにちは") });

    expect(listChanged()).toBe(1);
  });

  it.each([
    [
      "the backend says it failed",
      scripted([
        { type: "user", text: "你好" },
        { type: "error", message: "角色暂时无法回复" },
      ]),
    ],
    ["the reply stops without being done", scripted([{ type: "user", text: "你好" }])],
    [
      "the request fails",
      async function* (): AsyncIterable<TurnEvent> {
        throw new ApiError("本小时的对话次数已用完", 429);
      },
    ],
  ])("is not told about a text turn taken back when %s", async (_, turns) => {
    const { live, listChanged } = await conversation({ turns });
    live.setDraft("你好");

    await live.submit();

    expect(listChanged()).toBe(0);
  });

  it("is not told about a turn in a call that fails or is cut off", async () => {
    const { live, attempts, listChanged } = await conversation();
    await connected(live, attempts);
    const { handlers } = attempts[0];
    handlers.onEvent({ type: "user", text: "你好" });
    handlers.onEvent({ type: "error", message: "角色暂时无法回复" });
    handlers.onEvent({ type: "user", text: "你好" });
    handlers.onEvent({ type: "delta", segment: 0, lang: "ja", text: "こん" });

    await live.hangUp();

    expect(listChanged()).toBe(0);
  });
});

describe("LiveConversation: times", () => {
  it("dates the user's words when they are sent and the reply when the backend recorded it", async () => {
    const { live } = await conversation({
      messages: history,
      turns: scripted([
        { type: "user", text: "你好" },
        { type: "delta", segment: 0, lang: "ja", text: "こん" },
        { type: "done", message: message(4, "character", "こんにちは", "2026-09-28T08:49:00Z") },
      ]),
    });
    live.setDraft("你好");

    await live.submit();

    expect(live.snapshot().entries.map((e) => e.at)).toEqual([
      "2026-09-27T00:00:00Z",
      "2026-09-27T00:00:00Z",
      new Date(NOW).toISOString(),
      "2026-09-28T08:49:00Z",
    ]);
  });

  it("dates what the user says in a call when the backend takes it up", async () => {
    const { live, attempts } = await conversation();
    await connected(live, attempts);

    attempts[0].handlers.onEvent({ type: "user", text: "你好" });

    expect(live.snapshot().entries[0].at).toBe(new Date(NOW).toISOString());
  });
});

describe("LiveConversation: the call layer", () => {
  it("opens up again when the call ends while it is collapsed", async () => {
    const { live, attempts } = await conversation();
    await connected(live, attempts);
    live.collapse();
    expect(live.snapshot().collapsed).toBe(true);

    attempts[0].handlers.onDropped();

    expect(live.snapshot()).toMatchObject({ call: { phase: "ended" }, collapsed: false });
  });

  it("opens up when dialing again, clearing the last failure", async () => {
    const { live, attempts } = await conversation({
      turns: async function* (): AsyncIterable<TurnEvent> {
        throw new ApiError("本小时的对话次数已用完", 429);
      },
    });
    await connected(live, attempts);
    live.collapse();
    await live.hangUp();
    live.setDraft("你好");
    await live.submit();
    expect(live.snapshot()).toMatchObject({ collapsed: true, failure: { signedOut: false } });

    void live.startCall();

    expect(live.snapshot()).toMatchObject({ call: { phase: "dialing" }, collapsed: false, failure: null });
  });

  it("collapses and expands on request, only while a call is under way", async () => {
    const { live, attempts } = await conversation();
    live.collapse();
    expect(live.snapshot().collapsed).toBe(false);

    await connected(live, attempts);
    live.collapse();
    expect(live.snapshot().collapsed).toBe(true);
    live.expand();
    expect(live.snapshot().collapsed).toBe(false);
  });
});

describe("LiveConversation: the microphone list", () => {
  it("opens and closes while the call is connected", async () => {
    const { live, attempts } = await conversation();
    await connected(live, attempts);

    live.openMicPicker();
    expect(live.snapshot().pickingMic).toBe(true);
    live.closeMicPicker();
    expect(live.snapshot().pickingMic).toBe(false);
  });

  it("does not open until the call has connected", async () => {
    const { live } = await conversation();
    void live.startCall();

    live.openMicPicker();

    expect(live.snapshot().pickingMic).toBe(false);
  });

  it.each([
    ["drops", (_live: LiveConversation, attempts: Attempt[]) => attempts[0].handlers.onDropped()],
    ["is hung up", (live: LiveConversation) => live.hangUp()],
  ])("closes when the call %s", async (_, end) => {
    const { live, attempts } = await conversation();
    await connected(live, attempts);
    live.openMicPicker();

    await end(live, attempts);

    expect(live.snapshot().pickingMic).toBe(false);
  });
});

// How she looks is ruled in `standDirection.test.ts`; these show the call moving it on.
describe("LiveConversation: the stand", () => {
  it("keeps her mouth shut in text only, even when switched on while she speaks", async () => {
    const { live, attempts } = await conversation();
    live.toggleTextOnly();
    await connected(live, attempts);
    const { handlers } = attempts[0];

    handlers.onEvent({ type: "bot-started-speaking" });
    expect(live.snapshot().stand.speaking).toBe(false);

    live.toggleTextOnly();
    handlers.onEvent({ type: "bot-started-speaking" });
    expect(live.snapshot().stand.speaking).toBe(true);
    live.toggleTextOnly();
    expect(live.snapshot().stand.speaking).toBe(false);
  });

  it("keeps her mouth shut from the first call when text only was on already", async () => {
    const saved: CallPreferences = { micId: "", quality: "standard", muted: true, phoneTexture: false };
    const { live, attempts } = await conversation({
      ports: { preferences: { load: () => saved, save: (change) => ({ ...saved, ...change }) } },
    });
    await connected(live, attempts);

    attempts[0].handlers.onEvent({ type: "bot-started-speaking" });

    expect(live.snapshot()).toMatchObject({ textOnly: true, stand: { speaking: false } });
  });

  it("looks at the user who interrupts by typing once her voice stops, until she speaks again", async () => {
    const { live, attempts } = await conversation();
    const call = await connected(live, attempts);
    const { handlers } = attempts[0];
    handlers.onEvent({ type: "bot-started-speaking" });

    live.setDraft("等一下");
    await live.submit();
    expect(call.sent).toEqual(["等一下"]);
    expect(live.snapshot().stand).toMatchObject({ speaking: true, looking: false });
    handlers.onEvent({ type: "bot-stopped-speaking" });

    expect(live.snapshot().stand).toMatchObject({ mood: "calm", speaking: false, looking: true });
    handlers.onEvent({ type: "bot-started-speaking" });
    expect(live.snapshot().stand).toMatchObject({ speaking: true, looking: false });
  });

  it("keeps following the call while the call layer is collapsed", async () => {
    const { live, attempts } = await conversation();
    await connected(live, attempts);
    live.collapse();

    attempts[0].handlers.onEvent({ type: "bot-started-speaking" });

    expect(live.snapshot().stand.speaking).toBe(true);
  });

  it.each([
    ["is hung up", (live: LiveConversation) => live.hangUp()],
    ["drops", (_live: LiveConversation, attempts: Attempt[]) => attempts[0].handlers.onDropped()],
  ])("is cleared when the call %s, the next call starting calm", async (_, end) => {
    const { live, attempts } = await conversation();
    await connected(live, attempts);
    const { handlers } = attempts[0];
    handlers.onEvent({ type: "bot-started-speaking" });
    handlers.onEvent({ type: "user-started-speaking" });
    handlers.onEvent({ type: "user-stopped-speaking" });
    handlers.onEvent({ type: "user-started-speaking" });

    await end(live, attempts);
    expect(live.snapshot().stand).toEqual(CALM);

    await connected(live, attempts);
    expect(live.snapshot().stand).toEqual(CALM);
  });
});

describe("LiveConversation: her emotions", () => {
  /** The judged emotion of segment `segment` of reply `reply`, with a nod if given. */
  function emotion(reply: number, segment: number, feeling: Emotion, nod: "yes" | "no" | null = null): CallEvent {
    return { type: "emotion", reply, segment, emotion: feeling, nod };
  }

  function playing(reply: number, segment: number): CallEvent {
    return { type: "segment-playing", reply, segment };
  }

  /** A call under way with her voice, as reply `reply` starts; `emit` sends it events. */
  async function voiced(options: { textOnly?: boolean } = {}) {
    const opened = await conversation();
    if (options.textOnly) opened.live.toggleTextOnly();
    await connected(opened.live, opened.attempts);
    const emit = (...events: CallEvent[]) => events.forEach((event) => opened.attempts[0].handlers.onEvent(event));
    const mood = () => opened.live.snapshot().stand.mood;
    return { ...opened, emit, mood };
  }

  function reply(number: number): CallEvent {
    return { type: "user", text: "你好", reply: number };
  }

  function subtitle(segment: number, text = "こんにちは"): CallEvent {
    return { type: "delta", segment, lang: "ja", text };
  }

  it("changes as her voice starts playing the segment, not before", async () => {
    const { emit, mood } = await voiced();
    emit(reply(1), subtitle(0), emotion(1, 0, "happy"));
    expect(mood()).toBe("calm");

    emit(playing(1, 0));

    expect(mood()).toBe("happy");
  });

  it("changes as each segment's first subtitle shows in text only", async () => {
    const { emit, mood } = await voiced({ textOnly: true });
    emit(reply(1), emotion(1, 0, "surprised"));
    expect(mood()).toBe("calm");

    emit(subtitle(0));
    expect(mood()).toBe("surprised");
    emit(subtitle(0, "！"), { type: "delta", segment: 0, lang: "zh", text: "你好" }, subtitle(1));
    emit(emotion(1, 1, "thinking")); // judged once the segment is complete: after it shows
    expect(mood()).toBe("thinking");

    emit(reply(2), emotion(1, 1, "angry")); // the last reply's, once the next is under way
    expect(mood()).toBe("thinking");
  });
});
