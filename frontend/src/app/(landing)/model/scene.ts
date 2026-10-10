// 画面描述（spec「前端：落地页模型」）：给定滚动进度、视口和档位，算出这一刻的画面：在哪一幕、
// 幕内进度，白光、棱镜、出口附近的连续色散和每一道光的位置、宽度、颜色、强度，以及色散强度。
// 着色器层、CSS/SVG 层、DOM 层都只把它画出来，几何只在这里算一次，几层才对得齐。纯函数，不碰 DOM。
//
// 几何和时间线照搬原型拍板的做法（prototype/landing-page 的 scene.ts）：一道光统一表示成一条射线
// （起点、方向、长度）。第 1 幕里白光先移到棱镜的入射点，射进棱镜后从出口按色相扇出成一道道光；
// 扫过一遍把每种颜色依次点亮，最后 28 道光以同一个亮度停在扇面上。第 2 幕先「归队」：扇面拉直成
// 按组合顺序排满一屏的竖线（光谱尺），再放大到横滚的轨道上，每个组合一屏，组合之间整页推入。
// 三个状态之间逐道插值，就是「扇形 → 拉直 → 归队」的转场。第 3、4 幕里一道道光收成说话那一位的
// 一道，她说日语、打来电话；第 5 幕光又散开，一件事从一位传到另一位；第 7 幕收拢成一块手机屏幕。
// 各幕占几屏见 timeline.ts。

import type { Call } from "./interaction";
import { averageOklab, mixOklab } from "./oklab";
import { layoutOf, qualityOf, type Tier } from "./tier";
import {
  REGROUP_SCREENS,
  SEG_SCREENS,
  spanOf,
  timelineOf,
  whereIs,
  ZOOM_SCREENS,
  type ActSpan,
  type Timeline,
} from "./timeline";

export type Viewport = { w: number; h: number };
export type Point = readonly [x: number, y: number];

/** 一道光的固定属性：名单准备（spectrum.ts 的 lightsOf）在服务端算好。顺序就是光谱的顺序。 */
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
  /** 聚焦到她时的背景：她的极深同色相。 */
  deep: string;
  /** 她在光谱的第几个组合（从 0 起）、组合里第几位，组合有几人。 */
  unit: number;
  slot: number;
  unitSize: number;
};

export type SceneInput = {
  lights: readonly BandLight[];
  /** 页面滚过的屏数（timeline.ts）：0 是第 0 幕开头，1 是舞台钉住、第 1 幕开始的地方。 */
  scroll: number;
  viewport: Viewport;
  tier: Tier;
  /** 滚动速度（屏/秒），调用方先平滑过。只影响色散。 */
  speed?: number;
  /** 指针在画面上的位置，-1 到 1，中间是 0；调用方先用弹簧平滑过（spring.ts）。只影响第 0 幕白光的角度。 */
  pointer?: { x: number; y: number };
  /** 秒，给白光尽头的呼吸用。 */
  time?: number;
  /** 第 2 幕的横移量（组合数），调用方用弹簧把上一帧的 `spectrum.trackTarget` 平滑过；不给时就是目标本身。 */
  track?: number;
  /** 第 2 幕里聚焦到谁：偶像 → 聚焦的程度 0 到 1，调用方让它随时间淡入淡出（同时可以有一位在淡出、一位在淡入）。 */
  focus?: Readonly<Record<string, number>>;
  /** 第 2 幕名牌上名字占的竖直区间（视口坐标，舞台钉住时），光芯在那里断开。DOM 层量好了传进来。 */
  nameGaps?: Readonly<Record<string, readonly [top: number, bottom: number]>>;
  /** 第 3、4 幕里说话、打来电话的那一位；不给或者她不在名单里时，是光谱里的第一位。 */
  speaker?: string;
  /** 第 4 幕的来电接到哪一步了（交互 reducer 的 `call.phase`）；不给时在响。 */
  call?: Call["phase"];
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
  /** 光芯在这一段（沿射线的距离）断开：名牌上的名字压在光上时，名字处只留光晕。相等时不断开。 */
  gap0: number;
  gap1: number;
  /** 白色光芯的宽度和光晕半径（像素）。 */
  core: number;
  halo: number;
  /** 0 到 1。超过一半算满强度，同屏最多 5 道，其余是余烬（拷问记录「角色与光」：满强度的最多 3 到 5 个）：
   * 第 1 幕里一个亮点依次扫过各种颜色，同时只亮两三道。 */
  intensity: number;
};

/** 第 2 幕「光谱」DOM 要跟着走的部分。 */
export type SpectrumState = {
  /** 横移量（组合数）：0 是第一个组合在画面里，1 是第二个……DOM 的轨道平移 `-track` 屏。 */
  track: number;
  /** 横移的目标，调用方用弹簧追它，下一帧作为 `track` 传回来。 */
  trackTarget: number;
  /** 当前的组合（底部的组合名、跳转按钮的当前项）。 */
  unit: number;
  /** 该挂立绘的那一位：光谱停稳、聚焦的是当前组合的人时才有。 */
  stand: string | null;
};

/** 一颗传话的光点：沿二次贝塞尔弧线 from → to（控制点 ctrl，视口坐标，已经减去横移）走到 t 处，
 * 现在在 (x, y)；颜色从这段路起点的那一位渐变到终点的那一位。 */
export type Relay = { x: number; y: number; t: number; from: Point; ctrl: Point; to: Point; color: string; intensity: number };

