import { describe, expect, it } from "vitest";

import { liveTrail, pushTrail, TRAIL_LIFE, TRAIL_POINTS, type TrailPoint } from "./trail";

describe("指针痕迹：第 5 幕里指针留下的痕迹慢慢消散", () => {
  it("刚留下的最亮，越早留下的越淡", () => {
    let trail: TrailPoint[] = [];
    trail = pushTrail(trail, 0, 0, 0);
    trail = pushTrail(trail, 50, 0, 0.3);
    trail = pushTrail(trail, 100, 0, 0.6);
    const live = liveTrail(trail, 0.6);
    expect(live.map((p) => p.x)).toEqual([0, 50, 100]);
    expect(live[2].alpha).toBe(1);
    expect(live[0].alpha).toBeLessThan(live[1].alpha);
    expect(live[1].alpha).toBeLessThan(live[2].alpha);
  });

  it("过了一段时间就完全消失", () => {
    const trail = pushTrail([], 10, 10, 0);
    expect(liveTrail(trail, TRAIL_LIFE * 0.5)[0].alpha).toBeGreaterThan(0);
    expect(liveTrail(trail, TRAIL_LIFE + 0.01)).toEqual([]);
    expect(pushTrail(trail, 300, 300, TRAIL_LIFE + 0.01).map((p) => p.x)).toEqual([300]);
  });

  it("挪得太近的不另记一点；最多记这么多点，满了丢掉最早的", () => {
    expect(pushTrail(pushTrail([], 0, 0, 0), 1, 1, 0.01)).toHaveLength(1);
    let trail: TrailPoint[] = [];
    for (let k = 0; k < TRAIL_POINTS + 10; k++) trail = pushTrail(trail, k * 20, 0, k * 0.01);
    expect(trail).toHaveLength(TRAIL_POINTS);
    expect(trail.at(-1)!.x).toBe((TRAIL_POINTS + 9) * 20);
  });
});
