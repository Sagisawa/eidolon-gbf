"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";

import type { Outfit } from "@/lib/api";
import type { StandDirection } from "@/lib/standAnimations";

import { loadSpineRuntime } from "./spineRuntime";
import { StandEngine, type Framing } from "./StandEngine";

type Props = {
  outfit: Outfit;
  framing: Framing;
  /** 通话层收起时暂停渲染，展开时从当前姿势接着画。 */
  isPaused: boolean;
  /** 到了之后怎么出现：手机「大立绘」从底部升起；电脑和减少动态效果时原地淡入。 */
  entrance: "rise" | "fade";
  /** 她现在该是什么样子（spec「立绘指令」）。 */
  direction: StandDirection;
  /** 减少动态效果：身体动作一律用待机，从下一个动作开始生效。 */
  isReducedMotion: boolean;
};

/**
 * 通话层上的立绘（spec「通话层」）：铺满外框的一块画布，外框的位置和大小由通话层决定。
 * 加载中什么都不画（只露出背景图和纱），到了用 0.3 秒淡入。runtime 或素材加载不到、
 * 浏览器不支持 WebGL 时整块去掉，同样只剩背景图，不提示用户；换一通电话（重新挂载）再试。
 */
export function Stand({ outfit, framing, isPaused, entrance, direction, isReducedMotion }: Props) {
  // 按衣装的值而不是对象来载入：角色列表重新拉取时，同一套衣装不会让立绘重新载入。
  const { id, url } = outfit;
  const canvas = useRef<HTMLCanvasElement>(null);
  const engine = useRef<StandEngine | null>(null);
  const [phase, setPhase] = useState<"loading" | "shown" | "failed">("loading");

  // 引擎要等 runtime 和素材，晚于这几个 effect 创建：创建时按这里记下的最新取景、暂停状态和立绘指令来。
  const current = useRef({ framing, isPaused, direction, isReducedMotion });

  useEffect(() => {
    current.current.framing = framing;
    if (engine.current) engine.current.framing = framing;
  }, [framing]);

  useEffect(() => {
    current.current.isPaused = isPaused;
    engine.current?.setPaused(isPaused);
  }, [isPaused]);

  useEffect(() => {
    current.current.direction = direction;
    current.current.isReducedMotion = isReducedMotion;
    engine.current?.direct(direction, isReducedMotion);
  }, [direction, isReducedMotion]);

  useEffect(() => {
    const target = canvas.current;
    if (!target) return;
    let cancelled = false;
    let created: StandEngine | null = null;
    loadSpineRuntime()
      .then((spine) => {
        if (cancelled) return;
        created = new StandEngine(target, spine, current.current.framing);
        created.setPaused(current.current.isPaused);
        created.direct(current.current.direction, current.current.isReducedMotion);
        engine.current = created;
        return created.load({ id, url }).then(() => {
          if (!cancelled) setPhase("shown");
        });
      })
      .catch(() => {
        if (cancelled) return;
        created?.dispose();
        engine.current = null;
        setPhase("failed");
      });
    return () => {
      cancelled = true;
      created?.dispose();
      engine.current = null;
    };
  }, [id, url]);

  if (phase === "failed") return null;
  const shown = phase === "shown";
  return (
    <canvas
      ref={canvas}
      aria-hidden
      style={{
        ...fill,
        opacity: shown ? 1 : 0,
        transform: entrance === "rise" && !shown ? "translateY(12%)" : "none",
        transition: `opacity ${fadeIn}, transform var(--duration-medium) var(--ease-standard)`,
      }}
    />
  );
}

/** 画布铺满外框；它是 WebGL 的绘制面，没有对应的 Astryx 组件。 */
const fill: CSSProperties = { display: "block", width: "100%", height: "100%" };

/** 立绘到了之后的淡入：0.3 秒（spec「通话层」），取最接近的时长令牌。 */
const fadeIn = "var(--duration-medium-min) linear";
