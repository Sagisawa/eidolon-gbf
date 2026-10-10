import type { CSSProperties } from "react";

import { memoryWorld, type BandLight } from "./model/scene";
import type { Section } from "./model/timeline";

/**
 * 第 5 幕「记忆」：一件事从一位偶像传到另一位。服务端渲染，不带客户端 JS。
 *
 * 布景是两屏宽的一张 SVG（落地页模型的 memoryWorld，viewBox 2000 × 1000，横向拉伸铺满两屏）：
 * - 回忆的光迹：几条从接收的那一位出发的曲线，运动版式里由 LightStage 按模型给的进度一条条描出来
 *   （--lp-trace-0…），整张 SVG 跟着模型的横移平移（--lp-pan）；
 * - 一道道光和传话的光路：静止版式、光层没起来时由这张 SVG 画；光层画好以后让给着色器
 *   （光点是一颗沿同一条弧线走的彗星）。
 * 静止版式（定格档、静态档、没有 JS）里整张布景压进一屏，光路和光迹都是画完的样子。
 *
 * 光和光路的线宽不随布景拉伸（non-scaling-stroke）；光迹不能这样：描线用的虚线按 pathLength 换算，
 * 线宽不随布景拉伸时虚线改在屏幕上量，描不出进度。光迹的线宽跟着布景缩放，竖屏上由样式表加粗。
 */
export function Memory({ lights, section, title, body }: { lights: BandLight[]; section: Section; title: string; body: string }) {
  const world = memoryWorld(lights);
  const v = (x: number) => Math.round(x * 1000);
  const sender = lights.find((l) => l.id === world.sender);
  const receiver = lights.find((l) => l.id === world.receiver);
  const { from, ctrl, to } = world.arc;
  return (
    <div className="lp-stage-wrap lp-memory" data-lp-section={section.index} style={{ "--lp-screens": section.screens } as CSSProperties}>
      <section className="lp-stage lp-act5" aria-labelledby="lp-act5-title">
        <svg className="lp-memory-world" viewBox="0 0 2000 1000" preserveAspectRatio="none" aria-hidden>
          <defs>
            {sender && receiver && (
              <linearGradient id="lp-relay" gradientUnits="userSpaceOnUse" x1={v(from[0])} y1="0" x2={v(to[0])} y2="0">
                <stop offset="0" stopColor={sender.color} />
                <stop offset="1" stopColor={receiver.color} />
              </linearGradient>
            )}
          </defs>
          <g className="lp-memory-static">
            {world.lines.map((line) => {
              const lit = line.id === world.sender || line.id === world.receiver;
              return (
                <g key={line.id} opacity={lit ? 0.9 : 0.32}>
                  <line x1={v(line.x)} y1="0" x2={v(line.x)} y2="1000" stroke={line.color} strokeWidth="10" strokeOpacity="0.35" vectorEffect="non-scaling-stroke" />
                  <line x1={v(line.x)} y1="0" x2={v(line.x)} y2="1000" stroke="#fff" strokeOpacity="0.8" strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
                </g>
              );
            })}
            {sender && receiver && (
              <path
                d={`M${v(from[0])} ${v(from[1])} Q${v(ctrl[0])} ${v(ctrl[1])} ${v(to[0])} ${v(to[1])}`}
                fill="none"
                stroke="url(#lp-relay)"
                strokeWidth="2"
                vectorEffect="non-scaling-stroke"
              />
            )}
          </g>
          {receiver &&
            world.traces.map((d, k) => (
              <g key={d} className="lp-trace" style={{ "--lp-trace": `var(--lp-trace-${k}, 1)` } as CSSProperties}>
                <path d={d} pathLength={1} fill="none" stroke={receiver.color} strokeOpacity="0.28" strokeWidth="7" />
                <path d={d} pathLength={1} fill="none" stroke="#fff" strokeOpacity="0.85" strokeWidth="1.2" />
              </g>
            ))}
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
