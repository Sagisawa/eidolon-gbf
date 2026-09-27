import type { CSSProperties } from "react";

import { imageColorScale, type ModePair } from "@/lib/imageColor";

/** 按系统明暗取一对颜色中的一个。 */
export const ld = (p: ModePair) => `light-dark(${p.light}, ${p.dark})`;

/**
 * 把她的印象色注入一个子树（DESIGN.md「The Scoped Colour Rule」）：Astryx 的强调色换成她的，
 * 另以 `--her-*` 给出 imageColorScale() 成对校验过的颜色。这是界面取用她颜色的唯一入口，
 * 官方原色只作通话层头像背后的光晕（`--her-call-glow`，纯装饰）。
 */
export function herVars(color: string): CSSProperties {
  const s = imageColorScale(color);
  return {
    "--color-accent": ld(s.accent),
    "--color-accent-muted": ld(s.paper),
    "--color-text-accent": ld(s.accent),
    "--color-icon-accent": ld(s.accent),
    "--color-on-accent": ld(s.onAccent),
    "--her-mark": ld(s.mark),
    "--her-paper": ld(s.paper),
    "--her-paper-muted": ld(s.paperMuted),
    "--her-note": ld(s.note),
    "--her-note-rule": ld(s.noteRule),
    "--her-button": ld(s.button.bg),
    "--her-button-fg": ld(s.button.fg),
    "--her-call-top": s.call.top,
    "--her-call-deep": s.call.deep,
    "--her-call-glow": s.call.glow,
    "--her-call-rule": s.call.rule,
  } as CSSProperties;
}