/** 第 5 幕「记忆」。 */
export type MemoryState = {
  /** 横移（像素）：布景（两屏宽，memoryWorld）往左移了这么多。DOM 上的连线跟着它移。 */
  pan: number;
  /** 传话的光点，顺序和 memoryWorld 的 arcs 一样：先是发送的那一位传给接收的那一位，再是她传给另外三位。 */
  relays: Relay[];
  /** 每段光路（DOM 上的连线）画到了哪儿，0 到 1，顺序同上：光点走到哪儿，连线就画到哪儿。 */
  paths: number[];
  /** 指针在这一幕留下慢慢消散的痕迹（trail.ts）。 */
  trail: boolean;
};

/** 第 3 幕里的一句话：竖排的日语原文一列，和底下的一句中文字幕。 */
export type TalkLine = {
  /** 原文这一列的不透明度：出来了就一直留着。 */
  ja: number;
  /** 字幕被光扫到了哪儿，0 到 1：DOM 上扫过的部分显出来，扫光的亮边就在这里。 */
  sweep: number;
  /** 字幕的不透明度：下一句出来时这一句收掉，同一时刻只看得到一句（静止版式里几句都在）。 */
  subtitle: number;
};

/** 第 4 幕的来电。 */
export type CallState = {
  /** 光脉冲 0 到 1：铃声在画面上就是它，一阵一阵的。她的光和背景跟着亮。 */
  pulse: number;
  /** 画面振动的位移（像素）：响的时候抖，停的时候不动。 */
  shake: { x: number; y: number };
};

export type Scene = {
  /** 当前在哪一幕，和幕内进度 0 到 1（timeline.ts）。幕名轨亮到这一格。 */
  act: number;
  actProgress: number;
  /** 背景色。平时和页面的底色一样，画布淡入时看不出接缝；聚焦时过渡到她的极深底色。 */
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
  /** 第 2 幕：横移、当前组合、立绘。其他幕是 null。 */
  spectrum: SpectrumState | null;
  /** 第 5 幕：传话的光点、横移、连线的描边进度、指针痕迹。第 5 幕从下面进来的那一屏（光谱解开钉住）里
   * 已经是第 5 幕开头的样子，DOM 上的布景进到画面时就对得上；其他幕是 null。 */
  memory: MemoryState | null;
  /** 第 3 幕：每一句话的原文、扫光和字幕；第 4 幕里是说完的样子（第 3 幕的字在第 4 幕开头淡出）。其他幕是 null。 */
  talk: { lines: TalkLine[] } | null;
  /** 第 4 幕：光脉冲和振动。其他幕是 null。 */
  call: CallState | null;
  /** 第 7 幕的手机屏幕：中心 (x, y)，半宽 w、半高 h，圆角 r；亮度 0 到 1，1 是全站最亮的时候。 */
  screen: { x: number; y: number; w: number; h: number; r: number; intensity: number };
  /** DOM 上跟着时间线走的部分的不透明度：第 1 幕的文字，第 2 幕的名牌，第 3 幕的文字，第 4 幕的来电画面，
   * 第 7 幕的文字和行动按钮。 */
  text: { act1: number; plates: number; act3: number; act4: number; act7: number };
};

/** 页面的底色（landing.css 的 html、body 用同一个），画布淡入时看不出接缝。 */
const BACKGROUND = "#020203";

/** 第 1 幕结尾，28 道光停在扇面上的亮度：都看得见，又都不算满强度。 */
const SETTLED = 0.42;
/** 第 2 幕里不在画面中间的组合、聚焦时其余的人：余烬的亮度。 */
const EMBER = 0.14;
/** 第 2 幕里停在画面中间的组合的亮度。 */
const LIT = 0.82;
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

/** 左侧幕名轨占的宽度（landing.css 的 --lp-rail），名牌和光谱尺都让开它。 */
const railWidth = ({ w }: Viewport) => (w < 640 ? 36 : 72);

/** 光谱里有几个组合。 */
export const unitCount = (lights: readonly BandLight[]) => lights.reduce((n, l) => Math.max(n, l.unit + 1), 0);

/**
 * 第 2 幕横滚轨道上，第 u 个组合第 j 位（共 n 位）的横坐标，轨道没有平移时。每个组合占一屏，
 * 成员在幕名轨右边均匀排开。DOM 的名牌按它摆（LightStage 量视口时写进去），光也按它画。
 */
export function slotX(vp: Viewport, u: number, j: number, n: number): number {
  const left = railWidth(vp) + vp.w * 0.06;
  const right = vp.w * 0.06;
  return u * vp.w + left + ((j + 0.5) / n) * (vp.w - left - right);
}

/** 光谱尺：全部的光按光谱的顺序排满一屏，组合之间多留一点空。 */
function rulerX(vp: Viewport, lights: readonly BandLight[], i: number): number {
  const left = railWidth(vp) + vp.w * 0.05;
  const right = vp.w * 0.05;
  const gap = 0.9;
  const slots = lights.length + (unitCount(lights) - 1) * gap;
  const k = i + lights[i].unit * gap;
  return left + ((k + 0.5) / slots) * (vp.w - left - right);
}

/**
 * 横移的目标（组合数）。停留时也慢慢漂一点，推入时用缓动加速走完剩下的一屏；push 是推入的劲头
 * （0 到 1 再回到 0），给色散用。`seg` 是放大以后滚过的段数。
 */
function trackTarget(seg: number, units: number): { pos: number; push: number } {
  const last = units - 1;
  const s = clamp(seg, 0, units);
  const k = Math.min(Math.floor(s), last);
  const local = s - k;
  if (k >= last) return { pos: last + Math.min(local, 1) * 0.04, push: 0 };
  const HOLD = 0.55;
  const DRIFT = 0.08;
  if (local < HOLD) return { pos: k + (local / HOLD) * DRIFT, push: 0 };
  const t = (local - HOLD) / (1 - HOLD);
  return { pos: k + DRIFT + easeInOut(t) * (1 - DRIFT), push: hill(t) };
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
  /** 色散的劲头：滚动速度换算成 0 到 1。 */
  pace: number;
  samples: number;
};

