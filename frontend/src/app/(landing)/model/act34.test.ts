import { describe, expect, it } from "vitest";

import { copy } from "@/i18n";

import { idolColors } from "./color";
import { describeScene, memoryWorld, TALK_LINES, talkLineShown, type Scene, type SceneInput, type Viewport } from "./scene";
import { lightsOf, prepareSpectrum, type RosterEntry } from "./spectrum";
import { spanOf, timelineOf } from "./timeline";

const ROSTER: [name: string, color: string, unit: number][] = [
  ["真乃", "#ffbad6", 0],
  ["灯織", "#144384", 0],
  ["めぐる", "#ffe012", 0],
  ["恋鐘", "#f84cad", 1],
  ["咲耶", "#006047", 1],
  ["果穂", "#e5461c", 2],
  ["樹里", "#ffc602", 2],
  ["透", "#50d0d0", 3],
  ["小糸", "#7967c3", 3],
];
const characters: RosterEntry[] = ROSTER.map(([name, color, unit], i) => ({
  id: name,
  name,
  color,
  idol_id: i + 1,
  unit: `unit ${unit}`,
  unit_order: unit,
}));
const lights = lightsOf(prepareSpectrum(characters));
const tl = timelineOf(4);
const act2 = spanOf(tl, 2)!;
const act3 = spanOf(tl, 3)!;
const act4 = spanOf(tl, 4)!;
const act5 = spanOf(tl, 5)!;
const desktop: Viewport = { w: 1440, h: 900 };
const phone: Viewport = { w: 390, h: 844 };

function scene(input: Partial<SceneInput> = {}): Scene {
  return describeScene({ lights, scroll: act3.from, viewport: desktop, tier: "full", ...input });
}
const in3 = (p: number) => act3.from + p * act3.length;
const in4 = (p: number) => act4.from + p * act4.length;
const ps = Array.from({ length: 401 }, (_, k) => k / 400);
const bandOf = (s: Scene, id: string) => s.bands.find((b) => b.id === id)!;
const lit = (s: Scene) => s.bands.filter((b) => b.intensity > 0.5).length;

describe("describeScene: 第 2 幕到第 3 幕", () => {
  it("光谱解开钉住的那一屏里，一道道光连续地变成第 3 幕开头的样子", () => {
    const before = scene({ scroll: act3.from - 1e-9 });
    const start = scene({ scroll: act3.from });
    start.bands.forEach((b, i) => {
      expect(b.x).toBeCloseTo(before.bands[i].x, 3);
      expect(b.intensity).toBeCloseTo(before.bands[i].intensity, 3);
    });
    for (let q = 0; q <= 1; q += 0.01) {
      const a = scene({ scroll: act2.to - 1 + q });
      const b = scene({ scroll: act2.to - 1 + q + 0.0002 });
      a.bands.forEach((band, i) => expect(Math.abs(b.bands[i].x - band.x)).toBeLessThan(desktop.w * 0.01));
    }
  });
});

