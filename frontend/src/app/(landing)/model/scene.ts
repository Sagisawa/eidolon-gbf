// 画面描述（spec「前端：落地页模型」）：给定滚动进度、视口和档位，算出这一刻的画面：在哪一幕、
// 幕内进度，白光、棱镜、出口附近的连续色散和每一道光的位置、宽度、颜色、强度，以及色散强度。
// 着色器层、CSS/SVG 层、DOM 层都只把它画出来，几何只在这里算一次，几层才对得齐。纯函数，不碰 DOM。
//
// 几何和时间线照搬原型拍板的做法（prototype/landing-page 的 scene.ts）：一道光统一表示成一条射线
// （起点、方向、长度）。第 1 幕里白光先移到棱镜的入射点，射进棱镜后从出口按色相扇出成一道道光；
// 扫过一遍把每种颜色依次点亮，最后 28 道光以同一个亮度停在扇面上。原型里第 1 幕结尾的「归队」
// （扇面拉直、排成组合顺序）属于第 2 幕的开场（ticket 05），这里还没有：第 1 幕之后舞台解开钉住，
// 整个画面跟着页面往上走。05 在第 1 幕和这一屏之间插入第 2 幕，并给 Scene 加上它要的字段。

import { layoutOf, qualityOf, type Tier } from "./tier";

export type Viewport = { w: number; h: number };
export type Point = readonly [x: number, y: number];

/** 一道光的固定属性：名单准备（spectrum.ts 的 lightsOf）在服务端算好。 */
export type BandLight = {
  id: string;
  /** 光晕色，`#rrggbb`：她的印象色按亮度反向补偿过（color.ts）。 */
  color: string;
  /** 光晕强度系数：太亮的压一点。 */
  gain: number;
  /** 光晕宽度的倍数：越暗晕得越开。 */
  spread: number;
  /** 分光时按色相出射的名次，0 是偏折最小的粉红。 */
  hueRank: number;
};

export type SceneInput = {
  lights: readonly BandLight[];
  /** 页面滚过的屏数：0 是第 0 幕开头，1 是舞台钉住、第 1 幕开始的地方。 */
  scroll: number;
  viewport: Viewport;
  tier: Tier;
  /** 滚动速度（屏/秒），调用方先平滑过。只影响色散。 */
  speed?: number;
  /** 指针在画面上的位置，-1 到 1，中间是 0；调用方先用弹簧平滑过（spring.ts）。只影响第 0 幕白光的角度。 */
  pointer?: { x: number; y: number };
  /** 秒，给白光尽头的呼吸用。 */
  time?: number;
};

export type Band = {
  id: string;
  /** 光晕色和光晕强度系数，原样来自 BandLight：分光以后只出现她们自己的颜色，没有中间色。 */
  color: string;
  gain: number;
  /** 在扇面上的位置，0 到 1（色相名次归一）：出口附近的连续色散按它在相邻两道光的颜色之间过渡。 */
  hue: number;
  /** 射线起点和单位方向。 */
  x: number;
  y: number;
  dx: number;
  dy: number;
  /** 射线长度，以及从起点算起多远才开始淡入（出口附近留给连续色散）。 */
  length: number;
  start: number;
  /** 白色光芯的宽度和光晕半径（像素）。 */
  core: number;
  halo: number;
  /** 0 到 1。超过一半算满强度，同屏最多 5 道，其余是余烬（拷问记录「角色与光」：满强度的最多 3 到 5 个）：
   * 第 1 幕里一个亮点依次扫过各种颜色，同时只亮两三道。 */
  intensity: number;
};

export type Scene = {
  /** 当前在哪一幕（0、1；第 1 幕之后是 2），和幕内进度 0 到 1。 */
  act: number;
  actProgress: number;
  /** 背景色，和页面的底色一样，画布淡入时看不出接缝。 */
  background: string;
  /** 白光：从画面外的 (x0, y0) 射到 (x1, y1)；tip 是尽头那团光的亮度。 */
  beam: { x0: number; y0: number; x1: number; y1: number; intensity: number; tip: number };
  /** 棱镜：三个顶点和出射点。 */
  prism: { apex: Point; left: Point; right: Point; exit: Point; intensity: number };
  /** 出口附近的连续色散：以出口为圆心、半径 radius 的扇形，中心角 angle、半张角 spread。 */
  fan: { x: number; y: number; angle: number; spread: number; radius: number; intensity: number };
  /** 每一道光，顺序和 lights 一样。 */
  bands: Band[];
  /** 色散强度 0 到 1：只在转场时出现，滚得越快越大。 */
  dispersion: number;
  /** DOM 上跟着时间线走的文字的不透明度。 */
  text: { act1: number };
};

