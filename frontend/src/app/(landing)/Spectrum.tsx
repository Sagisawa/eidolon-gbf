"use client";

import { lazy, Suspense, useEffect, useRef, useState, useSyncExternalStore, type CSSProperties } from "react";

import type { Outfit } from "@/lib/api";

import type { Tier } from "./model/tier";
import { stageStore } from "./stageStore";

// 立绘（spine-ts 和应用的立绘组件）不进首屏的包：聚焦到一位偶像、停稳了才加载。
const Stand = lazy(() => import("@/components/conversations/stand/Stand").then((m) => ({ default: m.Stand })));

/** 一块名牌：名字、编号、颜色都由服务端算好。 */
export type Plate = {
  id: string;
  name: string;
  /** 偶像编号，两位数补零；没有编号时为 null。 */
  number: string | null;
  /** 她在第几个组合、组合里第几位、组合有几人：LightStage 按它把名牌摆到横滚轨道上。 */
  unit: number;
  slot: number;
  unitSize: number;
  /** 黑底和她的极深底色上写名字的颜色、光晕色、官方色、极深底色（color.ts）。 */
  ink: string;
  halo: string;
  official: string;
  deep: string;
  /** 她的默认衣装；没配立绘素材时为 null，聚焦时只有名字和光。 */
  outfit: Outfit | null;
};

export type SpectrumUnit = {
  /** 组合名；查不到组合的偶像排在最后一段，这一段没有组合名。 */
  name: string | null;
  plates: Plate[];
};

export type SpectrumCopy = { label: string; jump: string; jumpTo: string[]; others: string };

/** 聚焦停留这么久才挂立绘：鼠标扫过几块名牌时不接连加载。 */
const STAND_DELAY_MS = 220;
/** 离开她这么久才卸下立绘，淡出有时间走完。 */
const STAND_RELEASE_MS = 450;
/** 立绘画布的像素比上限（spec「渲染层」）。 */
const STAND_DPR = 1.5;
/** 立绘的待机姿势：不说话，看着镜头。招呼时让她开口是 ticket 08 的事。 */
const LOOKING = { mood: "calm", speaking: false, looking: true, nod: null } as const;

type Layout = { motion: boolean; tier: Tier };

/**
 * 第 2 幕「光谱」：全部偶像的竖排日文名，按组合分段，名字和组合名都是真文本，服务端渲染。
 *
 * - 运动版式：名牌由 LightStage 摆到横滚轨道上（轨道每个组合一屏），光由着色器画；底部常驻当前组合名，
 *   可以按组合跳转。聚焦（指针移上去、键盘聚焦、手指点）时她的立绘从光里浮现：立绘压在其他人的
 *   名牌上面，只有她自己的名牌在立绘之上（原型里用户专门纠正过）。
 * - 静止版式（定格档、静态档、没有 JS）：组合一段一段竖着排，光由 CSS 画。定格档聚焦时立绘只画一帧，
 *   静态档（不支持 WebGL）没有立绘。
 *
 * 聚焦写进 stageStore，循环据此让背景过渡到她的极深底色、其余的人降成余烬；该不该挂立绘由落地页模型
 * 判断（光谱停稳、她在当前组合里），经 stageStore 传回来。推入下一个组合时放下聚焦。
 */
