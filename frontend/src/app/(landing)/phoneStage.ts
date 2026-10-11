// 第 4 幕手机这一层的起落（LightStage 的循环每帧调 frame）：滚到第 3 幕附近才去下载 three.js 和模型、建画布；
// 有手机的那一刻才画，画面没变就不画；离开第 3、4 幕那一段就不画了，手指操作的设备上再把 WebGL 上下文放掉
// （和立绘一样），回来时重建。画布丢了上下文（不是自己放掉的）就收起手机，退回原来的全屏来电，不连带落地页降档。
//
// 手机画好第一帧以后，.lp-root 加上 lp-phone-on：来电界面从全屏挪进屏幕矩形（landing.css），stageStore 的
// phone 同时变成 true（来电就不挂全屏的立绘）。

import type { PhoneState } from "./model/phone";
import type { Quality } from "./model/tier";
import { spanOf, type Timeline } from "./model/timeline";
import type { PhoneLayer } from "./phoneLayer";
import { stageStore } from "./stageStore";

/** 第 3 幕开始前多少屏开始下载、建画布（第 2 幕解开钉住的那一屏里）。 */
const LOAD_AHEAD = 1;
/** 离开第 3、4 幕那一段这么多屏以外，手指操作的设备上放掉上下文。 */
const RELEASE_BEYOND = 1.5;

export type PhoneStage = {
  /** 每帧调：`scroll` 是滚过的屏数，`phone` 是落地页模型这一帧的手机（不在第 4 幕时是 null）。 */
  frame(scroll: number, phone: PhoneState | null): void;
  resize(w: number, h: number): void;
  setQuality(quality: Quality): void;
  /** 收起手机（落地页退到静态档、卸载）：之后不再建。 */
  drop(): void;
};

export function createPhoneStage({
  root,
  host,
  timeline,
  touch,
  quality,
  glow,
}: {
  root: HTMLElement;
  /** 画布放进这里（Call 的 .lp-phone，和屏幕上的来电界面同一个容器，一起振动）。 */
  host: HTMLElement;
  timeline: Timeline;
  touch: boolean;
  quality: Quality;
  /** 屏幕亮起时的颜色：打来电话的她的颜色。 */
  glow: string;
}): PhoneStage {
  const act3 = spanOf(timeline, 3);
  const act4 = spanOf(timeline, 4);
  let q = quality;
  let size = { w: 1, h: 1 };
  let layer: PhoneLayer | null = null;
  let canvas: HTMLCanvasElement | null = null;
  let building = false;
  let dropped = false;

  const setOn = (on: boolean) => {
    root.classList.toggle("lp-phone-on", on);
    stageStore.set({ phone: on });
  };

  // 放掉上下文：自己放的不算丢了。
  const release = () => {
    const c = canvas;
    canvas = null;
    layer?.destroy();
    layer = null;
    c?.remove();
  };

  const drop = () => {
    if (dropped) return;
    dropped = true;
    release();
    setOn(false);
  };

  const build = async () => {
    building = true;
    const c = document.createElement("canvas");
    c.className = "lp-phone-canvas";
    c.setAttribute("aria-hidden", "true");
    c.addEventListener("webglcontextlost", (e) => {
      if (c !== canvas) return;
      e.preventDefault();
      drop();
    });
    host.prepend(c);
    canvas = c;
    try {
      const mod = await import("./phoneLayer");
      const l = await mod.createPhoneLayer(c, q);
      if (dropped || canvas !== c) return l.destroy();
      l.resize(size.w, size.h);
      layer = l;
    } catch {
      drop();
    } finally {
      building = false;
    }
  };

  return {
    frame(scroll, phone) {
      if (dropped || !act3 || !act4) return;
      const near = scroll >= act3.from - LOAD_AHEAD && scroll < act4.to + LOAD_AHEAD;
      if (near && !layer && !building) void build();
      const far = scroll < act3.from - LOAD_AHEAD - RELEASE_BEYOND || scroll > act4.to + RELEASE_BEYOND;
      if (far && touch && layer) release();
      if (!layer || !phone) return;
      layer.render(phone, glow);
      if (!root.classList.contains("lp-phone-on")) setOn(true);
    },
    resize(w, h) {
      size = { w, h };
      layer?.resize(w, h);
    },
    setQuality(next) {
      q = next;
      layer?.setQuality(next);
    },
    drop,
  };
}
