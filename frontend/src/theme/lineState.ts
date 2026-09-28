import type { CSSProperties } from "react";

/**
 * 线形状态（DESIGN.md「The Line-State Rule」）：实线下划线=通话中，虚线下划线=正在呼叫，删除线=已结束；
 * 2px 粗、6px 偏移，线色取她的 rule 色（纸面上 `--her-note-rule`，通话层上 `--her-call-rule`）。
 */
export function lineState(line: "dashed" | "solid" | "struck", color: string): CSSProperties {
  return {
    textDecorationLine: line === "struck" ? "line-through" : "underline",
    textDecorationStyle: line === "dashed" ? "dashed" : "solid",
    textDecorationColor: color,
    textDecorationThickness: "var(--spacing-0-5)",
    textUnderlineOffset: "var(--spacing-1-5)",
  };
}