export function Spectrum({ units, copy }: { units: SpectrumUnit[]; copy: SpectrumCopy }) {
  const [focus, setFocus] = useState<string | null>(null);
  const [layout, setLayout] = useState<Layout | null>(null);
  const { unit, stand } = useSyncExternalStore(stageStore.subscribe, stageStore.get, stageStore.get);
  const plates = units.flatMap((u) => u.plates);
  const focusedPlate = plates.find((p) => p.id === focus) ?? null;

  useEffect(() => {
    const html = document.documentElement;
    setLayout({ motion: html.dataset.lpLayout === "motion", tier: (html.dataset.lpTier as Tier | undefined) ?? "static" });
  }, []);

  const focusOn = (id: string | null) => {
    stageStore.focus = id;
    setFocus(id);
  };
  const blur = (id: string) => {
    if (stageStore.focus !== id) return;
    stageStore.focus = null;
    setFocus(null);
  };

  // 推入下一个组合时放下聚焦，立绘不跟着跑到别的组合里。
  const lastUnit = useRef(unit);
  useEffect(() => {
    if (unit === lastUnit.current) return;
    lastUnit.current = unit;
    if (stageStore.focus && plates.find((p) => p.id === stageStore.focus)?.unit !== unit) focusOn(null);
  });

  // 运动版式：立绘跟着落地页模型（停稳了才有）；静止版式：聚焦到谁就是谁。
  const wanted = layout?.motion ? stand : layout?.tier === "reduced" ? focus : null;
  const standFor = useDelayed(wanted);
  const standPlate = plates.find((p) => p.id === standFor && p.outfit);

  const standSlot = (plate: Plate) => (
    <div
      className="lp-stand"
      data-shown={wanted === plate.id ? "" : undefined}
      data-side={plate.slot < plate.unitSize / 2 ? "after" : "before"}
      aria-hidden
    >
      <StandSlot key={plate.id} outfit={plate.outfit!} still={!layout?.motion} />
    </div>
  );

  return (
    <section
      className="lp-act2"
      aria-label={copy.label}
      data-focus={focus ?? undefined}
      style={focusedPlate ? ({ "--her-deep": focusedPlate.deep } as CSSProperties) : undefined}
    >
      <div className="lp-track">
        {units.map((u, i) => (
          <section
            key={u.name ?? ""}
            id={`lp-unit-${i}`}
            className="lp-seg"
            aria-labelledby={`lp-unit-name-${i}`}
            style={{ "--u": i } as CSSProperties}
            data-focused={focusedPlate && focusedPlate.unit === i ? "" : undefined}
          >
            <h2 id={`lp-unit-name-${i}`} className="lp-seg-name" lang={u.name ? "ja" : undefined}>
              {u.name ?? copy.others}
            </h2>
            <ol className="lp-seg-row">
              {u.plates.map((plate) => (
                <li key={plate.id} className="lp-plate-slot">
                  <button
                    type="button"
                    className="lp-plate"
                    data-lp-id={plate.id}
                    data-focused={focus === plate.id ? "" : undefined}
                    style={{ "--her-ink": plate.ink, "--her-halo": plate.halo } as CSSProperties}
                    onPointerEnter={(e) => e.pointerType === "mouse" && focusOn(plate.id)}
                    onPointerLeave={(e) => e.pointerType === "mouse" && blur(plate.id)}
                    onFocus={() => {
                      focusOn(plate.id);
                      // 键盘聚焦到别的组合里的名牌：滚过去，不让浏览器去滚横滚轨道。
                      if (layout?.motion && plate.unit !== stageStore.get().unit) stageStore.jump?.(plate.unit, true);
                    }}
                    onBlur={() => blur(plate.id)}
                    onClick={() => focusOn(plate.id)}
                  >
                    <span className="lp-plate-body">
                      {plate.number && (
                        <span className="lp-no" aria-hidden>
                          {plate.number}
                        </span>
                      )}
                      <span className="lp-name" lang="ja">
                        {plate.name}
                      </span>
                      <span className="lp-hex" aria-hidden>
                        {plate.official.toUpperCase()}
                      </span>
                    </span>
                  </button>
                  {/* 静止版式：立绘在名牌旁边，压在同一段里其他人的名牌上。 */}
                  {!layout?.motion && standPlate?.id === plate.id && standSlot(plate)}
                </li>
              ))}
            </ol>
          </section>
        ))}
        {/* 运动版式：立绘在轨道里，跟着轨道走；LightStage 把它摆到她名牌旁边空间大的一边。 */}
        {layout?.motion && (
          <div className="lp-stand" data-lp-stand={standFor ?? undefined} data-shown={stand && stand === standFor ? "" : undefined} aria-hidden>
            {standPlate && <StandSlot key={standPlate.id} outfit={standPlate.outfit!} still={false} />}
          </div>
        )}
      </div>

      {layout?.motion && units.length > 1 && (
        <nav className="lp-unitbar" aria-label={copy.jump}>
          <span className="lp-unitbar-name" lang="ja" aria-hidden>
            {units[unit]?.name ?? copy.others}
          </span>
          <ol className="lp-unitjump">
            {units.map((u, i) => (
              <li key={u.name ?? ""}>
                <button
                  type="button"
                  aria-label={copy.jumpTo[i]}
                  aria-current={i === unit ? "true" : undefined}
                  title={u.name ?? copy.others}
                  onClick={() => stageStore.jump?.(i)}
                >
                  {String(i + 1).padStart(2, "0")}
                </button>
              </li>
            ))}
          </ol>
        </nav>
      )}
    </section>
  );
}

/** 要挂立绘的人：停留一会儿才换上，离开一会儿才卸下。 */
function useDelayed(wanted: string | null): string | null {
  const [current, setCurrent] = useState<string | null>(null);
  useEffect(() => {
    if (wanted === current) return;
    const t = window.setTimeout(() => setCurrent(wanted), wanted ? STAND_DELAY_MS : STAND_RELEASE_MS);
    return () => window.clearTimeout(t);
  }, [wanted, current]);
  return current;
}

/**
 * 她的立绘：复用应用的立绘组件（独立 canvas，只盖立绘区域），穿默认衣装。素材加载不到时画布一直是空的，
 * 只剩名字和光，不报错。手机上离开她就释放 WebGL 上下文（立绘组件自己不释放，见 StandEngine.dispose）：
 * 卸下以后画布已经不在页面上了才释放，React 开发模式下 effect 重跑时画布还在，不会误伤。
 */
function StandSlot({ outfit, still }: { outfit: Outfit; still: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = box.current;
    return () => {
      const canvas = el?.querySelector("canvas");
      if (!canvas || !matchMedia("(hover: none)").matches) return;
      window.setTimeout(() => {
        if (canvas.isConnected) return;
        (canvas.getContext("webgl2") ?? canvas.getContext("webgl"))?.getExtension("WEBGL_lose_context")?.loseContext();
      }, 0);
    };
  }, []);
  return (
    <div ref={box} className="lp-stand-canvas">
      <Suspense fallback={null}>
        <Stand
          outfits={[outfit]}
          framing="knees"
          isPaused={false}
          entrance={still ? "fade" : "rise"}
          direction={LOOKING}
          isReducedMotion={still}
          isStill={still}
          maxPixelRatio={STAND_DPR}
        />
      </Suspense>
    </div>
  );
}