type Picture = Omit<Scene, "act" | "actProgress">;

/** 没有手机屏幕。 */
const NO_SCREEN: Scene["screen"] = { x: 0, y: 0, w: 0, h: 0, r: 0, intensity: 0 };
/** 第 0 到 2 幕以外，白光、棱镜、连续色散都熄着。 */
const QUIET_TEXT: Scene["text"] = { act1: 0, plates: 0, act3: 0, act4: 0, act7: 0 };

/** 第 1 幕进度为 p 时的画面（第 0 幕就是 p = 0）。 */
function act1Picture(lights: readonly BandLight[], vp: Viewport, m: Moment): Picture {
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
      y: g.exit[1],
      dx: Math.cos(angle),
      dy: Math.sin(angle),
      length: g.fanLength * (0.15 + 0.85 * open),
      start: g.fanRadius * 0.45,
      gap0: 0,
      gap1: 0,
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

  return {
    background: BACKGROUND,
    beam: {
      x0: g.entry[0] - dir[0] * g.back,
      y0: g.entry[1] - dir[1] * g.back,
      x1: g.entry[0],
      y1: g.entry[1],
      intensity: 1,
      tip: (1 - prismIn) * breathe,
    },
    prism: { apex: g.apex, left: g.left, right: g.right, exit: g.exit, intensity: prismIn },
    fan: { x: g.exit[0], y: g.exit[1], angle: g.baseAngle, spread: g.spreadMax * open, radius: g.fanRadius, intensity: fanIn },
    bands,
    dispersion: m.samples > 1 ? transition * m.pace : 0,
    spectrum: null,
    memory: null,
    talk: null,
    call: null,
    screen: NO_SCREEN,
    text: { ...QUIET_TEXT, act1: smooth(0.4, 0.48, p) },
  };
}

type Act2Input = {
  /** 第 2 幕开始后滚过的屏数，包括最后解开钉住的那一屏。 */
  q: number;
  /** 第 2 幕钉住的长度（不含解开钉住的那一屏）。 */
  length: number;
  track?: number;
  focus: Readonly<Record<string, number>>;
  nameGaps: Readonly<Record<string, readonly [number, number]>>;
};

/** 第 2 幕：扇面（第 1 幕的完成态）→ 光谱尺 → 横滚轨道。 */
function act2Picture(lights: readonly BandLight[], vp: Viewport, m: Moment, a: Act2Input): Picture {
  const fan = act1Picture(lights, vp, { ...m, p: 1 });
  const n = lights.length;
  const units = unitCount(lights);
  const regroup = smooth(0, REGROUP_SCREENS, a.q);
  const zoom = smooth(REGROUP_SCREENS, REGROUP_SCREENS + ZOOM_SCREENS, a.q);
  const target = trackTarget((a.q - REGROUP_SCREENS - ZOOM_SCREENS) / SEG_SCREENS, units);
  const track = a.track ?? target.pos;
  const current = clamp(Math.round(track), 0, units - 1);
  /** 解开钉住：名牌跟着舞台往上走。竖线本来就铺满整屏，不跟着走（不然下面露出一截黑，接着第 5 幕的光
   * 又从头铺满）；只有名字处的断口跟着名牌走。 */
  const lift = Math.max(0, a.q - a.length) * vp.h;
  /** 光谱停稳在轨道上（放大完、还没解开钉住）：聚焦只在这时起作用。 */
  const settled = smooth(0.8, 1, zoom) * (a.q < a.length ? 1 : 0);

  // 聚焦：权重加起来最多是 1；其余的人按别人被聚焦的程度降成余烬。
  const weights = lights.map((l) => clamp(a.focus[l.id] ?? 0) * settled);
  const total = Math.min(1, weights.reduce((s, w) => s + w, 0));
  const deep = averageOklab(lights.map((l, i) => [l.deep, weights[i]] as const));
  const background = deep ? mixOklab(BACKGROUND, deep, total) : BACKGROUND;

  // 逐道错开一点，转场不是整齐划一地动：第 k 道在 [k·s, k·s + 1 − (n−1)·s] 里走完。
  const stagger = (k: number, t: number, s: number) => smooth(k * s, k * s + 1 - Math.max(n - 1, 0) * s, t);
  const gapIn = smooth(0.6, 1, zoom);

  const bands: Band[] = lights.map((light, i) => {
    const A = fan.bands[i];
    const tb = easeInOut(stagger(i, regroup, 0.012));
    const tc = easeInOut(stagger(i, zoom, 0.006));
    // 同屏满强度的不超过 5 道：一个组合超过 5 人时，整个组合压在半强度。
    const full = light.unitSize > 5 ? 0.5 : 1;
    // 光谱尺上：第一个组合亮着，预告接下来从这里开始。
    const rulerI = light.unit === 0 ? 0.95 * full : 0.34;
    // 轨道上：离画面中间越远的组合越暗，推入的途中两个组合交接，同屏满强度的不超过一个组合。
    const near = 1 - smooth(0.15, 0.5, Math.abs(track - light.unit));
    const others = total - weights[i];
    const dim = (1 + 0.12 * weights[i]) * lerp(1, 0.22, clamp(others));
    const trackI = lerp(EMBER, LIT * full, near) * dim;
    const x = lerp(lerp(A.x, rulerX(vp, lights, i), tb), slotX(vp, light.unit, light.slot, light.unitSize) - track * vp.w, tc);
    let dx = lerp(A.dx, 0, tb);
    let dy = lerp(A.dy, 1, tb);
    const dl = Math.hypot(dx, dy) || 1;
    dx /= dl;
    dy /= dl;
    const oy = lerp(A.y, -40, tb);
    const name = a.nameGaps[light.id];
    // 名字的区间换算成沿竖线的距离，从中间往两头张开。
    const g0 = name ? name[0] - lift - oy : 0;
    const g1 = name ? name[1] - lift - oy : 0;
    const mid = (g0 + g1) / 2;
    return {
      ...A,
      x,
      y: oy,
      dx: tb >= 1 ? 0 : dx,
      dy: tb >= 1 ? 1 : dy,
      length: lerp(A.length, vp.h + 80, tb),
      start: lerp(A.start, -200, tb),
      gap0: name && gapIn > 0 ? lerp(mid, g0, gapIn) : 0,
      gap1: name && gapIn > 0 ? lerp(mid, g1, gapIn) : 0,
      core: lerp(lerp(A.core, 0.9, tb), 1.4, tc),
      halo: lerp(lerp(A.halo, Math.max(5, vp.w / 150) * light.spread, tb), 46 * light.spread, tc),
      intensity: lerp(lerp(A.intensity, rulerI, tb), trackI, tc),
    };
  });

  // 白光和棱镜在拉直的前半段熄掉：白光已经变成了一道道光的光芯。
  const fade = 1 - smooth(0, 0.5, regroup);
  const transition = Math.max(hill(regroup), 0.55 * hill(zoom), 0.4 * target.push);
  const strongest = weights.reduce((best, w, i) => (w > (best < 0 ? 0 : weights[best]) ? i : best), -1);
  const standOk =
    strongest >= 0 &&
    weights[strongest] > 0.5 &&
    zoom >= 1 &&
    a.q < a.length &&
    target.push < 0.05 &&
    Math.abs(track - current) < 0.15 &&
    lights[strongest].unit === current;

  return {
    background,
    beam: { ...fan.beam, intensity: fan.beam.intensity * fade, tip: 0 },
    prism: { ...fan.prism, intensity: fan.prism.intensity * fade },
    fan: { ...fan.fan, intensity: fan.fan.intensity * fade },
    bands,
    dispersion: m.samples > 1 ? transition * m.pace : 0,
    spectrum: { track, trackTarget: target.pos, unit: current, stand: standOk ? lights[strongest].id : null },
    memory: null,
    talk: null,
    call: null,
    screen: NO_SCREEN,
    text: { ...QUIET_TEXT, act1: 1 - smooth(0, 0.3, regroup), plates: smooth(0.45, 0.9, zoom) },
  };
}

