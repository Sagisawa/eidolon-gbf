import type { CSSProperties } from "react";

import { memoryWorld, type BandLight } from "./model/scene";
import type { Section } from "./model/timeline";

/**
 * 第 5 幕「记忆」：一件事从一位偶像传到另一位，再从她那里传开。服务端渲染，不带客户端 JS。
 *
 * 布景是两屏宽的一张 SVG（落地页模型的 memoryWorld，viewBox 2000 × 1000，横向拉伸铺满两屏）：
 * - 光路的连线：一段段弧线，颜色从这段路起点的那一位渐变到终点的那一位。运动版式里由 LightStage 按模型
 *   给的进度画出来（--lp-path-0…，光点走到哪儿画到哪儿），整张 SVG 跟着模型的横移平移（--lp-pan）；
 *   光点本身是着色器画的彗星。
 * - 一道道光：静止版式、光层没起来时由这张 SVG 画，这件事传过的人亮着；光层画好以后让给着色器。
 * 静止版式（定格档、静态档、没有 JS）里整张布景压进一屏，连线都是画完的样子。
 *
 * 光的线宽不随布景拉伸（non-scaling-stroke）；连线不能这样：描线用的虚线按 pathLength 换算，线宽不随布景
 * 拉伸时虚线改在屏幕上量，描不出进度。连线的线宽跟着布景缩放，竖屏上由样式表加粗。
 */
export function Memory({ lights, section, title, body }: { lights: BandLight[]; section: Section; title: string; body: string }) {
  const world = memoryWorld(lights);
  const v = (x: number) => Math.round(x * 1000);
  const colorOf = new Map(lights.map((l) => [l.id, l.color]));
  const reached = new Set(world.arcs.flatMap((a) => [a.source, a.target]));
  return (
    <div className="lp-stage-wrap lp-memory" data-lp-section={section.index} style={{ "--lp-screens": section.screens } as CSSProperties}>
      <section className="lp-stage lp-act5" aria-labelledby="lp-act5-title" data-lp-act="5">
        <svg className="lp-memory-world" viewBox="0 0 2000 1000" preserveAspectRatio="none" aria-hidden>
          <defs>
            {world.arcs.map((a, k) => (
              <linearGradient key={k} id={`lp-path-${k}`} gradientUnits="userSpaceOnUse" x1={v(a.from[0])} y1={v(a.from[1])} x2={v(a.to[0])} y2={v(a.to[1])}>
                <stop offset="0" stopColor={colorOf.get(a.source)} />
                <stop offset="1" stopColor={colorOf.get(a.target)} />
              </linearGradient>
            ))}
          </defs>
          <g className="lp-memory-static">
            {world.lines.map((line) => (
              <g key={line.id} opacity={reached.has(line.id) ? 0.9 : 0.32}>
                <line x1={v(line.x)} y1="0" x2={v(line.x)} y2="1000" stroke={line.color} strokeWidth="10" strokeOpacity="0.35" vectorEffect="non-scaling-stroke" />
                <line x1={v(line.x)} y1="0" x2={v(line.x)} y2="1000" stroke="#fff" strokeOpacity="0.8" strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
              </g>
            ))}
          </g>
          {world.arcs.map((a, k) => {
            const d = `M${v(a.from[0])} ${v(a.from[1])} Q${v(a.ctrl[0])} ${v(a.ctrl[1])} ${v(a.to[0])} ${v(a.to[1])}`;
            return (
              <g key={k} className="lp-path" style={{ "--lp-path": `var(--lp-path-${k}, 1)` } as CSSProperties}>
                <path d={d} pathLength={1} fill="none" stroke={`url(#lp-path-${k})`} strokeOpacity="0.22" strokeWidth="7" />
                <path d={d} pathLength={1} fill="none" stroke={`url(#lp-path-${k})`} strokeOpacity="0.75" strokeWidth="1.4" />
              </g>
            );
          })}
        </svg>
        <div className="lp-act5-copy">
          <h2 id="lp-act5-title" className="lp-act-title">
            {title}
          </h2>
          <p className="lp-act-body">{body}</p>
        </div>
      </section>
    </div>
  );
}
