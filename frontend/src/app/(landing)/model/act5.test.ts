import { describe, expect, it } from "vitest";

import { idolColors } from "./color";
import { describeScene, memoryWorld, type Scene, type SceneInput, type Viewport } from "./scene";
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
const world = memoryWorld(lights) as ReturnType<typeof memoryWorld> & { sender: string; receiver: string };

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

  it("回忆的光迹是几条从接收的那一位出发的曲线，不带任何文字", () => {
    expect(world.traces.length).toBeGreaterThanOrEqual(2);
    for (const d of world.traces) expect(d).toMatch(/^M[\d. ,CS-]+$/);
  });
});

describe("describeScene: 第 5 幕，一件事从一位偶像传到另一位", () => {
  const relays = ps.map((p) => scene({ scroll: in5(p) }).memory!);

  it("光点从她的光出发，沿预先算好的弧线落到另一位的光上，颜色从她渐变到另一位", () => {
    const lineX = (id: string, s: Scene) => s.bands.find((b) => b.id === id)!.x;
    const start = scene({ scroll: in5(0.12) });
    const mid = scene({ scroll: in5(0.45) }).memory!.relay;
    const end = scene({ scroll: in5(0.8) });
    expect(start.memory!.relay.x).toBeCloseTo(lineX(world.sender, start));
    expect(end.memory!.relay.x).toBeCloseTo(lineX(world.receiver, end));
    // 弧线鼓在两端的上方。
    expect(mid.y).toBeLessThan(Math.min(start.memory!.relay.y, end.memory!.relay.y));
    expect(start.memory!.relay.color).toBe(halo(world.sender));
    expect(end.memory!.relay.color).toBe(halo(world.receiver));
    expect([halo(world.sender), halo(world.receiver)]).not.toContain(mid.color);
  });

  it("光点跟着滚动连续地走，不跳", () => {
    relays.slice(1).forEach((r, k) => {
      expect(Math.abs(r.relay.x - relays[k].relay.x)).toBeLessThan(desktop.w * 0.05);
      expect(Math.abs(r.relay.y - relays[k].relay.y)).toBeLessThan(desktop.h * 0.05);
    });
  });

  it("画面跟着光点横移一到两屏，只往一个方向走", () => {
    const pans = relays.map((r) => r.pan);
    expect(pans).toEqual([...pans].sort((a, b) => a - b));
    expect(pans.at(-1)! - pans[0]).toBeGreaterThanOrEqual(desktop.w * 0.5);
    expect(pans.at(-1)! - pans[0]).toBeLessThanOrEqual(desktop.w * 2);
  });

  it("回忆的光迹在光点落下以后跟着滚动画出来，到这一幕结尾画完", () => {
    for (let k = 0; k < world.traces.length; k++) {
      const progress = relays.map((r) => r.traces[k]);
      expect(progress).toEqual([...progress].sort((a, b) => a - b));
      expect(progress[0]).toBe(0);
      expect(progress.at(-1)).toBe(1);
    }
    expect(scene({ scroll: in5(0.3) }).memory!.traces.every((t) => t === 0)).toBe(true);
  });

  it("同屏满强度的光不超过 5 道", () => {
    for (const p of ps) expect(scene({ scroll: in5(p) }).bands.filter((b) => b.intensity > 0.5).length).toBeLessThanOrEqual(5);
  });

  it("这一幕里指针会留下痕迹；别的幕里没有", () => {
    expect(scene({ scroll: in5(0.5) }).memory!.trail).toBe(true);
    expect(scene({ scroll: act2.from + 2 }).memory).toBeNull();
  });

  it("减少动态效果档：光路和光迹直接是完成态，没有指针痕迹", () => {
    const s = scene({ scroll: in5(0.1), tier: "reduced" });
    expect(s.memory!.traces.every((t) => t === 1)).toBe(true);
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

  it("第 5 幕解开钉住时光暗下去，到第 6 幕全暗", () => {
    const end = scene({ scroll: act6.from - 1e-6 });
    expect(end.bands.every((b) => b.intensity < 0.01)).toBe(true);
    expect(end.memory!.relay.intensity).toBe(0);
  });
});
