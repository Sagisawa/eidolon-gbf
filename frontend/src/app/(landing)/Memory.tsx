import type { CSSProperties } from "react";

import type { Section } from "./model/timeline";

/**
 * 第 5 幕「记忆」：一件事被一位偶像收进记忆、传给另一位、再从她那里传开。服务端渲染，不带客户端 JS。
 *
 * 运动版式里画面是一块 three.js 画布（memoryLayer.ts）：夜空、四座浮岛和站在上面的几位演员，镜头随滚动推近、
 * 拉远、转向。画布由 LightStage 滚到这一幕附近时建、放在这一幕的最前面，固定铺满视口，不透明度和标题正文的
 * 不透明度都由落地页模型给（--lp-memory、--lp-act5）。静止版式里只有标题和正文。
 */
export function Memory({ section, title, body }: { section: Section; title: string; body: string }) {
  return (
    <div className="lp-stage-wrap lp-memory" data-lp-section={section.index} style={{ "--lp-screens": section.screens } as CSSProperties}>
      <section className="lp-stage lp-act5" aria-labelledby="lp-act5-title" data-lp-act="5">
        <div className="lp-act5-copy" data-lp-find="act5">
          <h2 id="lp-act5-title" className="lp-act-title">
            {title}
          </h2>
          <p className="lp-act-body">{body}</p>
        </div>
      </section>
    </div>
  );
}