describe("describeScene: 第 3 幕，她说日语", () => {
  it("一道道光收成她一道：说话的是光谱里的第一位，也可以指定是谁", () => {
    const s = scene({ scroll: in3(0.5) });
    expect(s.act).toBe(3);
    expect(bandOf(s, "真乃").intensity).toBeGreaterThan(0.5);
    expect(s.bands.filter((b) => b.id !== "真乃").every((b) => b.intensity === 0)).toBe(true);
    const other = scene({ scroll: in3(0.5), speaker: "咲耶" });
    expect(bandOf(other, "咲耶").intensity).toBeGreaterThan(0.5);
    expect(bandOf(other, "真乃").intensity).toBe(0);
    // 指定的人不在名单里时，仍是第一位。
    expect(bandOf(scene({ scroll: in3(0.5), speaker: "不在名单里" }), "真乃").intensity).toBeGreaterThan(0.5);
  });

  it("她那道光竖着站在画面右边，给左边竖排的原文和底下的字幕留出地方", () => {
    for (const viewport of [desktop, phone]) {
      const b = bandOf(describeScene({ lights, scroll: in3(0.5), viewport, tier: "full" }), "真乃");
      expect(b.dx).toBe(0);
      expect(b.dy).toBe(1);
      expect(b.x).toBeGreaterThan(viewport.w * 0.6);
      expect(b.x).toBeLessThan(viewport.w * 0.95);
    }
  });

  it("原文一列一列出来，出来了就留着；字幕一句一句被光扫出来，扫完是 1", () => {
    const at = (p: number) => scene({ scroll: in3(p) }).talk!;
    expect(at(0).lines).toHaveLength(TALK_LINES);
    expect(at(0).lines.every((l) => l.ja === 0 && l.sweep === 0)).toBe(true);
    const end = at(1);
    expect(end.lines.every((l) => l.ja === 1 && l.sweep === 1)).toBe(true);
    for (let k = 0; k < TALK_LINES; k++) {
      // 第 k 列先出来，第 k + 1 列才出来；字幕的扫光一路往前，不回头，也不跳。
      const appear = (j: number) => ps.find((p) => at(p).lines[j].ja > 0.5)!;
      if (k > 0) expect(appear(k)).toBeGreaterThan(appear(k - 1));
      let last = 0;
      for (const p of ps) {
        const sweep = at(p).lines[k].sweep;
        expect(sweep).toBeGreaterThanOrEqual(last);
        expect(sweep - last).toBeLessThan(0.08);
        last = sweep;
      }
    }
  });

  it("同一时刻只看得到一句字幕：下一句扫出来时，上一句收掉；最后一句留到最后", () => {
    for (const p of ps) {
      const shown = scene({ scroll: in3(p) }).talk!.lines.filter((l) => l.subtitle > 0.5);
      expect(shown.length).toBeLessThanOrEqual(1);
    }
    expect(scene({ scroll: in3(1) }).talk!.lines.at(-1)!.subtitle).toBe(1);
  });

  it("落地页文案里正好有这么多句台词", () => {
    expect(copy.landing.act3.lines).toHaveLength(TALK_LINES);
  });

  it("每一句都有一个完整显示的时刻：原文在，字幕扫完了、看得见（页内查找找到它时滚到这里）", () => {
    for (let k = 0; k < TALK_LINES; k++) {
      const line = scene({ scroll: in3(talkLineShown(k)) }).talk!.lines[k];
      expect(line, `第 ${k + 1} 句`).toEqual({ ja: 1, sweep: 1, subtitle: 1 });
    }
  });

  it("这一幕没有色散，同屏满强度的光只有她一道", () => {
    for (const p of ps) {
      const s = scene({ scroll: in3(p), speed: 3 });
      expect(lit(s)).toBeLessThanOrEqual(1);
      if (p > 0.2) expect(s.dispersion).toBe(0);
    }
  });

  it("减少动态效果档（静态档同是静止版式）：原文和字幕一开始就完整显示，几句字幕都在", () => {
    const s = scene({ scroll: in3(0), tier: "reduced" });
    expect(s.talk!.lines.every((l) => l.ja === 1 && l.sweep === 1 && l.subtitle === 1)).toBe(true);
    expect(s.text.act3).toBe(1);
  });

  it("别的幕里没有这一幕的东西", () => {
    expect(scene({ scroll: act2.from + 1 }).talk).toBeNull();
    expect(scene({ scroll: act5.from + 0.5 }).talk).toBeNull();
  });
});

