import { describe, expect, it } from "vitest";
import { ApiError, type Message, type TurnEvent } from "@/lib/api";
import type { Call, CallHandlers, MicInUse } from "@/lib/call";
import { MicUnavailable } from "@/lib/callEnd";
import type { CallPreferences } from "@/lib/callPreferences";
import { LiveConversation, type Ports } from "@/lib/liveConversation";

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

/** A live conversation over fake ports: calls the test connects, scripted text turns,
 * preferences kept in memory, a clock that stands still. */
function conversation(
  options: { messages?: Message[]; turns?: (text: string) => AsyncIterable<TurnEvent> } = {},
) {
  const attempts: Attempt[] = [];
  let stored: CallPreferences = { micId: "", quality: "standard", muted: false };
  const ports: Ports = {
    startCall: (_conversationId, preferences, handlers) =>
      new Promise((connect, fail) => attempts.push({ preferences, handlers, connect, fail })),
    sendTurn: (_conversationId, text) => (options.turns ?? noTurns)(text),
    preferences: {
      load: () => ({ ...stored }),
      save: (change) => (stored = { ...stored, ...change }),
    },
    onCharacterAudio: () => {},
    now: () => NOW,
  };
  const live = new LiveConversation("c1", options.messages ?? [], ports);
  let published = 0;
  live.subscribe(() => published++);
  return {
    live,
    attempts,
    preferences: () => stored,
    published: () => published,
  };
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

function message(id: number, role: Message["role"], text: string): Message {
  const segments = role === "user" ? [] : [{ ja: text, zh: `（${text}）` }];
  return {
    id,
    role,
    text: role === "user" ? text : null,
    ja: role === "user" ? null : text,
    zh: role === "user" ? null : `（${text}）`,
    segments,
    created_at: "2026-09-27T00:00:00Z",
  };
}

const history = [message(1, "user", "早上好"), message(2, "character", "おはよう")];

describe("LiveConversation: a call", () => {
  it("dials, then counts from when it connects, with the backend's time limit", async () => {
    const { live, attempts } = conversation();
    const calling = live.startCall();
    expect(live.snapshot().call).toEqual({ phase: "dialing" });

    attempts[0].connect(new FakeCall(1800));
    await calling;

    expect(live.snapshot().call).toEqual({ phase: "connected", since: NOW, maxSeconds: 1800 });
  });

  it("goes straight back to idle when the user hangs up, taking back the reply cut off", async () => {
    const { live, attempts } = conversation({ messages: history });
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
    const { live, attempts } = conversation();
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
    const { live, attempts } = conversation();
    const calling = live.startCall();
    await live.hangUp();

    attempts[0].fail(new Error("无法接通，请稍后再试"));
    await calling;

    expect(live.snapshot().call).toEqual({ phase: "idle" });
  });

  it("lets a new call be dialed after one hung up while dialing, which does not disturb it", async () => {
    const { live, attempts } = conversation();
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
    const { live, attempts } = conversation();

    await failing(live, attempts, error);

    expect(live.snapshot().call).toMatchObject({ phase: "ended", end: { reason, counts: false } });
  });

  it("ends with the backend's reason and word on the limit, taking back the reply cut off", async () => {
    const { live, attempts } = conversation({ messages: history });
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
    const { live, attempts } = conversation();
    await connected(live, attempts, new FakeCall(1800, false));
    attempts[0].handlers.onDropped();
    expect(live.snapshot().call).toMatchObject({ phase: "ended", end: { reason: "dropped", counts: true } });

    await connected(live, attempts, new FakeCall(1800, true));
    attempts[1].handlers.onDropped();
    expect(live.snapshot().call).toMatchObject({ phase: "ended", end: { reason: "dropped", counts: false } });
  });

  it("does not give a new call's drop the reason an earlier call was ended for", async () => {
    const { live, attempts } = conversation();
    await connected(live, attempts);
    attempts[0].handlers.onEvent({ type: "ended", reason: "turn_limit", message: "说了 20 轮了", counts: true });
    attempts[0].handlers.onDropped();

    await connected(live, attempts);
    attempts[1].handlers.onDropped();

    expect(live.snapshot().call).toMatchObject({ phase: "ended", end: { reason: "dropped" } });
  });

  it("leaves a call that drops while dialing to fail to connect", async () => {
    const { live, attempts } = conversation();
    const calling = live.startCall();

    attempts[0].handlers.onDropped();

    expect(live.snapshot().call).toEqual({ phase: "dialing" });
    attempts[0].fail(new Error("无法接通，请稍后再试"));
    await calling;
    expect(live.snapshot().call).toMatchObject({ phase: "ended", end: { reason: "not_connected" } });
  });

  it("goes back to idle from the end, or dials again", async () => {
    const { live, attempts } = conversation();
    await failing(live, attempts, new Error("无法接通，请稍后再试"));

    live.dismissEnd();
    expect(live.snapshot().call).toEqual({ phase: "idle" });

    await failing(live, attempts, new Error("无法接通，请稍后再试"));
    void live.startCall();
    expect(live.snapshot().call).toEqual({ phase: "dialing" });
    expect(attempts).toHaveLength(3);
  });

  it("hangs up a call that finishes connecting after the page is left", async () => {
    const { live, attempts, published } = conversation();
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
    const { live, attempts } = conversation();
    const calling = live.startCall();
    live.dispose();
    attempts[0].fail(new Error("无法接通，请稍后再试"));
    await calling;

    expect(live.snapshot().call).toEqual({ phase: "dialing" }); // as it was when the page was left
  });

  it("hangs up the call under way when the page is left", async () => {
    const { live, attempts } = conversation();
    const call = await connected(live, attempts);

    live.dispose();

    expect(call.hangUps).toBe(1);
  });

  it("stops showing what it is hearing once the backend takes the words up", async () => {
    const { live, attempts } = conversation();
    await connected(live, attempts);
    const { handlers } = attempts[0];
    handlers.onHearing("你好");
    expect(live.snapshot().hearing).toBe("你好");

    handlers.onEvent({ type: "user", text: "你好" });

    expect(live.snapshot().hearing).toBe("");
    expect(live.snapshot().entries.map((e) => e.kind)).toEqual(["user", "character"]);
  });

  it("shows her latest line in this call, not one from before it", async () => {
    const { live, attempts } = conversation({ messages: history });
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
    const { live, attempts } = conversation({ messages: history });
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
    const { live } = conversation({
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

describe("LiveConversation: mic mute", () => {
  it("turns the microphone off and on in the browser only", async () => {
    const { live, attempts } = conversation();
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
    const { live, attempts } = conversation();
    const call = await connected(live, attempts);
    live.toggleMic();
    live.setDraft("你好");

    await live.submit();

    expect(call.sent).toEqual(["你好"]);
  });

  it("starts each call with the microphone on", async () => {
    const { live, attempts } = conversation();
    await connected(live, attempts);
    live.toggleMic();
    await live.hangUp();

    await connected(live, attempts);

    expect(live.snapshot().micMuted).toBe(false);
  });

  it("does nothing until the call has connected", () => {
    const { live } = conversation();
    void live.startCall();

    live.toggleMic();

    expect(live.snapshot().micMuted).toBe(false);
  });
});

describe("LiveConversation: switching the microphone", () => {
  it("switches the call to the chosen microphone, which becomes the default for later calls", async () => {
    const { live, attempts, preferences } = conversation();
    const call = await connected(live, attempts);
    call.switchTo = { id: "usb", fellBack: false };

    await live.switchMic("usb");

    expect(call.switches).toEqual(["usb"]);
    expect(call.hangUps).toBe(0);
    expect(live.snapshot().micId).toBe("usb");
    expect(preferences().micId).toBe("usb");
  });

  it("keeps the microphone muted across a switch", async () => {
    const { live, attempts } = conversation();
    await connected(live, attempts);
    live.toggleMic();

    await live.switchMic("usb");

    expect(live.snapshot().micMuted).toBe(true);
  });

  it("starts a call on the default microphone, saying which one is in use", async () => {
    const { live, attempts } = conversation();
    const calling = live.startCall();
    attempts[0].connect(new FakeCall(1800, false, { id: "usb", fellBack: false }));
    await calling;

    expect(attempts[0].preferences.micId).toBe("");
    expect(live.snapshot().micId).toBe("usb");
    expect(live.snapshot().micNotice).toBeNull();
  });

  it("says so when the default microphone is gone and the system default is used", async () => {
    const { live, attempts, preferences } = conversation();
    await connected(live, attempts, new FakeCall(1800, false, { id: "", fellBack: true }));

    expect(live.snapshot().micId).toBe("");
    expect(live.snapshot().micNotice).toBe("fell_back");
    // Kept: plugged back in, it is used again.
    expect(preferences().micId).toBe("");
  });

  it("says so when the microphone in use is unplugged during the call", async () => {
    const { live, attempts } = conversation();
    const call = new FakeCall(1800, false, { id: "usb", fellBack: false });
    await connected(live, attempts, call);

    attempts[0].handlers.onMicLost({ id: "", fellBack: true });

    expect(live.snapshot().micId).toBe("");
    expect(live.snapshot().micNotice).toBe("fell_back");
    expect(call.hangUps).toBe(0);
  });

  it("says so when the microphone is unplugged and no other one opens, keeping the call", async () => {
    const { live, attempts } = conversation();
    const call = await connected(live, attempts, new FakeCall(1800, false, { id: "usb", fellBack: false }));

    attempts[0].handlers.onMicLost(null);

    expect(live.snapshot().micNotice).toBe("lost");
    expect(live.snapshot().call.phase).toBe("connected");
    expect(call.hangUps).toBe(0);
  });

  it("keeps the microphone in use when the chosen one cannot be opened", async () => {
    const { live, attempts, preferences } = conversation();
    const call = await connected(live, attempts, new FakeCall(1800, false, { id: "usb", fellBack: false }));
    call.switchTo = null;

    await live.switchMic("broken");

    expect(live.snapshot().micId).toBe("usb");
    expect(live.snapshot().micNotice).toBe("unavailable");
    expect(preferences().micId).toBe("");
  });

  it("clears the notice after a switch that works, and when the call is over", async () => {
    const { live, attempts } = conversation();
    const call = await connected(live, attempts, new FakeCall(1800, false, { id: "", fellBack: true }));
    call.switchTo = { id: "usb", fellBack: false };

    await live.switchMic("usb");
    expect(live.snapshot().micNotice).toBeNull();

    attempts[0].handlers.onMicLost({ id: "", fellBack: true });
    await live.hangUp();
    expect(live.snapshot().micNotice).toBeNull();
  });

  it("does nothing until the call has connected", async () => {
    const { live, preferences } = conversation();
    void live.startCall();

    await live.switchMic("usb");

    expect(preferences().micId).toBe("");
  });

  it("does not show a switch that finishes after the call is over", async () => {
    const { live, attempts } = conversation();
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
    const { live, attempts, preferences } = conversation();
    const call = await connected(live, attempts);

    live.toggleTextOnly();

    expect(live.snapshot().textOnly).toBe(true);
    expect(preferences().muted).toBe(true);
    expect(call.textOnly).toEqual([true]);
  });

  it("starts a call with the switch as it is", async () => {
    const { live, attempts } = conversation();
    live.toggleTextOnly();

    void live.startCall();

    expect(attempts[0].preferences.muted).toBe(true);
  });
});

describe("LiveConversation: typing", () => {
  it("keeps the draft within the 2000 characters the backend accepts", () => {
    const { live } = conversation();

    live.setDraft("あ".repeat(2005));

    expect(live.snapshot().draft).toBe("あ".repeat(2000));
  });

  it("records a text turn the backend answers", async () => {
    const { live } = conversation({
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
    const { live } = conversation({ messages: history, turns });
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
    const { live } = conversation({ messages: history, turns });
    live.setDraft("你好");

    await live.submit();

    expect(live.snapshot().failure?.countsTowardLimit).toBe(false);
  });

  it("does not say whether a text turn counts when its reply just stops", async () => {
    // 连接断了，前端分不清是服务出错还是回复其实已经记下，所以不下结论。
    const { live } = conversation({
      messages: history,
      turns: scripted([{ type: "user", text: "你好" }]),
    });
    live.setDraft("你好");

    await live.submit();

    expect(live.snapshot().failure).not.toBeNull();
    expect(live.snapshot().failure?.countsTowardLimit).toBeUndefined();
  });

  it("hands what the user types in a call to the call instead of starting a text turn", async () => {
    const { live, attempts } = conversation({ messages: history });
    const call = await connected(live, attempts);
    live.setDraft("你好");

    await live.submit();

    expect(call.sent).toEqual(["你好"]);
    expect(live.snapshot()).toMatchObject({ draft: "", busy: false });
    expect(live.snapshot().entries.map((e) => e.key)).toEqual(["m1", "m2"]);
  });

  it("sends nothing while a call is dialing, keeping the text in the input", async () => {
    const turns: string[] = [];
    const { live, attempts } = conversation({
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
    const { live, attempts } = conversation({
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
    const { live, published } = conversation({
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
