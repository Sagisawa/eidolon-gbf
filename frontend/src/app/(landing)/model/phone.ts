// 第 4 幕的手机（.scratch/landing-call-phone 票 03）：落地页模型给出手机在画面上的位置、绕竖轴的转角、缩放、
// 屏幕亮度、振动和停稳以后屏幕的矩形。three.js 的相机（phoneLayer.ts）和 DOM 上的来电界面都照它摆，两边是同一个
// 出处。纯函数，不碰 DOM。
//
// 尺寸是手机模型（public/landing/phone/，Ranguel 的 iPhone 17 Pro）量出来的，单位毫米。换模型时照新模型改。

import type { Viewport } from "./scene";

/** 机身、屏幕的尺寸（毫米）。屏幕在机身正中；屏幕平面在机身中心往前 screenZ 处。 */
export const PHONE_MM = {
  w: 73.1,
  h: 150,
  /** 侧边的厚度：前玻璃到背面玻璃，不含相机那一条。 */
  depth: 8.8,
  screen: { w: 66.8, h: 144.9, r: 11.7, z: 3.4 },
} as const;

/** 停稳以后屏幕在画面上的矩形：中心 (x, y)，宽高，圆角（像素）。 */
export type ScreenRect = { x: number; y: number; w: number; h: number; r: number };

export type PhoneState = {
  /** 手机（机身中心）在画面上的位置，像素。 */
  x: number;
  y: number;
  /** 机身的高度，像素：缩放就是它。 */
  height: number;
  /** 绕竖轴的转角（弧度）：π/2 是侧面（侧边朝着访客），π 是背面，2π 是正面。 */
  yaw: number;
  /** 屏幕亮度：0 熄屏，1 亮起。 */
  screen: number;
  /** 手机的不透明度：她的光交给它时淡入，去第 5 幕时淡出。 */
  opacity: number;
  /** 振动的位移（像素）：只在响铃时有。手机和屏幕上的 DOM 一起抖。 */
  shake: { x: number; y: number };
  /** 停稳以后屏幕的矩形，DOM 上的来电界面摆在这里。 */
  rect: ScreenRect;
  /** 停稳以后机身占的地方：标题在它上面，正文在它下面。 */
  bounds: { left: number; top: number; right: number; bottom: number };
};

const clamp = (x: number, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const smooth = (a: number, b: number, x: number) => {
  const t = clamp((x - a) / (b - a));
  return t * t * (3 - 2 * t);
};
const easeInOut = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);

// —— 第 4 幕的时间线（幕内进度）。
/** 她的光挪到画面中间、收窄成手机侧边那么长的一条竖线。 */
export const NARROW: readonly [number, number] = [0.02, 0.14];
/** 交接：光熄掉，侧着的手机在同一个地方淡入。 */
export const HANDOFF: readonly [number, number] = [0.12, 0.18];
/** 转身：侧面转到背面，在背面停一会儿，再转到正面；同时从 TURN_SCALE 放大到停稳的大小。 */
const TO_BACK: readonly [number, number] = [0.18, 0.34];
const AT_BACK: readonly [number, number] = [0.34, 0.42];
const TO_FRONT: readonly [number, number] = [0.42, 0.64];
/** 在背面停留时慢慢多转的一点（弧度），停着也不是死的。 */
const BACK_DRIFT = 0.06;
/** 转身开始时的大小（相对停稳的大小）。 */
export const TURN_SCALE = 0.86;
/** 屏幕亮起。 */
const SCREEN_ON: readonly [number, number] = [0.64, 0.7];
/** 来电界面、标题和正文显出来；铃声（光脉冲和振动）同时开始。 */
export const CALL_SHOWN: readonly [number, number] = [0.68, 0.74];

/** 第 4 幕进度为 p 时手机的转角（弧度）：π/2 → π（停一会儿）→ 2π。 */
function yawAt(p: number): number {
  const back = Math.PI + BACK_DRIFT * smooth(AT_BACK[0], AT_BACK[1], p);
  if (p < AT_BACK[0]) return lerp(Math.PI / 2, Math.PI, easeInOut(smooth(TO_BACK[0], TO_BACK[1], p)));
  return lerp(back, 2 * Math.PI, easeInOut(smooth(TO_FRONT[0], TO_FRONT[1], p)));
}

/** 第 4 幕进度为 p 时手机的大小（相对停稳的大小）。 */
export const scaleAt = (p: number) => lerp(TURN_SCALE, 1, easeInOut(smooth(TO_BACK[0], TO_FRONT[1], p)));

/**
 * 第 4 幕进度为 p 时的手机。`shake` 是这一刻的振动位移，调用方按铃声算好（只在响铃时有）。
 * 静止版式由调用方传 p = 1：一开始就是正面、亮屏。
 */
export function phoneAt(vp: Viewport, p: number, shake: { x: number; y: number }): PhoneState {
  const rest = phoneRest(vp);
  return {
    ...rest,
    height: rest.height * scaleAt(p),
    yaw: yawAt(p),
    screen: smooth(SCREEN_ON[0], SCREEN_ON[1], p),
    opacity: smooth(HANDOFF[0] + 0.01, HANDOFF[1] - 0.01, p),
    shake,
  };
}

/** 竖屏：和 scene.ts 的 isPortrait 是同一条线。 */
const isPortrait = ({ w, h }: Viewport) => h > w * 1.1;

/**
 * 停稳的地方：画面正中。机身高度占画面高度的 64%（竖屏 56%），上下各留出两成左右给标题和正文；
 * 窄的画面上再按宽度收一收，机身左右不出画面。
 */
export function phoneRest(vp: Viewport): Pick<PhoneState, "x" | "y" | "height" | "rect" | "bounds"> {
  const portrait = isPortrait(vp);
  const aspect = PHONE_MM.h / PHONE_MM.w;
  const height = Math.min(vp.h * (portrait ? 0.56 : 0.64), vp.w * (portrait ? 0.62 : 0.5) * aspect);
  const x = vp.w / 2;
  const y = vp.h / 2;
  const mm = height / PHONE_MM.h;
  const s = PHONE_MM.screen;
  const width = PHONE_MM.w * mm;
  return {
    x,
    y,
    height,
    rect: { x, y, w: s.w * mm, h: s.h * mm, r: s.r * mm },
    bounds: { left: x - width / 2, top: y - height / 2, right: x + width / 2, bottom: y + height / 2 },
  };
}