/** 白光、棱镜、连续色散都熄了的画面，光按 `bands` 摆。 */
function quiet(lights: readonly BandLight[], vp: Viewport, bands: Band[]): Picture {
  const fan = act1Picture(lights, vp, { p: 1, pointer: { x: 0, y: 0 }, time: 0, pace: 0, samples: 1 });
  return {
    ...fan,
    beam: { ...fan.beam, intensity: 0, tip: 0 },
    prism: { ...fan.prism, intensity: 0 },
    fan: { ...fan.fan, intensity: 0 },
    bands,
    dispersion: 0,
    spectrum: null,
    memory: null,
    talk: null,
    call: null,
    screen: NO_SCREEN,
    text: QUIET_TEXT,
  };
}

/** 两组光之间逐道插值（形状一样，颜色不变）。 */
function blend(a: Band[], b: Band[], t: number): Band[] {
  if (t <= 0) return a;
  if (t >= 1) return b;
  return a.map((x, i) => {
    const y = b[i];
    const dx = lerp(x.dx, y.dx, t);
    const dy = lerp(x.dy, y.dy, t);
    const dl = Math.hypot(dx, dy) || 1;
    return {
      ...x,
      x: lerp(x.x, y.x, t),
      y: lerp(x.y, y.y, t),
      dx: dx / dl,
      dy: dy / dl,
      length: lerp(x.length, y.length, t),
      start: lerp(x.start, y.start, t),
      gap0: lerp(x.gap0, y.gap0, t),
      gap1: lerp(x.gap1, y.gap1, t),
      core: lerp(x.core, y.core, t),
      halo: lerp(x.halo, y.halo, t),
      intensity: lerp(x.intensity, y.intensity, t),
    };
  });
}

/** 第 5 幕布景里的一段光路：从 source 那一位的光传到 target 那一位的光，二次贝塞尔弧线（布景坐标）。 */
export type MemoryArc = { source: string; target: string; from: Point; ctrl: Point; to: Point };

export type MemoryWorld = {
  /** 每一道光在布景里的横坐标，顺序和 lights 一样。 */
  lines: { id: string; color: string; x: number }[];
  sender: string | null;
  receiver: string | null;
  /** 发送的那一位传给接收的那一位的光路。 */
  arc: MemoryArc;
  /** 接收的那一位再传给另外三位的光路。 */
  spreads: MemoryArc[];
  /** 全部光路，先 arc 后 spreads；DOM 上的连线、着色器的光点都按这个顺序。 */
  arcs: MemoryArc[];
};

/**
 * 第 5 幕的布景，单位是视口：两屏宽（x 从 0 到 2）、一屏高（y 从 0 到 1）。全部的光按光谱的顺序竖着排开。
 * 一件事从光谱里的第一位（发送的那一位）传给后半段里和她颜色差得最开的一位（接收的那一位），沿一条
 * 鼓在上方的弧线走；再从她那里传开，落到她两边的另外三位身上（「我对一位偶像说的事，别的偶像也会知道」）。
 * 着色器（光、光点）和 DOM 上的 SVG（连线，静态档里还有光）都照它画，SVG 的 viewBox 是 2000 × 1000。
 */
