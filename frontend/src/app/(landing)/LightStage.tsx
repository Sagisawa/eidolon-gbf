"use client";

import { useEffect, useRef, type CSSProperties, type ReactNode } from "react";

import { describeScene, STAGE_SCREENS, type BandLight, type Scene, type Viewport } from "./model/scene";
import { settleSpring, stepSpring } from "./model/spring";
import { qualityOf, tierReducer, TIERS, type Tier, type TierAction } from "./model/tier";
import { idle } from "./idle";
import type { Light } from "./light";

/** 按帧降档要攒够的样本：至少这么多帧、这么长时间才算一次平均（原型的做法）。 */
const MEASURE_FRAMES = 90;
const MEASURE_MS = 2500;

/**
 * 第 1 幕的舞台和光层。一个 requestAnimationFrame 循环驱动一切：Lenis 推进滚动 → 落地页模型算出
 * 这一帧的画面 → 直接写 DOM 的样式变量（不走 React 状态）→ OGL 画光。档位由首屏前的内联脚本写在
 * <html> 上（tierScript.ts），这里读它：
 *
 * - 运动版式（完整、简化档）：舞台 `position: sticky` 钉住，滚动驱动第 0、1 幕的变形。原生滚动加
 *   Lenis（lerp 0.1，触屏不做平滑）：Lenis 只把滚轮的位移平滑以后写回页面原生的滚动位置，不吸附、
 *   不分页、不改变滚动距离，键盘翻页、页内查找、浏览器后退都照常。Lenis 在首帧之后才加载，
 *   加载之前就是原生滚动。OGL 在浏览器空闲时才加载，画好第一帧才淡入，淡入时首屏 CSS 画的白光
 *   同时淡出；两束光的几何是同一套（model/scene.ts 的锚点就是 landing.css 里 .lp-beam 的尽头）。
 * - 定格档（减少动态效果）：不钉住、不加载 Lenis；OGL 只渲染一帧第 1 幕的完成态就停下，
 *   窗口尺寸变了才重画那一帧。画好之前，静态档的 SVG 先顶着。
 * - 静态档（省流量、不支持 WebGL）：什么都不加载，光由服务端渲染的 SVG（StaticLight）和 CSS 画。
 *
 * 光层建不起来或 WebGL 上下文丢了，就地退到静态档：收起画布，版式不变。
 */
