import { describe, expect, it } from "vitest";

import { connectTone, focusOf, holdMs, INITIAL, interactionReducer, type Interaction, type InteractionAction } from "./interaction";

const run = (...actions: InteractionAction[]): Interaction => actions.reduce(interactionReducer, INITIAL);

const press = (id: string, greeting: Extract<InteractionAction, { type: "press" }>["greeting"] = "voice"): InteractionAction => ({
  type: "press",
  id,
  greeting,
});

describe("interactionReducer: 聚焦和点击偶像", () => {
  it("指针、键盘移到一位偶像上就聚焦她，移开就放下；聚焦本身从不出声", () => {
    const pointed = run({ type: "point", id: "meguru" });
    expect(focusOf(pointed)).toBe("meguru");
    expect(pointed.saying).toBeNull();
    expect(pointed.sound).toBe("hidden");
    expect(focusOf(run({ type: "point", id: "meguru" }, { type: "unpoint", id: "meguru" }))).toBeNull();
  });

  it("从一位移到另一位时，先到的移开不会放下后到的", () => {
    const s = run({ type: "point", id: "meguru" }, { type: "point", id: "kogane" }, { type: "unpoint", id: "meguru" });
    expect(focusOf(s)).toBe("kogane");
  });

  it("推入别的组合时放下聚焦，正在说的那句也收掉", () => {
    const s = run(press("meguru"), { type: "leave" });
    expect(focusOf(s)).toBeNull();
    expect(s.saying).toBeNull();
  });
});

describe("interactionReducer: 招呼要不要出声", () => {
  it("第一次点就聚焦她并出声；真的出了声才出现声音开关（开着），播完记下来", () => {
    const pressed = run(press("meguru"));
    expect(focusOf(pressed)).toBe("meguru");
    expect(pressed.saying).toMatchObject({ id: "meguru", voice: "loading" });
    expect(pressed.sound).toBe("hidden");
    const playing = interactionReducer(pressed, { type: "voice", n: 1, event: "playing" });
    expect(playing.saying?.voice).toBe("playing");
    expect(playing.sound).toBe("on");
    expect(interactionReducer(playing, { type: "voice", n: 1, event: "ended" }).saying?.voice).toBe("ended");
  });

  it("音频加载失败就只剩字幕，也不出现开关", () => {
    const s = run(press("meguru"), { type: "voice", n: 1, event: "failed" });
    expect(s.saying).toMatchObject({ id: "meguru", voice: null });
    expect(s.sound).toBe("hidden");
  });

  it("关掉开关以后点，只显示字幕；再打开，正在显示的那句不从中间出声，之后点的又出声", () => {
    const off = run(
      press("meguru"),
      { type: "voice", n: 1, event: "playing" },
      { type: "voice", n: 1, event: "ended" },
      { type: "sound" },
      press("kogane"),
    );
    expect(off.saying).toMatchObject({ id: "kogane", voice: null });
    expect(off.sound).toBe("off");
    const on = interactionReducer(off, { type: "sound" });
    expect(on.sound).toBe("on");
    expect(on.saying).toMatchObject({ id: "kogane", voice: null });
    expect(interactionReducer(on, press("meguru")).saying).toMatchObject({ id: "meguru", voice: "loading" });
  });

  it("说到一半关掉开关：声音停下，字幕留着", () => {
    const s = run(press("meguru"), { type: "voice", n: 1, event: "playing" }, { type: "sound" });
    expect(s.saying).toMatchObject({ id: "meguru", voice: null });
  });

  it("没有音频（没配素材地址或她没有音色）时只显示字幕", () => {
    expect(run(press("meguru", "subtitle")).saying).toMatchObject({ id: "meguru", voice: null });
  });

  it("没有招呼的偶像点了只聚焦，没有字幕和声音；上一句也停下", () => {
    const s = run(press("meguru"), press("kogane", "none"));
    expect(focusOf(s)).toBe("kogane");
    expect(s.saying).toBeNull();
  });
});