export function memoryWorld(lights: readonly BandLight[]): MemoryWorld {
  const n = lights.length;
  const lines = lights.map((l, i) => ({ id: l.id, color: l.color, x: 0.12 + ((i + 0.5) / Math.max(n, 1)) * 1.76 }));
  const sender = 0;
  // 后半段里色相离她最远的（色相名次在环上量）。
  const ring = (a: number, b: number) => Math.min(Math.abs(a - b), n - Math.abs(a - b));
  let receiver = Math.min(n - 1, Math.ceil(n / 2));
  for (let i = receiver; i < n; i++)
    if (ring(lights[i].hueRank, lights[sender].hueRank) > ring(lights[receiver].hueRank, lights[sender].hueRank)) receiver = i;
  const from: Point = [lines[sender]?.x ?? 0.3, 0.66];
  const to: Point = [lines[receiver]?.x ?? 1.3, 0.4];
  const arc: MemoryArc = {
    source: lights[sender]?.id ?? "",
    target: lights[receiver]?.id ?? "",
    from,
    ctrl: [(from[0] + to[0]) / 2, 0.02],
    to,
  };
  // 传开：她右上、右下、左边各一位，落在光上的高度错开，弧线朝不同的方向鼓。左边那条往下鼓，不和传给她的
  // 那条（从左上方来）贴在一起；都避开画面左下角的文字。
  const spreads: MemoryArc[] = [];
  if (n > 2) {
    const used = new Set([sender, receiver]);
    const SPREAD: [dx: number, y: number, bend: number][] = [
      [0.24, 0.18, -0.12],
      [0.3, 0.6, 0.1],
      [-0.3, 0.52, 0.14],
    ];
    for (const [dx, y, bend] of SPREAD) {
      let best = -1;
      for (let i = 0; i < n; i++)
        if (!used.has(i) && (best < 0 || Math.abs(lines[i].x - to[0] - dx) < Math.abs(lines[best].x - to[0] - dx))) best = i;
      if (best < 0) break;
      used.add(best);
      const end: Point = [lines[best].x, y];
      spreads.push({ source: arc.target, target: lines[best].id, from: to, ctrl: [(to[0] + end[0]) / 2, (to[1] + y) / 2 + bend], to: end });
    }
  }
  return {
    lines,
    sender: lights[sender]?.id ?? null,
    receiver: n > 1 ? lights[receiver].id : null,
    arc,
    spreads,
    arcs: n > 1 ? [arc, ...spreads] : [],
  };
}

/** 第 5 幕里不是这件事主角的光：余烬的亮度。 */
const MEMORY_EMBER = 0.12;
/** 被传到的人亮起来的亮度：同屏满强度的是她和传到的三位，不超过 5 道。 */
const MEMORY_LIT = 0.62;

/** 第 5 幕的横移：开头发送的那一位站在画面左边三成处，传到她时她站在画面六成处，之后不再动。 */
const panAt = (world: MemoryWorld, vp: Viewport, t: number) => lerp(world.arc.from[0] - 0.3, world.arc.to[0] - 0.6, t) * vp.w;

/** 第 5 幕的光：两屏宽的布景里竖着的一道道光，减去横移。 */
function memoryBands(lights: readonly BandLight[], vp: Viewport, world: MemoryWorld, pan: number, lit: (id: string) => number): Band[] {
  return curtain(lights, vp, 0).map((b, i) => ({
    ...b,
    x: world.lines[i].x * vp.w - pan,
    halo: 12 * lights[i].spread,
    intensity: lit(b.id),
  }));
}

/** 第 k 段光路的时间（第 5 幕的幕内进度）：光点从 start 出发，到 end 落下。 */
const relayWindow = (k: number): [start: number, end: number] => (k === 0 ? [0.12, 0.48] : [0.54 + 0.05 * (k - 1), 0.8 + 0.05 * (k - 1)]);

/**
 * 第 5 幕：一个光点从发送的那一位的光出发，颜色渐变着，沿弧线落到接收的那一位的光上，她亮起来；
 * 再从她那里分出三个光点，落到另外三位的光上，落到谁，谁就亮起来。走过的光路留下淡淡的连线
 * （DOM 上的 SVG）。画面跟着第一个光点往右横移不到一屏。最后一屏解开钉住，光暗下去，接上全站最暗的
 * 第 6 幕。`q` 是第 5 幕开始后滚过的屏数。
 */