/** 第 1 幕钉住滚过几屏。 */
export const ACT1_SCREENS = 3.2;
/** 舞台一共几屏：第 1 幕，加上解开钉住、整体往上走的一屏。DOM 按它定舞台的高度。 */
export const STAGE_SCREENS = ACT1_SCREENS + 1;
/** 页面的底色（landing.css 的 html、body 用同一个），画布淡入时看不出接缝。 */
const BACKGROUND = "#020203";

/** 第 1 幕结尾，28 道光停在扇面上的亮度：都看得见，又都不算满强度。 */
const SETTLED = 0.42;
/** 第 0 幕里指针能把白光转多少度。 */
const TILT = 6 * (Math.PI / 180);
const DEG = Math.PI / 180;

const clamp = (x: number, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const smooth = (a: number, b: number, x: number) => {
  const t = clamp((x - a) / (b - a));
  return t * t * (3 - 2 * t);
};
const easeInOut = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
/** 0 到 1 之间鼓起来的一座小山，两端正好是 0、中间是 1（sin(πt) 在 t = 1 时不是精确的 0）。 */
const hill = (t: number) => 4 * t * (1 - t);

/** 竖屏：白光从上往下射，扇面朝下。和 landing.css 的 `max-aspect-ratio: 10/11` 是同一条线。 */
const isPortrait = ({ w, h }: Viewport) => h > w * 1.1;

/** 第几幕、幕内进度。 */
function whereIs(scroll: number): { act: number; actProgress: number } {
  if (scroll < 1) return { act: 0, actProgress: clamp(scroll) };
  if (scroll < 1 + ACT1_SCREENS) return { act: 1, actProgress: (scroll - 1) / ACT1_SCREENS };
  return { act: 2, actProgress: clamp(scroll - 1 - ACT1_SCREENS) };
}

/**
 * 白光的锚点和棱镜。锚点在第 0 幕是白光的尽头（首屏 CSS 那一束的尽头，landing.css 的 .lp-beam），
 * 第 1 幕开头移到棱镜的入射点；棱镜是一个正三角形，顶点朝向和白光的方向有关。
 */
function geometry(vp: Viewport, entering: number) {
  const { w, h } = vp;
  const portrait = isPortrait(vp);
  const fwd: Point = portrait ? [0, 1] : [1, 0];
  const side: Point = portrait ? [-1, 0] : [0, 1];
  const rest: Point = portrait ? [w * 0.5, h * 0.3] : [w * 0.46, h * 0.66];
  const entry0: Point = portrait ? [w * 0.56, h * 0.17] : [w * 0.3, h * 0.42];
  const entry: Point = [lerp(rest[0], entry0[0], entering), lerp(rest[1], entry0[1], entering)];
  const s = portrait ? w * 0.24 : Math.min(w, h) * 0.17;
  const at = (u: number, v: number): Point => [
    entry[0] + fwd[0] * (u + 0.25 * s) + side[0] * (v + 0.144 * s),
    entry[1] + fwd[1] * (u + 0.25 * s) + side[1] * (v + 0.144 * s),
  ];
  return {
    fwd,
    entry,
    apex: at(0, -0.577 * s),
    left: at(-0.5 * s, 0.289 * s),
    right: at(0.5 * s, 0.289 * s),
    exit: at(0.25 * s, -0.144 * s),
    fanLength: portrait ? h * 1.05 : w * 1.15,
    fanRadius: Math.min(portrait ? 200 : 300, (portrait ? h : w) * 0.24),
    baseAngle: Math.atan2(fwd[1], fwd[0]) + (portrait ? 5 : 9) * DEG,
    spreadMax: (portrait ? 13 : 15) * DEG,
    /** 指针让白光转的方向：光源跟着指针走（电脑上上下，竖屏上左右）。 */
    tiltOf: (pointer: { x: number; y: number }) => (portrait ? pointer.x : -pointer.y) * TILT,
    back: Math.max(w, h) * 1.5,
  };
}

type Moment = {
  /** 第 1 幕的幕内进度。 */
  p: number;
  pointer: { x: number; y: number };
  time: number;
  speed: number;
  /** 舞台解开钉住以后整个画面往上走的像素。 */
  lift: number;
  samples: number;
};

/** 第 1 幕进度为 p 时的画面（第 0 幕就是 p = 0）。 */
function picture(lights: readonly BandLight[], vp: Viewport, m: Moment): Omit<Scene, "act" | "actProgress"> {
  const { p } = m;
  const entering = easeInOut(smooth(0, 0.14, p));
  const g = geometry(vp, entering);

  // —— 第 1 幕的时间线。
  const prismIn = smooth(0.02, 0.14, p);
  const open = easeInOut(smooth(0.12, 0.46, p));
  const fanIn = smooth(0.1, 0.2, p);
  // 一个亮点从偏折最小的颜色扫到偏折最大的，依次点亮；扫过以后大家停在同一个亮度上。
  const n = lights.length;
  const sweep = lerp(-3, n + 2, smooth(0.14, 0.7, p));
  const settle = smooth(0.62, 0.8, p);

  const bands: Band[] = lights.map((light) => {
    const hue = n > 1 ? light.hueRank / (n - 1) : 0.5;
    const angle = g.baseAngle + (hue - 0.5) * 2 * g.spreadMax * open;
    const lit = 0.1 + 0.9 * Math.exp(-(((light.hueRank - sweep) / 1.7) ** 2));
    return {
      id: light.id,
      color: light.color,
      gain: light.gain,
      hue,
      x: g.exit[0],
      y: g.exit[1] - m.lift,
      dx: Math.cos(angle),
      dy: Math.sin(angle),
      length: g.fanLength * (0.15 + 0.85 * open),
      start: g.fanRadius * 0.45,
      core: 1.1,
      halo: 9 * light.spread,
      intensity: Math.max(lerp(0.1, SETTLED, settle), lit) * fanIn,
    };
  });

  // 白光：第 0 幕随指针转一点，移向棱镜时转回来，射进棱镜时正好对准入射点。
  const tilt = g.tiltOf(m.pointer) * (1 - entering);
  const dir: Point = [
    Math.cos(tilt) * g.fwd[0] - Math.sin(tilt) * g.fwd[1],
    Math.sin(tilt) * g.fwd[0] + Math.cos(tilt) * g.fwd[1],
  ];
  const breathe = 0.75 + 0.25 * Math.sin(m.time * 1.6);

  // 色散只在转场时出现：白光移向棱镜、扇面张开；滚得越快分得越开，停下来时只剩一点。
  const transition = Math.max(hill(smooth(0, 0.14, p)), hill(smooth(0.12, 0.46, p)));
  const pace = Math.min(1, 0.25 + Math.abs(m.speed) / 2);
  const up = (pt: Point): Point => [pt[0], pt[1] - m.lift];

  return {
    background: BACKGROUND,
    beam: {
      x0: g.entry[0] - dir[0] * g.back,
      y0: g.entry[1] - dir[1] * g.back - m.lift,
      x1: g.entry[0],
      y1: g.entry[1] - m.lift,
      intensity: 1,
      tip: (1 - prismIn) * breathe,
    },
    prism: { apex: up(g.apex), left: up(g.left), right: up(g.right), exit: up(g.exit), intensity: prismIn },
    fan: { x: g.exit[0], y: g.exit[1] - m.lift, angle: g.baseAngle, spread: g.spreadMax * open, radius: g.fanRadius, intensity: fanIn },
    bands,
    dispersion: m.samples > 1 ? transition * pace : 0,
    text: { act1: smooth(0.4, 0.48, p) },
  };
}

export function describeScene(input: SceneInput): Scene {
  const { lights, scroll, viewport, tier } = input;
  const where = whereIs(scroll);
  const still = { x: 0, y: 0 };
  // 「减少动态效果」档和静态档：任何进度下都是第 1 幕的完成态，定格、不呼吸、不随指针和速度变。
  if (layoutOf(tier) === "still") {
    return { ...where, ...picture(lights, viewport, { p: 1, pointer: still, time: 0, speed: 0, lift: 0, samples: 1 }) };
  }
  return {
    ...where,
    ...picture(lights, viewport, {
      p: clamp((scroll - 1) / ACT1_SCREENS),
      pointer: input.pointer ?? still,
      time: input.time ?? 0,
      speed: input.speed ?? 0,
      lift: Math.max(0, scroll - 1 - ACT1_SCREENS) * viewport.h,
      samples: qualityOf(tier, false).samples,
    }),
  };
}
