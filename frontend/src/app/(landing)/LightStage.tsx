"use client";

import { useEffect, useRef, type CSSProperties, type ReactNode } from "react";

import { describeScene, slotX, unitCount, type BandLight, type Scene, type Viewport } from "./model/scene";
import { settleSpring, stepSpring } from "./model/spring";
import { qualityOf, tierReducer, TIERS, type Tier, type TierAction } from "./model/tier";
import { holdAt, timelineOf, type Section } from "./model/timeline";
import { liveTrail, pushTrail, type TrailPoint } from "./model/trail";
import { idle } from "./idle";
import type { Light } from "./light";
import { stageStore } from "./stageStore";

/** 按帧降档要攒够的样本：至少这么多帧、这么长时间才算一次平均（原型的做法）。 */
const MEASURE_FRAMES = 90;
const MEASURE_MS = 2500;
/** 聚焦淡入淡出的时间常数（秒）。 */
const FOCUS_EASE = 0.22;

/** 页面上的一段（Landing.tsx 里 `data-lp-section` 的元素），量好的位置。 */
type Measured = Section & { el: HTMLElement; top: number; height: number };

/**
 * 第 1、2 幕的舞台和整页的光层。一个 requestAnimationFrame 循环驱动一切：Lenis 推进滚动 → 落地页模型
 * 算出这一帧的画面 → 直接写 DOM 的样式变量（不走 React 状态）→ OGL 画光。档位由首屏前的内联脚本写在
 * <html> 上（tierScript.ts），这里读它：
 *
 * - 运动版式（完整、简化档）：页面分成几段（model/timeline.ts），钉住的一段是 `position: sticky` 的舞台，
 *   高度正好是它占的屏数。循环按每一段量好的位置把滚动位置换算成时间线上的屏数，交给落地页模型。
 *   原生滚动加 Lenis（lerp 0.1，触屏不做平滑）：Lenis 只把滚轮的位移平滑以后写回页面原生的滚动位置，
 *   不吸附、不分页、不改变滚动距离，键盘翻页、页内查找、浏览器后退都照常。Lenis 在首帧之后才加载，
 *   加载之前就是原生滚动。OGL 在浏览器空闲时才加载，画好第一帧才淡入，淡入时首屏 CSS 画的白光
 *   同时淡出；两束光的几何是同一套（model/scene.ts 的锚点就是 landing.css 里 .lp-beam 的尽头）。
 *   第 2 幕的名牌按模型的 slotX 摆到横滚轨道上，轨道的横移经弹簧平滑；名牌上名字的位置量好了传给模型，
 *   光芯在那里断开。第 5 幕的布景（Memory 的 SVG）跟着模型横移、光点走到哪儿连线画到哪儿，指针在这一幕留下
 *   慢慢消散的痕迹；第 7 幕的文字和行动按钮跟着模型淡入。
 * - 定格档（减少动态效果）：不钉住、不加载 Lenis；OGL 只渲染一帧第 1 幕的完成态就停下，
 *   窗口尺寸变了才重画那一帧。画好之前，静态档的 SVG 先顶着。
 * - 静态档（省流量、不支持 WebGL）：什么都不加载，光由服务端渲染的 SVG（StaticLight）和 CSS 画。
 *
 * 光层建不起来或 WebGL 上下文丢了，就地退到静态档：收起画布，版式不变，各幕的 CSS 光重新露出来。
 */