function act5Picture(lights: readonly BandLight[], vp: Viewport, m: Moment, span: ActSpan, q: number, still: boolean): Picture {
  const world = memoryWorld(lights);
  const p = clamp(q / span.length);
  const fade = 1 - smooth(0, 0.85, q - span.length);
  const pan = panAt(world, vp, easeInOut(smooth(0.1, 0.5, p)));
  const colorOf = new Map(lights.map((l) => [l.id, l.color]));
  const px = ([x, y]: Point): Point => [x * vp.w - pan, y * vp.h];
  // 每个人亮起来的时候：光点落到她身上。
  const arrived = new Map(world.arcs.map((a, k) => [a.target, smooth(relayWindow(k)[1] - 0.02, relayWindow(k)[1] + 0.04, p)]));
  const lit = (id: string) => {
    const base =
      id === world.sender
        ? MEMORY_EMBER + 0.6 * smooth(0.04, 0.12, p) * (1 - 0.5 * smooth(0.3, 0.5, p))
        : MEMORY_EMBER + (MEMORY_LIT - MEMORY_EMBER) * (arrived.get(id) ?? 0);
    return base * fade;
  };
  const relays = world.arcs.map((a, k): Relay => {
    const [start, end] = relayWindow(k);
    const t = easeInOut(smooth(start, end, p));
    const [from, ctrl, to] = [px(a.from), px(a.ctrl), px(a.to)];
    const at = (i: number) => (1 - t) * (1 - t) * from[i] + 2 * (1 - t) * t * ctrl[i] + t * t * to[i];
    return {
      x: at(0),
      y: at(1),
      t,
      from,
      ctrl,
      to,
      color: mixOklab(colorOf.get(a.source)!, colorOf.get(a.target)!, t),
      intensity: smooth(start - 0.06, start, p) * (1 - smooth(end, end + 0.05, p)) * fade,
    };
  });
  return {
    ...quiet(lights, vp, memoryBands(lights, vp, world, pan, lit)),
    dispersion: 0,
    memory: { pan, relays, paths: relays.map((r) => r.t), trail: !still },
  };
}

/** 竖着铺满一屏的光，按光谱的顺序：第 7 幕从这里开始收拢。 */
function curtain(lights: readonly BandLight[], vp: Viewport, intensity: number): Band[] {
  const n = lights.length;
  const left = railWidth(vp) + vp.w * 0.05;
  const right = vp.w * 0.05;
  return lights.map((light, i) => ({
    id: light.id,
    color: light.color,
    gain: light.gain,
    hue: n > 1 ? light.hueRank / (n - 1) : 0.5,
    x: left + ((i + 0.5) / Math.max(n, 1)) * (vp.w - left - right),
    y: -40,
    dx: 0,
    dy: 1,
    length: vp.h + 80,
    start: -200,
    gap0: 0,
    gap1: 0,
    core: 1,
    halo: 14 * light.spread,
    intensity,
  }));
}

/** 第 7 幕收拢时的亮度：都看得见，又都不算满强度。 */
const CURTAIN = 0.34;

/** 第 7 幕的手机屏幕：电脑上在画面左边、文字在右边；竖屏上在上面、文字在下面。 */
function screenOf(vp: Viewport): Omit<Scene["screen"], "intensity"> {
  const portrait = isPortrait(vp);
  const h = portrait ? Math.min(vp.h * 0.2, vp.w * 0.62) : vp.h * 0.3;
  const w = h * 0.46;
  return { x: portrait ? vp.w * 0.5 : railWidth(vp) + (vp.w - railWidth(vp)) * 0.3, y: vp.h * (portrait ? 0.34 : 0.5), w, h, r: w * 0.18 };
}

/**
 * 第 7 幕：28 道光从暗处回来，收拢成一块手机屏幕的白光，这是全站最亮的地方，然后出现行动按钮。
 * `q` 是第 7 幕开始后滚过的屏数（最后一屏解开钉住，屏幕跟着页面往上走）。舞台钉住以后光才回来，
 * 第 6 幕从头到尾都是暗的。
 */
function act7Picture(lights: readonly BandLight[], vp: Viewport, m: Moment, span: ActSpan, q: number): Picture {
  const p = clamp(q / span.length);
  const lift = Math.max(0, q - span.length) * vp.h;
  const geo = screenOf(vp);
  const c = easeInOut(smooth(0.08, 0.6, p));
  const fill = smooth(0.35, 0.75, p);
  const n = lights.length;
  const bands = curtain(lights, vp, CURTAIN * smooth(0, 0.1, p)).map((b, i) => ({
    ...b,
    x: lerp(b.x, geo.x + ((i + 0.5) / Math.max(n, 1) - 0.5) * 2 * geo.w * 0.82, c),
    y: lerp(b.y, geo.y - geo.h, c) - lift,
    length: lerp(b.length, geo.h * 2, c),
    start: lerp(b.start, -90, c),
    core: lerp(b.core, 0.8, c),
    halo: lerp(b.halo, 5, c),
    // 收进屏幕的同时，屏幕亮起来，一道道光化进这片白里。
    intensity: b.intensity * lerp(1, 1.3, c) * (1 - smooth(0.5, 0.78, p)),
  }));
  return {
    ...quiet(lights, vp, bands),
    dispersion: m.samples > 1 ? 0.5 * hill(c) * m.pace : 0,
    screen: { ...geo, y: geo.y - lift, intensity: fill },
    text: { ...QUIET_TEXT, act7: smooth(0.62, 0.8, p) },
  };
}

/** 第 3、4 幕里说话、打来电话的那一位在 lights 里的下标：指定了、并且在名单里的就是她，不然是第一位。 */
function speakerIndex(lights: readonly BandLight[], id: string | undefined): number {
  const i = id === undefined ? -1 : lights.findIndex((l) => l.id === id);
  return Math.max(0, i);
}

/** 第 3 幕有几句话：落地页文案（copy.landing.act3.lines）正好这么多句。 */
export const TALK_LINES = 3;

/** 第 3 幕她那道光的横坐标：画面右边，原文竖排在它左边、字幕在底下。landing.css 的 .lp-talk 按同一个比例排字。 */
const talkLightX = (vp: Viewport) => vp.w * (isPortrait(vp) ? 0.84 : 0.78);

