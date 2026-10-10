// 第 5 幕里指针（和手指）留下的痕迹，慢慢消散，呼应「她会记住」。只记最近的一串点，着色器把它们连成
// 一道淡淡的光（light.ts）。纯函数，不碰 DOM。

export type TrailPoint = { x: number; y: number; /** 秒 */ t: number };

/** 一个点留多久（秒）。 */
export const TRAIL_LIFE = 1.6;
/** 最多记几个点；着色器的 uniform 数组也是这么长。 */
export const TRAIL_POINTS = 24;
/** 离上一个点不到这么远（像素）就不另记。 */
const MIN_STEP = 6;

const alive = (trail: readonly TrailPoint[], now: number) => trail.filter((p) => now - p.t < TRAIL_LIFE);

/** 指针移到 (x, y)：记下这一点，丢掉消散了的和太多的。 */
export function pushTrail(trail: readonly TrailPoint[], x: number, y: number, now: number): TrailPoint[] {
  const kept = alive(trail, now);
  const last = kept.at(-1);
  if (last && Math.hypot(x - last.x, y - last.y) < MIN_STEP) return kept;
  return [...kept, { x, y, t: now }].slice(-TRAIL_POINTS);
}

/** 现在还看得见的点，从早到晚；alpha 是亮度，刚留下的是 1，越早越淡，消散完就不在了。 */
export function liveTrail(trail: readonly TrailPoint[], now: number): { x: number; y: number; alpha: number }[] {
  return alive(trail, now).map((p) => ({ x: p.x, y: p.y, alpha: (1 - (now - p.t) / TRAIL_LIFE) ** 2 }));
}
