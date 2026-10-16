import { describe, expect, it } from "vitest";

import { cameraAt, FIGURE_HEIGHT, type Vec3 } from "./memory";
import { BEATS, memoryTop, STANDS, STEPS, storyAt, type MemoryStory } from "./memoryStory";
import type { Viewport } from "./scene";

const desktop: Viewport = { w: 1440, h: 900 };
const ps = Array.from({ length: 801 }, (_, k) => k / 800);

describe("storyAt: 一件事传开", () => {
  const ALL = [0, 1, 2, 3];
  const at = (p: number, cast: readonly number[] = ALL) => storyAt(p, cameraAt(p, desktop), cast);
  const run = (cast: readonly number[] = ALL) => ps.map((p) => at(p, cast));
  const dist = (a: Vec3, b: Vec3) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
  const copyTo = (s: MemoryStory, k: number) => s.copies.find((c) => c.to === k);
  const stored = (s: MemoryStory, k: number) => s.stored.some((b) => b.island === k);
  /** 第一个满足条件的进度。 */
  const first = (scenes: MemoryStory[], f: (s: MemoryStory) => boolean) => ps[scenes.findIndex(f)];

  it("节拍照原型的节拍表：在每个节拍的起点进入这一拍，往后不回头", () => {
    BEATS.forEach((b, k) => expect(at(b.at).beat).toBe(k));
    const beats = run().map((s) => s.beat);
    expect(beats).toEqual([...beats].sort((a, b) => a - b));
    expect(beats[0]).toBe(0);
    expect(beats.at(-1)).toBe(BEATS.length - 1);
  });

  it("手机亮起，消息落到真乃头顶，变成方块，再收进她的柱子", () => {
    const head: Vec3 = [STANDS[0][0], STANDS[0][1] + FIGURE_HEIGHT, STANDS[0][2]];
    expect(at(0.05).message).toBeNull();
    expect(at(0.1).phone).toBe(1);
    expect(at(0.3).phone).toBeLessThan(0.5);
    // 落到她头顶上方，那时还是气泡；她想了想，变成方块。
    const caught = at(0.175).message!;
    expect(dist(caught.position, head)).toBeLessThan(0.6);
    expect(caught.position[1]).toBeGreaterThan(head[1]);
    expect(caught.morph).toBe(0);
    expect(at(0.23).message!.morph).toBe(1);
    // 收进柱子的那一刻消息没了，柱顶有了一块，就在消息最后到的地方。
    const scenes = run();
    const last = scenes.findLastIndex((s) => s.message !== null);
    expect(dist(scenes[last].message!.position, memoryTop(0))).toBeLessThan(0.05);
    expect(stored(scenes[last], 0)).toBe(false);
    expect(stored(scenes[last + 1], 0)).toBe(true);
  });

  it("收进记忆柱的时刻按顺序：真乃、果穗、冬优子、雾子；收进以后柱顶一直有块，往回滚就没了", () => {
    const scenes = run();
    const times = ALL.map((k) => first(scenes, (s) => stored(s, k)));
    expect(times[0]).toBeLessThan(times[1]);
    expect(times[1]).toBeLessThan(times[2]);
    expect(times[2]).toBeLessThan(times[3]);
    for (const k of ALL) scenes.forEach((s, i) => expect(stored(s, k), `第 ${k} 座岛，p ${ps[i]}`).toBe(ps[i] >= times[k]));
    // 柱顶的那块收进时闪一下，然后静下来。
    const flash = (p: number, k: number) => at(p).stored.find((b) => b.island === k)?.flash ?? 0;
    expect(flash(times[1] + 0.02, 1)).toBeGreaterThan(0.5);
    expect(flash(1, 1)).toBe(0);
  });

  it("副本从真乃的柱子走到果穗的，再从果穗的走到冬优子和雾子的；沿路线连续地走，不跳", () => {
    const scenes = run();
    for (const [from, to] of [[0, 1], [1, 2], [1, 3]]) {
      const shown = scenes.flatMap((s, i) => (copyTo(s, to) ? [i] : []));
      expect(shown.length, `给第 ${to} 座岛的那份`).toBeGreaterThan(10);
      // 一段连着出现，不闪。
      expect(shown.at(-1)! - shown[0]).toBe(shown.length - 1);
      expect(dist(copyTo(scenes[shown[0]], to)!.position, memoryTop(from))).toBeLessThan(0.05);
      expect(dist(copyTo(scenes[shown.at(-1)!], to)!.position, memoryTop(to))).toBeLessThan(0.15);
      // 出发时出发的那位已经收进了，到了就收进她的柱子、这份不见了。
      expect(stored(scenes[shown[0]], from)).toBe(true);
      expect(stored(scenes[shown.at(-1)! + 1], to)).toBe(true);
      expect(copyTo(scenes[shown.at(-1)! + 1], to)).toBeUndefined();
      for (let n = 1; n < shown.length; n++) {
        const step = dist(copyTo(scenes[shown[n - 1]], to)!.position, copyTo(scenes[shown[n]], to)!.position);
        expect(step, `给第 ${to} 座岛的那份，p ${ps[shown[n]]}`).toBeLessThan(0.3);
      }
    }
  });

  it("转台在副本上桥之前已经接上，副本走过的桥面亮起来、之后一直亮着", () => {
    expect(at(0).turntable).toBeCloseTo(Math.PI / 2, 9);
    expect(at(0.3).turntable).toBeCloseTo(Math.PI / 2, 9);
    const scenes = run();
    scenes.forEach((s, i) => {
      if (copyTo(s, 1)) expect(s.turntable, `p ${ps[i]}`).toBe(0);
    });
    const turns = scenes.map((s) => s.turntable);
    expect(turns).toEqual([...turns].sort((a, b) => b - a));
    // 桥面一块块亮：副本走到哪亮到哪。
    const lit = (k: number) => scenes.map((s) => s.bridge[k]);
    for (const k of [0, 1]) {
      expect(lit(k)).toEqual([...lit(k)].sort((a, b) => a - b));
      expect(lit(k)[0]).toBe(0);
      expect(lit(k).at(-1)).toBe(1);
    }
    expect(first(scenes, (s) => s.bridge[0] > 0.5)).toBeLessThan(first(scenes, (s) => s.bridge[1] > 0.5));
    expect(first(scenes, (s) => s.bridge[0] > 0)).toBeGreaterThanOrEqual(first(scenes, (s) => !!copyTo(s, 1)));
  });

  it("台阶一级级升起来，在副本下台阶之前已经升好；副本走过的台阶亮起来", () => {
    const scenes = run();
    expect(at(0.6).steps.every((s) => s.rise === 0)).toBe(true);
    for (const [stair, to] of [[0, 2], [1, 3]]) {
      const mine = STEPS.flatMap((s, i) => (s.stair === stair ? [i] : []));
      expect(mine).toHaveLength(4);
      // 一级比一级晚升起来。
      const risen = mine.map((i) => first(scenes, (s) => s.steps[i].rise > 0));
      expect(risen).toEqual([...risen].sort((a, b) => a - b));
      expect(new Set(risen).size).toBe(4);
      scenes.forEach((s, n) => {
        if (copyTo(s, to)) for (const i of mine) expect(s.steps[i].rise, `p ${ps[n]}`).toBe(1);
      });
      const lit = mine.map((i) => first(scenes, (s) => s.steps[i].lit > 0.5));
      expect(lit).toEqual([...lit].sort((a, b) => a - b));
      for (const i of mine) expect(at(1).steps[i].lit).toBe(1);
    }
  });

  it("收到时一跳，真乃接住时往后仰，传话时转向对方，平时朝着镜头", () => {
    const pose = (p: number, k: number) => at(p).figures.find((f) => f.island === k)!;
    const facing = (from: number, to: number) => Math.atan2(STANDS[to][0] - STANDS[from][0], STANDS[to][2] - STANDS[from][2]);
    const same = (a: number, b: number) => expect(Math.abs(Math.atan2(Math.sin(a - b), Math.cos(a - b)))).toBeLessThan(1e-6);
    for (const k of ALL) {
      same(pose(0, k).yaw, cameraAt(0, desktop).azimuth);
      expect(pose(0, k).hop).toBe(0);
      expect(pose(0, k).reach).toBe(0);
    }
    expect(pose(0.18, 0).reach).toBe(1);
    expect(pose(0.18, 1).reach).toBe(0);
    const scenes = run();
    for (const k of [1, 2, 3]) {
      const arrive = first(scenes, (s) => stored(s, k));
      const hops = scenes.map((s) => s.figures.find((f) => f.island === k)!.hop);
      expect(Math.max(...hops.filter((_, i) => Math.abs(ps[i] - arrive) < 0.04))).toBeGreaterThan(0.8);
      expect(hops.filter((_, i) => Math.abs(ps[i] - arrive) > 0.06).every((h) => h === 0)).toBe(true);
    }
    // 真乃把它传给果穗时朝着果穗，冬优子、雾子收到时朝着果穗。
    same(pose(0.48, 0).yaw, facing(0, 1));
    same(pose(0.8, 2).yaw, facing(2, 1));
    same(pose(0.8, 3).yaw, facing(3, 1));
  });

  it("全景里几根光线把四根柱顶连起来", () => {
    expect(at(0.8).threads.every((t) => t.opacity === 0)).toBe(true);
    const end = at(1);
    expect(end.threads.length).toBeGreaterThanOrEqual(3);
    expect(end.threads.every((t) => t.opacity > 0.5)).toBe(true);
    // 每一位都连着。
    for (const k of ALL) expect(end.threads.some((t) => t.from === k || t.to === k)).toBe(true);
    expect(end.stored.map((b) => b.island).sort()).toEqual(ALL);
  });

  it("演员缺一位时，传给她的那一份、她收进柱子、她的动作和连到她的线都不出现，其他照常", () => {
    const full = run();
    run([0, 1, 3]).forEach((s, i) => {
      expect(copyTo(s, 2)).toBeUndefined();
      expect(stored(s, 2)).toBe(false);
      expect(s.figures.some((f) => f.island === 2)).toBe(false);
      expect(s.threads.some((t) => t.from === 2 || t.to === 2)).toBe(false);
      expect(s.copies).toEqual(full[i].copies.filter((c) => c.to !== 2));
      expect(s.stored).toEqual(full[i].stored.filter((b) => b.island !== 2));
      // 果穗传话时朝着在场的那一位（两位都在时朝着两人中间），别的动作照常。
      expect(s.figures.filter((f) => f.island !== 1)).toEqual(full[i].figures.filter((f) => f.island !== 1 && f.island !== 2));
      expect(s.message).toEqual(full[i].message);
      // 台阶照样升起；往她那里去的那段没人走过，不亮。
      s.steps.forEach((step, n) => expect(step).toEqual(STEPS[n].stair === 0 ? { ...full[i].steps[n], lit: 0 } : full[i].steps[n]));
    });
  });

  it("真乃不在时只剩场景：没有消息、副本、柱顶的块和连线，手机不亮", () => {
    run([1, 2, 3]).forEach((s) => {
      expect(s.message).toBeNull();
      expect(s.copies).toEqual([]);
      expect(s.stored).toEqual([]);
      expect(s.threads).toEqual([]);
      expect(s.phone).toBe(0);
      expect(s.bridge.every((b) => b === 0)).toBe(true);
      expect(s.figures.map((f) => f.island)).toEqual([1, 2, 3]);
      expect(s.figures.every((f) => f.hop === 0 && f.reach === 0)).toBe(true);
    });
  });
});