export function LightStage({ lights, children }: { lights: BandLight[]; children: ReactNode }) {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const html = document.documentElement;
    const stage = wrap.current!;
    const target = canvas.current!;
    let tier = readTier(html);
    const touch = matchMedia("(hover: none)").matches;
    if (!qualityOf(tier, touch).canvas) return;

    let light: Light | null = null;
    /** 画布收起了：卸载，或者退到了静态档。之后不再建光层。 */
    let dropped = false;
    /** 画布淡入了：之前白光不随指针转，和首屏 CSS 画的那束对得上。 */
    let shown = false;
    const cleanups: (() => void)[] = [];
    const dispatch = (action: TierAction) => {
      const next = tierReducer(tier, action);
      if (next === tier) return;
      tier = next;
      // 版式（data-lp-layout）是首屏前定的，运行中不改：从运动版式退到静态档时舞台照样钉住、
      // 照样那么长，正在第 1 幕中间的人不会被一下甩到光谱。
      html.dataset.lpTier = tier;
      if (qualityOf(tier, touch).canvas) light?.setQuality(qualityOf(tier, touch));
      else drop();
    };
    // 收起画布：SVG 和 CSS 画的光重新露出来。运动版式的主循环不停，第 1 幕的文字照样由它推进。
    const drop = () => {
      if (dropped) return;
      dropped = true;
      light?.destroy();
      light = null;
      stage.closest(".lp-root")?.classList.remove("lp-gl-on");
    };
    let unmounted = false;
    const unmount = () => {
      unmounted = true;
      cleanups.forEach((f) => f());
      drop();
    };
    const lost = (e: Event) => {
      e.preventDefault();
      dispatch({ type: "lost" });
    };
    target.addEventListener("webglcontextlost", lost);
    cleanups.push(() => target.removeEventListener("webglcontextlost", lost));

    // 光层的包也等到空闲才下载：不和首屏的字体、样式抢带宽。
    const loadLight = (onReady: (l: Light) => void) =>
      idle()
        .then(() => (dropped ? null : import("./light")))
        .then(async (mod) => {
          if (!mod) return;
          const l = await mod.createLight(target, qualityOf(tier, touch));
          if (dropped) return l.destroy();
          light = l;
          onReady(l);
          // 第一帧画好以后再淡入。
          requestAnimationFrame(() => {
            if (dropped) return;
            shown = true;
            stage.closest(".lp-root")?.classList.add("lp-gl-on");
          });
        })
        .catch(() => dispatch({ type: "lost" }));

    // —— 定格档：画一帧就停。
    if (!qualityOf(tier, touch).animate) {
      const draw = () => {
        if (!light) return;
        // 量画布所在的盒子：OGL 会把画布的宽高写成内联样式。
        const box = (target.parentElement ?? target).getBoundingClientRect();
        light.resize(box.width, box.height);
        light.render(describeScene({ lights, scroll: 1, viewport: { w: box.width, h: box.height }, tier }), 0);
      };
      void loadLight(draw);
      window.addEventListener("resize", draw);
      cleanups.push(() => window.removeEventListener("resize", draw));
      return unmount;
    }

    // —— 运动版式。
    let vp: Viewport = { w: 1, h: 1 };
    let stageTop = 1;
    const measure = () => {
      vp = { w: html.clientWidth, h: window.innerHeight };
      stage.style.setProperty("--lp-vh", `${vp.h}px`);
      stageTop = stage.getBoundingClientRect().top + window.scrollY;
      light?.resize(vp.w, vp.h);
    };
    measure();
    window.addEventListener("resize", measure);
    cleanups.push(() => window.removeEventListener("resize", measure));

    // 滚过的屏数：第 0 幕不管多高都算一屏，舞台钉住的地方正好是 1。
    const scrollOf = (y: number) => (y < stageTop ? y / Math.max(stageTop, 1) : 1 + (y - stageTop) / vp.h);

    // 指针（鼠标、笔）和手指：只影响第 0 幕白光的角度，经弹簧平滑。手指用 touch 事件：
    // 滑动时浏览器会接管 pointer 事件去滚动页面，touchmove 照样会来。
    const aim = { x: 0, y: 0 };
    const toward = (x: number, y: number) => {
      aim.x = (x / vp.w) * 2 - 1;
      aim.y = (y / vp.h) * 2 - 1;
    };
    const onPointer = (e: PointerEvent) => e.pointerType !== "touch" && toward(e.clientX, e.clientY);
    const onTouch = (e: TouchEvent) => e.touches[0] && toward(e.touches[0].clientX, e.touches[0].clientY);
    window.addEventListener("pointermove", onPointer, { passive: true });
    window.addEventListener("touchstart", onTouch, { passive: true });
    window.addEventListener("touchmove", onTouch, { passive: true });
    cleanups.push(() => {
      window.removeEventListener("pointermove", onPointer);
      window.removeEventListener("touchstart", onTouch);
      window.removeEventListener("touchmove", onTouch);
    });

    let lenis: { raf(time: number): void; destroy(): void } | null = null;
    requestAnimationFrame(() =>
      import("lenis").then(({ default: Lenis }) => {
        if (unmounted) return;
        lenis = new Lenis({ lerp: 0.1, syncTouch: false, autoRaf: false });
      }),
    );
    cleanups.push(() => lenis?.destroy());

    void loadLight((l) => l.resize(vp.w, vp.h));

    let px = settleSpring(0);
    let py = settleSpring(0);
    let speed = 0;
    let last = performance.now();
    let lastScroll = scrollOf(window.scrollY);
    let frames = { n: 0, ms: 0, since: last };
    let parked = false;
    let raf = 0;
    const loop = (now: number) => {
      raf = requestAnimationFrame(loop);
      lenis?.raf(now);
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      if (dt <= 0) return;

      const scroll = scrollOf(window.scrollY);
      // 滚动速度（屏/秒）：低通一下，色散不跟着每一帧的抖动闪。
      speed += ((scroll - lastScroll) / dt - speed) * (1 - Math.exp(-dt / 0.12));
      lastScroll = scroll;
      px = stepSpring(px, shown ? aim.x : 0, dt);
      py = stepSpring(py, shown ? aim.y : 0, dt);

      const scene: Scene = describeScene({
        lights,
        scroll,
        viewport: vp,
        tier,
        speed,
        pointer: { x: px.x, y: py.x },
        time: now / 1000,
      });
      stage.style.setProperty("--lp-act1-text", String(scene.text.act1));

      if (!light) return;
      // 舞台整个滚出去以后画面是空的，画最后一帧就歇着。
      const gone = scroll >= STAGE_SCREENS + 0.05;
      if (gone && parked) return;
      parked = gone;
      light.render(scene, now / 1000);

      // 按帧降档：只在画着的时候量，攒够一段算一次平均。
      frames.n += 1;
      frames.ms += dt * 1000;
      if (frames.n >= MEASURE_FRAMES && now - frames.since >= MEASURE_MS) {
        dispatch({ type: "frames", averageMs: frames.ms / frames.n });
        frames = { n: 0, ms: 0, since: now };
      }
    };
    raf = requestAnimationFrame(loop);
    // 标签页切到后台时 requestAnimationFrame 停了，回来的第一帧不算进帧耗时。
    const onVisible = () => {
      last = performance.now();
      frames = { n: 0, ms: 0, since: last };
    };
    document.addEventListener("visibilitychange", onVisible);
    cleanups.push(() => {
      cancelAnimationFrame(raf);
      document.removeEventListener("visibilitychange", onVisible);
    });
    return unmount;
  }, [lights]);

  return (
    <div ref={wrap} className="lp-stage-wrap" style={{ "--lp-stage-screens": STAGE_SCREENS } as CSSProperties}>
      <div className="lp-stage">
        <canvas ref={canvas} className="lp-canvas" aria-hidden />
        {children}
      </div>
    </div>
  );
}

function readTier(html: HTMLElement): Tier {
  const t = html.dataset.lpTier as Tier | undefined;
  return t && TIERS.includes(t) ? t : "static";
}