export function LightStage({ lights, section, children }: { lights: BandLight[]; section: Section; children: ReactNode }) {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const html = document.documentElement;
    const stage = wrap.current!;
    const root = stage.closest<HTMLElement>(".lp-root")!;
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
    // 收起画布：SVG 和 CSS 画的光重新露出来。运动版式的主循环不停，各幕的文字照样由它推进。
    const drop = () => {
      if (dropped) return;
      dropped = true;
      light?.destroy();
      light = null;
      root.classList.remove("lp-gl-on");
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
            root.classList.add("lp-gl-on");
          });
        })
        .catch(() => dispatch({ type: "lost" }));

    // —— 定格档：画一帧就停。
    if (!qualityOf(tier, touch).animate) {
      const draw = () => {
        if (!light) return;
        // 量第 1 幕那一屏（画布盖着它）：OGL 会把画布的宽高写成内联样式，不能量画布本身。
        const box = (stage.querySelector(".lp-act1") ?? target).getBoundingClientRect();
        light.resize(box.width, box.height);
        light.render(describeScene({ lights, scroll: 1, viewport: { w: box.width, h: box.height }, tier }), 0);
      };
      void loadLight(draw);
      window.addEventListener("resize", draw);
      cleanups.push(() => window.removeEventListener("resize", draw));
      return unmount;
    }

    // —— 运动版式。
    const timeline = timelineOf(unitCount(lights));
    const sections: Measured[] = [...root.querySelectorAll<HTMLElement>("[data-lp-section]")].map((el) => ({
      ...timeline.sections[Number(el.dataset.lpSection)],
      el,
      top: 0,
      height: 1,
    }));
    const plates = [...stage.querySelectorAll<HTMLElement>("[data-lp-id]")];
    const lightOf = new Map(lights.map((l) => [l.id, l]));
    // 立绘的框由 Spectrum 在知道版式以后才渲染，比这里晚一步，用到时再找。
    let standBoxEl: HTMLElement | null = null;
    const findStandBox = () => (standBoxEl ??= stage.querySelector<HTMLElement>(".lp-track > .lp-stand"));
    const track = stage.querySelector<HTMLElement>(".lp-track");
    const railItems = [...root.querySelectorAll<HTMLElement>("[data-lp-rail]")];
    const memoryEl = root.querySelector<HTMLElement>(".lp-memory");
    const startEl = root.querySelector<HTMLElement>(".lp-start");

    let vp: Viewport = { w: 1, h: 1 };
    let nameGaps: Record<string, readonly [number, number]> = {};
    /** 名牌上文字（编号、名字、色值）的竖直区间：舞台钉住时舞台顶就是视口顶。字体晚到会改变名字的高度，到了要重新量。 */
    const measureGaps = () => {
      const top = stage.getBoundingClientRect().top;
      nameGaps = Object.fromEntries(
        plates.map((el) => {
          const r = el.querySelector(".lp-plate-body")!.getBoundingClientRect();
          return [el.dataset.lpId!, [r.top - top - 6, r.bottom - top + 6] as const];
        }),
      );
    };
    const measure = () => {
      vp = { w: html.clientWidth, h: window.innerHeight };
      root.style.setProperty("--lp-vh", `${vp.h}px`);
      for (const s of sections) {
        s.top = s.el.getBoundingClientRect().top + window.scrollY;
        s.height = Math.max(1, s.el.offsetHeight);
      }
      for (const el of plates) {
        const l = lightOf.get(el.dataset.lpId!);
        if (l) el.style.left = `${slotX(vp, l.unit, l.slot, l.unitSize)}px`;
      }
      measureGaps();
      placeStand();
      light?.resize(vp.w, vp.h);
    };
    // 立绘站在她名牌外侧空间大的一边。
    let standFor: string | undefined;
    const placeStand = () => {
      const standBox = findStandBox();
      const l = standBox && lightOf.get(standBox.dataset.lpStand ?? "");
      if (!standBox || !l) return;
      const x = slotX(vp, l.unit, l.slot, l.unitSize);
      const side = x - l.unit * vp.w < vp.w * 0.55 ? 1 : -1;
      standBox.style.left = `${x + side * (standBox.offsetWidth * 0.5 + 24) - standBox.offsetWidth * 0.5}px`;
    };
    measure();
    window.addEventListener("resize", measure);
    document.fonts.addEventListener("loadingdone", measure);
    cleanups.push(() => {
      window.removeEventListener("resize", measure);
      document.fonts.removeEventListener("loadingdone", measure);
    });

    /**
     * 滚过的屏数（时间线的单位）。钉住的一段高度正好是它的屏数，一一对应；照常往上走的一段按比例换算，
     * 但最后一屏一一对应：那是下一段从下面进来的时候，和下一段的画面要对得上。
     */
    const scrollOf = (y: number) => {
      const s = sections.find((s) => y < s.top + s.height) ?? sections.at(-1)!;
      const into = Math.max(0, y - s.top);
      if (s.pinned || s.height <= vp.h) return s.from + Math.min(s.screens, (into / s.height) * s.screens);
      const body = s.height - vp.h;
      return into < body ? s.from + (into / body) * (s.screens - 1) : s.from + s.screens - 1 + Math.min(1, (into - body) / vp.h);
    };
    /** 时间线上第 `screens` 屏在页面上的位置（scrollOf 反过来，只用于钉住的段）。 */
    const yOf = (screens: number) => {
      const s = sections.find((s) => screens < s.from + s.screens) ?? sections.at(-1)!;
      return s.top + ((screens - s.from) / s.screens) * s.height;
    };

    // 指针（鼠标、笔）和手指：只影响第 0 幕白光的角度，经弹簧平滑。手指用 touch 事件：
    // 滑动时浏览器会接管 pointer 事件去滚动页面，touchmove 照样会来。
    const aim = { x: 0, y: 0 };
    /** 第 5 幕里指针留下的痕迹（视口坐标）；模型说这一幕要痕迹时才记。 */
    let trail: TrailPoint[] = [];
    let trailOn = false;
    const toward = (x: number, y: number) => {
      aim.x = (x / vp.w) * 2 - 1;
      aim.y = (y / vp.h) * 2 - 1;
      if (trailOn) trail = pushTrail(trail, x, y, performance.now() / 1000);
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

    let lenis: { raf(time: number): void; scrollTo(y: number, o?: { duration?: number; immediate?: boolean }): void; destroy(): void } | null = null;
    requestAnimationFrame(() =>
      import("lenis").then(({ default: Lenis }) => {
        if (unmounted) return;
        lenis = new Lenis({ lerp: 0.1, syncTouch: false, autoRaf: false });
      }),
    );
    cleanups.push(() => lenis?.destroy());

    // 按组合跳转：滚到那个组合停稳的地方。
    stageStore.jump = (u, instant) => {
      const y = yOf(holdAt(timeline, u));
      if (lenis) lenis.scrollTo(y, instant ? { immediate: true } : { duration: 1.2 });
      else window.scrollTo({ top: y, behavior: instant ? "instant" : "smooth" });
    };
    cleanups.push(() => (stageStore.jump = null));

    void loadLight((l) => l.resize(vp.w, vp.h));

    let px = settleSpring(0);
    let py = settleSpring(0);
    let trackSpring: ReturnType<typeof settleSpring> | null = null;
    let trackTarget = 0;
    const focus: Record<string, number> = {};
    let speed = 0;
    let last = performance.now();
    let lastScroll = scrollOf(window.scrollY);
    let frames = { n: 0, ms: 0, since: last };
    let act = -1;
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
      // 横移：弹簧追上一帧模型给的目标。不在第 2 幕时没有弹簧，进第 2 幕的那一帧直接落在目标上
      // （刷新后停在某个组合、从后面的幕滚回来，轨道都不会从头扫过几屏）。
      if (trackSpring) trackSpring = stepSpring(trackSpring, trackTarget, dt);
      // 聚焦：被聚焦的那位淡入，其余的淡出，淡完的拿掉。
      const ease = 1 - Math.exp(-dt / FOCUS_EASE);
      for (const id of new Set([...Object.keys(focus), ...(stageStore.focus ? [stageStore.focus] : [])])) {
        const w = (focus[id] ?? 0) + ((id === stageStore.focus ? 1 : 0) - (focus[id] ?? 0)) * ease;
        if (w < 0.002 && id !== stageStore.focus) delete focus[id];
        else focus[id] = w;
      }

      const scene: Scene = describeScene({
        lights,
        scroll,
        viewport: vp,
        tier,
        speed,
        pointer: { x: px.x, y: py.x },
        time: now / 1000,
        track: trackSpring?.x,
        focus,
        nameGaps,
      });
      stage.style.setProperty("--lp-act1-text", String(scene.text.act1));
      stage.style.setProperty("--lp-plates", String(scene.text.plates));
      // 名牌显出来以后才接指针：之前它们透明地盖在第 1 幕上面。
      stage.toggleAttribute("data-lp-plates", scene.text.plates > 0.5);
      if (!scene.spectrum) trackSpring = null;
      else {
        trackTarget = scene.spectrum.trackTarget;
        trackSpring ??= settleSpring(trackTarget);
        if (track) track.style.transform = `translate3d(${-scene.spectrum.track * vp.w}px,0,0)`;
        stageStore.set({ unit: scene.spectrum.unit, stand: scene.spectrum.stand });
        const standBox = findStandBox();
        if (standBox && standBox.dataset.lpStand !== standFor) {
          standFor = standBox.dataset.lpStand;
          placeStand();
        }
      }
      if (scene.memory && memoryEl) {
        memoryEl.style.setProperty("--lp-pan", `${-scene.memory.pan}px`);
        scene.memory.paths.forEach((t, k) => memoryEl.style.setProperty(`--lp-path-${k}`, String(t)));
      }
      trailOn = !!scene.memory?.trail;
      const marks = trailOn ? liveTrail(trail, now / 1000) : [];
      if (startEl) {
        startEl.style.setProperty("--lp-act7", String(scene.text.act7));
        startEl.toggleAttribute("data-lp-cta", scene.text.act7 > 0.5);
      }
      if (scene.act !== act) {
        act = scene.act;
        for (const li of railItems) {
          const on = Number(li.dataset.lpRail) === act;
          li.toggleAttribute("data-current", on);
          if (on) li.setAttribute("aria-current", "step");
          else li.removeAttribute("aria-current");
        }
      }

      if (!light) return;
      // 画面里什么都没亮时（第 6 幕最暗的那一段）画一帧就歇着。
      const dark = isDark(scene) && marks.length === 0;
      if (dark && parked) return;
      parked = dark;
      light.render(scene, now / 1000, marks);

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
    <div
      ref={wrap}
      className="lp-stage-wrap"
      data-lp-section={section.index}
      style={{ "--lp-screens": section.screens } as CSSProperties}
    >
      <div className="lp-stage">
        <canvas ref={canvas} className="lp-canvas" aria-hidden />
        {children}
      </div>
    </div>
  );
}

/** 画面里没有一处是亮的。 */
const isDark = (s: Scene) =>
  s.beam.intensity < 0.003 &&
  s.prism.intensity < 0.003 &&
  s.fan.intensity < 0.003 &&
  s.screen.intensity < 0.003 &&
  (s.memory?.relays ?? []).every((r) => r.intensity < 0.003) &&
  s.bands.every((b) => b.intensity < 0.004);

function readTier(html: HTMLElement): Tier {
  const t = html.dataset.lpTier as Tier | undefined;
  return t && TIERS.includes(t) ? t : "static";
}