/** 第 3 幕里一道道光收成她一道的那一段（幕内进度）。 */
const TALK_GATHER = 0.14;
/** 第 3 幕第 k 句从哪儿开始（幕内进度）：原文那一列先出来，字幕紧跟着被扫出来。 */
const talkStart = (k: number) => 0.16 + k * 0.27;
/** 字幕扫一遍占的幕内进度。 */
const SWEEP = 0.15;
/** 第 3 幕第 k 句完整显示的时刻（幕内进度）：原文在，字幕刚扫完、下一句还没出来。页内查找找到这一句时滚到这里。 */
export const talkLineShown = (k: number) => talkStart(k) + 0.03 + SWEEP + 0.01;
/** 第 3、4 幕里她那道光的亮度：说话、响铃时再亮一点，都算满强度；其余的光都熄了。 */
const SPEAKER_LIT = 0.6;

/**
 * 第 3 幕「她说日语」：竖着铺满一屏的光收成说话那一位的一道，站到画面右边。她说几句日语：竖排的原文一列
 * 一列出来，中文字幕一句一句被光从左往右扫出来（不是打字机）；她说着的时候光亮一点。`p` 是幕内进度；
 * 静止版式里原文和字幕一开始就完整显示，几句字幕都在。
 */
function act3Picture(lights: readonly BandLight[], vp: Viewport, m: Moment, p: number, her: number, still: boolean): Picture {
  const gather = easeInOut(smooth(0, TALK_GATHER, p));
  const lines: TalkLine[] = Array.from({ length: TALK_LINES }, (_, k) => {
    if (still) return { ja: 1, sweep: 1, subtitle: 1 };
    const start = talkStart(k);
    const out = k < TALK_LINES - 1 ? 1 - smooth(talkStart(k + 1) - 0.02, talkStart(k + 1) + 0.01, p) : 1;
    return { ja: smooth(start, start + 0.05, p), sweep: clamp((p - start - 0.03) / SWEEP), subtitle: smooth(start, start + 0.02, p) * out };
  });
  const speaking = Math.max(...lines.map((l) => hill(l.sweep)));
  const x = talkLightX(vp);
  const bands = curtain(lights, vp, EMBER).map((b, i) =>
    i === her
      ? {
          ...b,
          x: lerp(b.x, x, gather),
          core: lerp(b.core, 1.4, gather),
          halo: lerp(b.halo, 34 * lights[i].spread, gather),
          intensity: lerp(EMBER, SPEAKER_LIT + 0.22 * speaking, gather),
        }
      : // 其余的光朝她那里靠一点，同时熄掉。
        { ...b, x: lerp(b.x, lerp(b.x, x, 0.5), gather), intensity: EMBER * (1 - gather) },
  );
  return {
    ...quiet(lights, vp, bands),
    dispersion: m.samples > 1 ? 0.4 * hill(gather) * m.pace : 0,
    talk: { lines },
    text: { ...QUIET_TEXT, act3: still ? 1 : smooth(0.04, TALK_GATHER, p) },
  };
}

/** 第 4 幕里来电的画面显出来的那一段（幕内进度）：背景过渡到她的极深底色，她的光挪到画面中间。 */
const CALL_IN = 0.15;
/** 铃声的节奏（秒）：响两下、停一会儿，和手机来电一样。 */
const RING_PERIOD = 2.6;
const RING_BURSTS: readonly [from: number, to: number][] = [
  [0, 0.5],
  [0.65, 1.15],
];
/** 响铃时画面振动的幅度（像素）。 */
const SHAKE = 3;
/** 减少动态效果档里定格的光脉冲：画面静止，但看得出在发光。 */
const STILL_PULSE = 0.5;

/** 第 `time` 秒的光脉冲：响的两下各是一座小山，停的时候是 0。 */
function ringPulse(time: number): number {
  const t = ((time % RING_PERIOD) + RING_PERIOD) % RING_PERIOD;
  return Math.max(0, ...RING_BURSTS.map(([a, b]) => (t > a && t < b ? Math.sin((Math.PI * (t - a)) / (b - a)) : 0)));
}

/**
 * 第 4 幕「来电」：全屏是她。背景过渡到她的极深底色，她那道光站到画面中间；铃声在画面上是一阵一阵的
 * 光脉冲，响的时候画面振动（访客接听以前从不出声）。接通以后不再响，她的光稳稳地亮着。`p` 是幕内进度；
 * 静止版式里画面静止：光脉冲定格在一半，不振动。
 */
function act4Picture(
  lights: readonly BandLight[],
  vp: Viewport,
  m: Moment,
  p: number,
  her: number,
  phase: Call["phase"],
  still: boolean,
): Picture & { call: CallState } {
  const from = act3Picture(lights, vp, m, 1, her, still);
  const enter = still ? 1 : easeInOut(smooth(0, CALL_IN, p));
  const ringing = phase !== "connected";
  const pulse = !ringing ? 0 : still ? STILL_PULSE : ringPulse(m.time) * enter;
  const t = m.time;
  const shake = still || pulse === 0 ? { x: 0, y: 0 } : { x: SHAKE * pulse * Math.sin(2 * Math.PI * 23 * t), y: 0.4 * SHAKE * pulse * Math.sin(2 * Math.PI * 17 * t + 1) };
  const light = lights[her];
  const base = mixOklab(BACKGROUND, light.deep, enter);
  const bands = from.bands.map((b, i) =>
    i === her
      ? {
          ...b,
          x: lerp(b.x, vp.w * 0.5, enter),
          halo: lerp(b.halo, 46 * light.spread, enter),
          intensity: lerp(b.intensity, ringing ? 0.5 + 0.38 * pulse : 0.78, enter),
        }
      : b,
  );
  return {
    ...from,
    background: pulse > 0 ? mixOklab(base, light.color, 0.14 * pulse) : base,
    bands,
    dispersion: 0,
    // 第 3 幕的字在这一幕开头淡出：留着说完的样子。
    talk: from.talk,
    call: { pulse, shake },
    text: { ...QUIET_TEXT, act3: still ? 0 : 1 - smooth(0, 0.08, p), act4: still ? 1 : smooth(0.06, CALL_IN + 0.05, p) },
  };
}