describe("describeScene: 第 4 幕，来电", () => {
  const deep = idolColors("#ffbad6").deep;
  /** 一段时间里光脉冲的最大值和最小值。 */
  const range = (input: Partial<SceneInput>) => {
    const pulses = Array.from({ length: 300 }, (_, k) => scene({ scroll: in4(0.5), time: k * 0.02, ...input }).call!.pulse);
    return [Math.min(...pulses), Math.max(...pulses)];
  };

  it("全屏是她：背景过渡到她的极深底色，她那道光站到画面中间", () => {
    const s = scene({ scroll: in4(0.5), time: 1.9 });
    expect(s.act).toBe(4);
    expect(s.background).toBe(deep);
    const b = bandOf(s, "真乃");
    expect(b.x).toBeCloseTo(desktop.w * 0.5, 0);
    expect(s.bands.filter((x) => x.id !== "真乃").every((x) => x.intensity === 0)).toBe(true);
  });

  it("她有立绘时，来电的画面显出来、她那道光就熄了（不在立绘正后面竖一条线）；没有立绘时光留着", () => {
    for (const p of [0, 0.05, 0.1, 0.5]) {
      const a = bandOf(scene({ scroll: in4(p), speakerStand: true }), "真乃").intensity;
      const b = bandOf(scene({ scroll: in4(p + 0.001), speakerStand: true }), "真乃").intensity;
      expect(Math.abs(b - a), `p ${p}`).toBeLessThan(0.05);
    }
    const s = scene({ scroll: in4(0.5), time: 0.25, speakerStand: true });
    expect(s.bands.every((b) => b.intensity === 0)).toBe(true);
    expect(s.call!.pulse).toBeGreaterThan(0.9);
    expect(bandOf(scene({ scroll: in4(0.5) }), "真乃").intensity).toBeGreaterThan(0.4);
  });

  it("响铃：光一阵一阵地脉动，响的时候画面振动、她的光和背景跟着亮，停的时候不动", () => {
    const frames = Array.from({ length: 300 }, (_, k) => scene({ scroll: in4(0.5), time: k * 0.02 }));
    const pulses = frames.map((s) => s.call!.pulse);
    expect(Math.min(...pulses)).toBeLessThan(0.05);
    expect(Math.max(...pulses)).toBeGreaterThan(0.9);
    for (const [k, s] of frames.entries()) {
      const { pulse, shake } = s.call!;
      if (pulse < 0.01) expect(Math.hypot(shake.x, shake.y), `第 ${k} 帧`).toBeLessThan(0.05);
      expect(Math.hypot(shake.x, shake.y), `第 ${k} 帧`).toBeLessThanOrEqual(4);
    }
    const loud = frames.find((s) => s.call!.pulse > 0.9)!;
    const quiet = frames.find((s) => s.call!.pulse === 0)!;
    expect(Math.hypot(loud.call!.shake.x, loud.call!.shake.y)).toBeGreaterThan(0);
    expect(bandOf(loud, "真乃").intensity).toBeGreaterThan(bandOf(quiet, "真乃").intensity);
    expect(loud.background).not.toBe(quiet.background);
  });

  it("接通以后不再响、不再振动，她的光稳稳地亮着", () => {
    const [low, high] = range({ call: "connected" });
    expect(high).toBe(0);
    expect(low).toBe(0);
    const s = scene({ scroll: in4(0.5), time: 0.2, call: "connected" });
    expect(s.call!.shake).toEqual({ x: 0, y: 0 });
    expect(bandOf(s, "真乃").intensity).toBeGreaterThan(0.5);
  });

  it("减少动态效果档：来电画面静止，不随时间脉动、不振动", () => {
    const at = (time: number) => scene({ scroll: in4(0), tier: "reduced", time }).call!;
    expect(at(0)).toEqual(at(0.3));
    expect(at(0).shake).toEqual({ x: 0, y: 0 });
    expect(at(0).pulse).toBeGreaterThan(0);
  });

  it("同屏满强度的光只有她一道；没有色散", () => {
    for (const p of ps) {
      const s = scene({ scroll: in4(p), time: p * 7, speed: 3 });
      expect(lit(s)).toBeLessThanOrEqual(1);
      expect(s.dispersion).toBe(0);
    }
  });

  it("第 3 幕到第 4 幕：她的光连续地挪到中间，第 3 幕的字退出去，来电的画面显出来", () => {
    for (let q = 0; q <= 1; q += 0.005) {
      const a = bandOf(scene({ scroll: act4.from - 0.05 + q * 0.3 }), "真乃");
      const b = bandOf(scene({ scroll: act4.from - 0.05 + q * 0.3 + 0.0005 }), "真乃");
      expect(Math.abs(b.x - a.x)).toBeLessThan(desktop.w * 0.01);
    }
    expect(scene({ scroll: in3(0.99) }).text.act3).toBe(1);
    expect(scene({ scroll: in4(0.5) }).text.act3).toBe(0);
    expect(scene({ scroll: in4(0) }).text.act4).toBe(0);
    expect(scene({ scroll: in4(0.5) }).text.act4).toBe(1);
  });
});

describe("describeScene: 第 4 幕到第 5 幕", () => {
  it("来电解开钉住的那一屏里，一道道光连续地变成第 5 幕的样子，背景回到黑", () => {
    const before = scene({ scroll: act5.from - 1e-9 });
    const start = scene({ scroll: act5.from });
    start.bands.forEach((b, i) => {
      expect(b.x).toBeCloseTo(before.bands[i].x, 3);
      expect(b.intensity).toBeCloseTo(before.bands[i].intensity, 3);
    });
    expect(before.background).toBe(start.background);
    for (let q = 0; q <= 1; q += 0.01) {
      const a = scene({ scroll: act5.from - 1 + q });
      const b = scene({ scroll: act5.from - 1 + q + 0.0002 });
      a.bands.forEach((band, i) => expect(Math.abs(b.bands[i].x - band.x)).toBeLessThan(desktop.w * 0.01));
    }
  });

  it("来电的画面在解开钉住的那一屏的前半段淡出，不跟着舞台整块往上走", () => {
    expect(scene({ scroll: act4.to - 1 }).text.act4).toBe(1);
    expect(scene({ scroll: act4.to - 0.5 }).text.act4).toBe(0);
  });

  it("第 5 幕从下面进来的那一屏里，连线还一条都没画，布景停在第 5 幕开头的横移上", () => {
    const start = scene({ scroll: act5.from }).memory!;
    for (const q of [0.01, 0.5, 0.99]) {
      const entering = scene({ scroll: act5.from - 1 + q }).memory;
      expect(entering?.paths.every((t) => t === 0), `q ${q}`).toBe(true);
      expect(entering!.pan).toBeCloseTo(start.pan);
      expect(entering!.relays.every((r) => r.intensity === 0)).toBe(true);
      expect(entering!.trail).toBe(false);
    }
    expect(memoryWorld(lights).arcs.length).toBeGreaterThan(0);
  });
});