describe("interactionReducer: 同时只播一句", () => {
  it("点另一位时上一句停下，换成她这一句；上一句的音频事件和收尾不影响这一句", () => {
    const s = run(
      press("meguru"),
      press("kogane"),
      { type: "voice", n: 1, event: "failed" },
      { type: "voice", n: 1, event: "ended" },
      { type: "done", n: 1 },
    );
    expect(s.saying).toMatchObject({ id: "kogane", n: 2, voice: "loading" });
  });

  it("指针移到另一位身上时，上一句收掉", () => {
    expect(run(press("meguru"), { type: "point", id: "kogane" }).saying).toBeNull();
  });

  it("她说着的时候指针移开，她仍然是聚焦的那位，直到说完", () => {
    const talking = run({ type: "point", id: "meguru" }, press("meguru"), { type: "unpoint", id: "meguru" });
    expect(focusOf(talking)).toBe("meguru");
    const done = interactionReducer(talking, { type: "done", n: 1 });
    expect(done.saying).toBeNull();
    expect(focusOf(done)).toBeNull();
  });
});

describe("holdMs: 字幕还要留多久", () => {
  it("音频还在加载或在播时等它，播完以后再留一会儿，只有字幕时留得久一些", () => {
    expect(holdMs({ id: "a", n: 1, voice: "loading" })).toBeNull();
    expect(holdMs({ id: "a", n: 1, voice: "playing" })).toBeNull();
    const after = holdMs({ id: "a", n: 1, voice: "ended" })!;
    const textOnly = holdMs({ id: "a", n: 1, voice: null })!;
    expect(after).toBeGreaterThan(0);
    expect(textOnly).toBeGreaterThan(after);
  });
});

describe("interactionReducer: 第 4 幕的接听", () => {
  /** 从 `from` 走到 `actions` 以后，每一步要不要播接通音。 */
  const tones = (from: Interaction, ...actions: InteractionAction[]) => {
    const steps: boolean[] = [];
    actions.reduce((s, a) => {
      const next = interactionReducer(s, a);
      steps.push(connectTone(s, next));
      return next;
    }, from);
    return steps;
  };

  it("滚动经过时只有画面在响：没接听就不出声", () => {
    expect(tones(INITIAL, { type: "point", id: "mano" }, { type: "leave" }, { type: "hang-up" })).toEqual([false, false, false]);
  });

  it("点一下「接听」就接通，播一声接通音（没有铃声）", () => {
    expect(run({ type: "answer" }).call).toBe("connected");
    expect(tones(INITIAL, { type: "answer" })).toEqual([true]);
  });

  it("接通音真的响了才出现声音开关；放不出来就不出现", () => {
    const connected = run({ type: "answer" });
    expect(connected.sound).toBe("hidden");
    expect(interactionReducer(connected, { type: "tone", event: "playing" }).sound).toBe("on");
    expect(interactionReducer(connected, { type: "tone", event: "failed" }).sound).toBe("hidden");
  });

  it("声音开关关着时接听：照样接通，但不播接通音", () => {
    const off = run(press("meguru"), { type: "voice", n: 1, event: "playing" }, { type: "sound" });
    expect(off.sound).toBe("off");
    expect(tones(off, { type: "answer" })).toEqual([false]);
    expect(interactionReducer(off, { type: "answer" }).call).toBe("connected");
  });

  it("离开第 4 幕就挂断：回到响铃的样子，不出声；已经接通了再点「接听」不再播", () => {
    const connected = run({ type: "answer" });
    expect(interactionReducer(connected, { type: "hang-up" }).call).toBe("ringing");
    expect(tones(connected, { type: "answer" }, { type: "hang-up" })).toEqual([false, false]);
  });

  it("同时只有一种声音：接听时正在说的招呼停下", () => {
    const s = run(press("meguru"), { type: "voice", n: 1, event: "playing" }, { type: "answer" });
    expect(s.saying).toBeNull();
  });
});
