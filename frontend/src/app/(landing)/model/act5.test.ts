import { describe, expect, it } from "vitest";

import { idolColors } from "./color";
import { describeScene, memoryWorld, type MemoryWorld, type Scene, type SceneInput, type Viewport } from "./scene";
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
  ["にちか", "#a6ceb6", 4],
  ["美琴", "#760f10", 4],
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
const tl = timelineOf(5);
const act2 = spanOf(tl, 2)!;
const act5 = spanOf(tl, 5)!;
const act6 = spanOf(tl, 6)!;
const desktop: Viewport = { w: 1440, h: 900 };
const world = memoryWorld(lights) as MemoryWorld & { sender: string; receiver: string };

function scene(input: Partial<SceneInput> = {}): Scene {
  return describeScene({ lights, scroll: act5.from, viewport: desktop, tier: "full", ...input });
}
const in5 = (p: number) => act5.from + p * act5.length;
const ps = Array.from({ length: 401 }, (_, k) => k / 400);
const halo = (id: string) => idolColors(ROSTER.find(([name]) => name === id)![1]).halo;

describe("memoryWorld: 第 5 幕的布景", () => {
  it("一件事从光谱里的第一位传给后半段里的一位，两人的颜色差得开", () => {
    expect(world.sender).toBe("真乃");
    const order = lights.map((l) => l.id);
    expect(order.indexOf(world.receiver)).toBeGreaterThanOrEqual(order.length / 2);
  });

  it("全部的光按光谱的顺序竖着排在两屏宽的布景里", () => {
    const xs = world.lines.map((l) => l.x);
    expect(xs).toEqual([...xs].sort((a, b) => a - b));
    expect(xs[0]).toBeGreaterThan(0);
    expect(xs.at(-1)).toBeLessThan(2);
  });

  it("再从她那里传给另外三位：三位各不相同，不是发送的人也不是她，弧线落在各自的光上", () => {
    const targets = world.spreads.map((s) => s.target);
    expect(new Set(targets).size).toBe(3);
    expect(targets).not.toContain(world.sender);
    expect(targets).not.toContain(world.receiver);
    const lineX = new Map(world.lines.map((l) => [l.id, l.x]));
    for (const s of world.spreads) {
      expect(s.from).toEqual(world.arc.to);
      expect(s.to[0]).toBe(lineX.get(s.target));
    }
  });
});