/** 页面按名单算出的时间线；同一份名单每帧都要，记下最近一次的。 */
let memo: { units: number; timeline: Timeline } | null = null;
function timelineFor(lights: readonly BandLight[]): Timeline {
  const units = unitCount(lights);
  if (memo?.units !== units) memo = { units, timeline: timelineOf(units) };
  return memo.timeline;
}

export function describeScene(input: SceneInput): Scene {
  const { lights, scroll, viewport, tier } = input;
  const timeline = timelineFor(lights);
  const where = whereIs(timeline, scroll);
  const still = layoutOf(tier) === "still";
  // 「减少动态效果」档和静态档：任何进度下都是这一幕的完成态，定格、不呼吸、不随指针和速度变。
  const m: Moment = still
    ? { p: 1, pointer: { x: 0, y: 0 }, time: 0, pace: 0, samples: 1 }
    : {
        p: 0,
        pointer: input.pointer ?? { x: 0, y: 0 },
        time: input.time ?? 0,
        pace: Math.min(1, 0.25 + Math.abs(input.speed ?? 0) / 2),
        samples: qualityOf(tier, false).samples,
      };

  const act1 = spanOf(timeline, 1)!;
  const act2 = spanOf(timeline, 2);
  const act6 = spanOf(timeline, 6)!;
  const act7 = spanOf(timeline, 7)!;
  if (scroll >= act7.from) {
    return { ...where, ...act7Picture(lights, viewport, m, act7, still ? act7.length : scroll - act7.from) };
  }
  if (scroll >= act6.from) {
    // 全站最暗、最静的一段：第 7 幕开头的样子，光还没回来。
    return { ...where, ...act7Picture(lights, viewport, m, act7, 0) };
  }
  const act5 = spanOf(timeline, 5)!;
  if (scroll >= act5.from) {
    return { ...where, ...act5Picture(lights, viewport, m, act5, still ? act5.length : scroll - act5.from, still) };
  }
  const act3 = spanOf(timeline, 3);
  const act4 = spanOf(timeline, 4);
  const her = speakerIndex(lights, input.speaker);
  if (act4 && scroll >= act4.from) {
    const q = still ? act4.length : scroll - act4.from;
    const picture = act4Picture(lights, viewport, m, clamp(q / act4.length), her, input.call ?? "ringing", still);
    const release = q - act4.length;
    if (release <= 0) return { ...where, ...picture };
    // 解开钉住的那一屏：她的光和熄着的光一起变形成第 5 幕开头的样子，背景回到黑，铃声的光暗下去，来电的画面淡出。
    // 第 5 幕的布景这时已经从下面进来了：连线一条都还没画，横移停在开头，还不留指针痕迹。
    const t = smooth(0, 1, release);
    const world = memoryWorld(lights);
    const next = memoryBands(lights, viewport, world, panAt(world, viewport, 0), () => MEMORY_EMBER);
    const entering = act5Picture(lights, viewport, m, act5, 0, still).memory!;
    return {
      ...where,
      ...picture,
      background: mixOklab(picture.background, BACKGROUND, t),
      bands: blend(picture.bands, next, t),
      call: { pulse: picture.call.pulse * (1 - t), shake: { x: picture.call.shake.x * (1 - t), y: picture.call.shake.y * (1 - t) } },
      // 来电的画面（立绘只盖到舞台底边）不跟着舞台整块往上走，先淡出。
      text: { ...picture.text, act4: 1 - smooth(0, 0.5, release) },
      memory: { ...entering, relays: entering.relays.map((r) => ({ ...r, intensity: 0 })), trail: false },
    };
  }
  if (act3 && scroll >= act3.from) {
    return { ...where, ...act3Picture(lights, viewport, m, still ? 1 : clamp((scroll - act3.from) / act3.length), her, still) };
  }
  if (act2 && scroll >= act2.from) {
    // 定格时是光谱尺：全部的光排在一屏里，一帧就是整条光谱。
    const q = still ? REGROUP_SCREENS : scroll - act2.from;
    const picture = act2Picture(lights, viewport, m, {
      q,
      length: act2.length,
      track: still ? undefined : input.track,
      focus: input.focus ?? {},
      nameGaps: input.nameGaps ?? {},
    });
    const release = q - act2.length;
    if (release <= 0) return { ...where, ...picture };
    // 解开钉住的那一屏：一道道光变形成第 3 幕开头的样子（竖着铺满一屏）。画面外很远的那些先在画面外收到
    // 画面边上，免得几屏外的光一下扫过整个画面。第 3 幕的舞台这时从下面进来，原文和字幕都还没出来。
    const opening = act3Picture(lights, viewport, m, 0, her, still);
    const gather = smooth(0, 0.3, release);
    const near = picture.bands.map((b) => ({ ...b, x: lerp(b.x, clamp(b.x, -0.15 * viewport.w, 1.15 * viewport.w), gather) }));
    return {
      ...where,
      ...picture,
      bands: blend(near, opening.bands, smooth(0, 1, release)),
      talk: opening.talk,
      text: { ...picture.text, act3: 0 },
    };
  }
  const picture = act1Picture(lights, viewport, { ...m, p: still ? 1 : clamp((scroll - act1.from) / act1.length) });
  return { ...where, ...picture, beam: still ? { ...picture.beam, tip: 0 } : picture.beam };
}
