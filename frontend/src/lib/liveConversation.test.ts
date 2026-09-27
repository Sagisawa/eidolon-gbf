import { describe, expect, it } from "vitest";
import { ApiError, type Message, type TurnEvent } from "@/lib/api";
import type { Call, CallHandlers } from "@/lib/call";
import type { CallPreferences } from "@/lib/callPreferences";
import { LiveConversation, type Ports } from "@/lib/liveConversation";

/** A call that has connected: records what the conversation asks of it. */
class FakeCall implements Call {
  sent: string[] = [];
  mutes: boolean[] = [];
  hangUps = 0;
  sendText = (text: string) => void this.sent.push(text);
  setMuted = (muted: boolean) => void this.mutes.push(muted);
  hangUp = async () => void this.hangUps++;
}

/** One `startCall`: it stays connecting until the test says how it ends. */
type Attempt = {
  preferences: CallPreferences;
  handlers: CallHandlers;
  connect: (call: Call) => void;
  fail: (error: Error) => void;
};

/** A live conversation over fake ports: calls the test connects, scripted text turns,
 * preferences kept in memory. */
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
async function connected(live: LiveConversation, attempts: Attempt[]): Promise<FakeCall> {
  const calling = live.toggleCall();
  const call = new FakeCall();
  attempts[attempts.length - 1].connect(call);
  await calling;
  return call;
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

describe("LiveConversation", () => {
  it("hangs up a call that finishes connecting after the page is left", async () => {
    const { live, attempts, published } = conversation();
    const calling = live.toggleCall();
    expect(live.snapshot().phase).toBe("connecting");

    live.dispose();
    const before = published();
    const call = new FakeCall();
    attempts[0].connect(call);
    await calling;

    expect(call.hangUps).toBe(1);
    expect(live.snapshot().phase).not.toBe("active");
    expect(published()).toBe(before);
  });

  it("shows no failure for a call that fails to connect after the page is left", async () => {
    const { live, attempts } = conversation();
    const calling = live.toggleCall();
    live.dispose();
    attempts[0].fail(new Error("无法接通，请稍后再试"));
    await calling;

    expect(live.snapshot().failure).toBeNull();
  });

  it("hangs up the call under way when the page is left", async () => {
    const { live, attempts } = conversation();
    const call = await connected(live, attempts);

    live.dispose();

    expect(call.hangUps).toBe(1);
  });

  it("takes back the reply cut off when the user hangs up, without a failure", async () => {
    const { live, attempts } = conversation({ messages: history });
    const call = await connected(live, attempts);
    const { handlers } = attempts[0];
    handlers.onEvent({ type: "user", text: "你好" });
    handlers.onEvent({ type: "delta", segment: 0, lang: "ja", text: "こん" });
    handlers.onHearing("还有");

    await live.toggleCall();

    expect(call.hangUps).toBe(1);
    expect(live.snapshot()).toMatchObject({ phase: "idle", hearing: "", failure: null });
    expect(live.snapshot().entries.map((e) => e.key)).toEqual(["m1", "m2"]);
  });

  it("takes back the reply cut off when the call drops, saying why the backend ended it", async () => {
    const { live, attempts } = conversation({ messages: history });
    await connected(live, attempts);
    const { handlers } = attempts[0];
    handlers.onEvent({ type: "ended", message: "通话已达到时长上限" });
    handlers.onEvent({ type: "user", text: "你好" });
    handlers.onHearing("还有");

    handlers.onDropped();

    expect(live.snapshot()).toMatchObject({
      phase: "idle",
      hearing: "",
      failure: { message: "通话已达到时长上限", signedOut: false },
    });
    expect(live.snapshot().entries.map((e) => e.key)).toEqual(["m1", "m2"]);
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

  it("does not give a new call's drop the reason an earlier call was ended for", async () => {
    const { live, attempts } = conversation();
    await connected(live, attempts);
    attempts[0].handlers.onEvent({ type: "ended", message: "通话已达到时长上限" });
    attempts[0].handlers.onDropped();

    await connected(live, attempts);
    attempts[1].handlers.onDropped();

    expect(live.snapshot().failure).toEqual({ message: "通话已断开", signedOut: false });
  });

  it("says the call dropped when the backend gave no reason", async () => {
    const { live, attempts } = conversation();
    await connected(live, attempts);

    attempts[0].handlers.onDropped();

    expect(live.snapshot().failure).toEqual({ message: "通话已断开", signedOut: false });
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

  it("sends nothing while a call is connecting, keeping the text in the input", async () => {
    const turns: string[] = [];
    const { live, attempts } = conversation({
      turns: (text) => {
        turns.push(text);
        return scripted([])();
      },
    });
    const calling = live.toggleCall();
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

    await live.toggleCall();
    answer();
    await sending;

    expect(attempts).toEqual([]);
    expect(live.snapshot().phase).toBe("idle");
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

  it("keeps the mute switch in the preferences and tells the call under way", async () => {
    const { live, attempts, preferences } = conversation();
    const call = await connected(live, attempts);

    live.toggleMute();

    expect(live.snapshot().muted).toBe(true);
    expect(preferences().muted).toBe(true);
    expect(call.mutes).toEqual([true]);
  });

  it("starts a call with the mute switch as it is", async () => {
    const { live, attempts } = conversation();
    live.toggleMute();

    void live.toggleCall();

    expect(attempts[0].preferences.muted).toBe(true);
  });

  it("leaves a call that drops while connecting to fail to connect", async () => {
    const { live, attempts } = conversation();
    const calling = live.toggleCall();

    attempts[0].handlers.onDropped();

    expect(live.snapshot()).toMatchObject({ phase: "connecting", failure: null });
    attempts[0].fail(new Error("无法接通，请稍后再试"));
    await calling;
    expect(live.snapshot()).toMatchObject({
      phase: "idle",
      failure: { message: "无法接通，请稍后再试", signedOut: false },
    });
  });

  it("shows a turn failing in a call while the call goes on", async () => {
    const { live, attempts } = conversation({ messages: history });
    await connected(live, attempts);
    const { handlers } = attempts[0];
    handlers.onEvent({ type: "user", text: "你好" });

    handlers.onEvent({ type: "error", message: "角色暂时无法回复" });

    expect(live.snapshot()).toMatchObject({
      phase: "active",
      failure: { message: "角色暂时无法回复", signedOut: false },
    });
    expect(live.snapshot().entries.map((e) => e.key)).toEqual(["m1", "m2"]);
  });

  it("clears the last failure when a call starts", async () => {
    const { live, attempts } = conversation();
    const failing = live.toggleCall();
    attempts[0].fail(new Error("无法接通，请稍后再试"));
    await failing;

    void live.toggleCall();

    expect(live.snapshot().failure).toBeNull();
  });

  it("goes back to idle with the backend's reason when a call fails to connect", async () => {
    const { live, attempts } = conversation();
    const calling = live.toggleCall();
    attempts[0].fail(new ApiError("通话暂时不可用", 503));
    await calling;

    expect(live.snapshot().phase).toBe("idle");
    expect(live.snapshot().failure).toEqual({ message: "通话暂时不可用", signedOut: false });
  });
});