describe("describeScene: 第 5 幕，一件事传开", () => {
  const frames = ps.map((p) => scene({ scroll: in5(p) }));
  const lineX = (id: string, s: Scene) => s.bands.find((b) => b.id === id)!.x;
  const intensity = (id: string, s: Scene) => s.bands.find((b) => b.id === id)!.intensity;

  it("光点从她的光出发，沿预先算好的弧线落到另一位的光上，颜色从她渐变到另一位", () => {
    const start = scene({ scroll: in5(0.12) });
    const mid = scene({ scroll: in5(0.3) }).memory!.relays[0];
    const end = scene({ scroll: in5(0.48) });
    const [a, b] = [start.memory!.relays[0], end.memory!.relays[0]];
    expect(a.intensity).toBeGreaterThan(0);
    expect(a.x).toBeCloseTo(lineX(world.sender, start));
    expect(b.x).toBeCloseTo(lineX(world.receiver, end));
    // 弧线鼓在两端的上方。
    expect(mid.y).toBeLessThan(Math.min(a.y, b.y));
    expect(a.color).toBe(halo(world.sender));
    expect(b.color).toBe(halo(world.receiver));
    expect([halo(world.sender), halo(world.receiver)]).not.toContain(mid.color);
  });

  it("她亮起来以后，再分出三个光点落到另外三位的光上，颜色从她渐变到各自的颜色；落到谁，谁才亮起来", () => {
    world.spreads.forEach((spread, k) => {
      const leaving = scene({ scroll: in5(0.54 + 0.05 * k) });
      const arriving = scene({ scroll: in5(0.8 + 0.05 * k) });
      const [a, b] = [leaving.memory!.relays[k + 1], arriving.memory!.relays[k + 1]];
      expect(a.intensity).toBeGreaterThan(0);
      expect(a.x).toBeCloseTo(lineX(world.receiver, leaving));
      expect(b.x).toBeCloseTo(lineX(spread.target, arriving));
      expect(a.color).toBe(halo(world.receiver));
      expect(b.color).toBe(halo(spread.target));
      expect(intensity(spread.target, leaving)).toBeLessThan(0.2);
      expect(intensity(spread.target, scene({ scroll: in5(1) }))).toBeGreaterThan(0.5);
    });
    // 传开之前，她先亮。
    expect(intensity(world.receiver, scene({ scroll: in5(0.54) }))).toBeGreaterThan(0.5);
  });

  it("光点跟着滚动连续地走，不跳", () => {
    frames.slice(1).forEach((f, k) =>
      f.memory!.relays.forEach((r, i) => {
        const prev = frames[k].memory!.relays[i];
        expect(Math.abs(r.x - prev.x)).toBeLessThan(desktop.w * 0.05);
        expect(Math.abs(r.y - prev.y)).toBeLessThan(desktop.h * 0.05);
      }),
    );
  });

  it("画面跟着光点横移一到两屏，只往一个方向走；传开的三位都在画面里", () => {
    const pans = frames.map((f) => f.memory!.pan);
    expect(pans).toEqual([...pans].sort((a, b) => a - b));
    expect(pans.at(-1)! - pans[0]).toBeGreaterThanOrEqual(desktop.w * 0.5);
    expect(pans.at(-1)! - pans[0]).toBeLessThanOrEqual(desktop.w * 2);
    const end = frames.at(-1)!;
    for (const { target } of world.spreads) {
      expect(lineX(target, end)).toBeGreaterThan(desktop.w * 0.08);
      expect(lineX(target, end)).toBeLessThan(desktop.w);
    }
  });

  it("走过的光路跟着光点画出来（DOM 上的连线），到这一幕结尾画完", () => {
    for (let k = 0; k < 1 + world.spreads.length; k++) {
      const progress = frames.map((f) => f.memory!.paths[k]);
      expect(progress).toEqual([...progress].sort((a, b) => a - b));
      expect(progress[0]).toBe(0);
      expect(progress.at(-1)).toBe(1);
    }
  });

  it("同屏满强度的光不超过 5 道", () => {
    for (const f of frames) expect(f.bands.filter((b) => b.intensity > 0.5).length).toBeLessThanOrEqual(5);
  });

  it("这一幕里指针会留下痕迹；别的幕里没有", () => {
    expect(scene({ scroll: in5(0.5) }).memory!.trail).toBe(true);
    expect(scene({ scroll: act2.from + 2 }).memory).toBeNull();
  });

  it("减少动态效果档：光路画完、传到的人都亮着，没有指针痕迹", () => {
    const s = scene({ scroll: in5(0.1), tier: "reduced" });
    expect(s.memory!.paths.every((t) => t === 1)).toBe(true);
    for (const { target } of world.spreads) expect(intensity(target, s)).toBeGreaterThan(0.5);
    expect(s.memory!.trail).toBe(false);
  });
});

describe("describeScene: 第 2 幕到第 5 幕、第 5 幕到第 6 幕", () => {
  it("光谱解开钉住的那一屏里，一道道光连续地变成第 5 幕的样子", () => {
    const before = scene({ scroll: act5.from - 1e-9 });
    const start = scene({ scroll: act5.from });
    start.bands.forEach((b, i) => {
      expect(b.x).toBeCloseTo(before.bands[i].x, 3);
      expect(b.intensity).toBeCloseTo(before.bands[i].intensity, 3);
    });
    for (let q = 0; q <= 1; q += 0.01) {
      const a = scene({ scroll: act5.from - 1 + q });
      const b = scene({ scroll: act5.from - 1 + q + 0.0002 });
      a.bands.forEach((band, i) => expect(Math.abs(b.bands[i].x - band.x)).toBeLessThan(desktop.w * 0.01));
    }
  });

  it("光谱解开钉住、第 5 幕从下面进来的那一屏里，连线还一条都没画，布景停在第 5 幕开头的横移上", () => {
    const start = scene({ scroll: act5.from }).memory!;
    for (const q of [0.01, 0.5, 0.99]) {
      const entering = scene({ scroll: act5.from - 1 + q }).memory;
      expect(entering?.paths.every((t) => t === 0), `q ${q}`).toBe(true);
      expect(entering!.pan).toBeCloseTo(start.pan);
      expect(entering!.relays.every((r) => r.intensity === 0)).toBe(true);
      expect(entering!.trail).toBe(false);
    }
  });

  it("第 5 幕解开钉住时光暗下去，到第 6 幕全暗", () => {
    const end = scene({ scroll: act6.from - 1e-6 });
    expect(end.bands.every((b) => b.intensity < 0.01)).toBe(true);
    expect(end.memory!.relays.every((r) => r.intensity === 0)).toBe(true);
  });
});
