import type { ReactNode } from "react";

/**
 * 她说的日语原文：标上 lang="ja"，换成 LINE Seed JP（`--font-ja`，根布局用 next/font 载入）。
 * Astryx 的 Text/Stack 不接受 lang，所以用一个不参与布局的语义 span（display: contents），
 * 外面照常用 Text 定字号，例如 `<Text type="large" weight="normal"><Ja>…</Ja></Text>`。
 */
export function Ja({ children }: { children: ReactNode }) {
  return (
    <span lang="ja" style={{ display: "contents", fontFamily: "var(--font-ja), var(--font-family-body)" }}>
      {children}
    </span>
  );
}
