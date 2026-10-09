import type { CSSProperties } from "react";

import { imageColorScale, type ModePair } from "@/lib/imageColor";

/** 按系统明暗取一对颜色中的一个。 */
export const ld = (p: ModePair) => `light-dark(${p.light}, ${p.dark})`;

/**
 * 把她的印象色注入一个子树（DESIGN.md「The Scoped Colour Rule」）：shadcn 的 `--primary`/`--primary-foreground`
 * 换成她的 accent/onAccent，`--ring` 换成她的 mark（不碰 `--accent`，那是悬停底色）；迁移期间 Astryx 的强调色也照旧换。
 * 另以 `--her-*` 给出 imageColorScale() 成对校验过的颜色。这是界面取用她颜色的唯一入口，不直接给出官方原色。
 * 通话层永远是深色，`--her-call-deep` 只有一份。
 *
 * 浮层（Dialog、DropdownMenu、Drawer 等）通过 portal 渲染到子树外面，拿不到这些变量：
 * 需要她的颜色时，把 portal 的 container 指到子树里，或在浮层内容上再展开一次 herVars()。
 */
export function herVars(color: string): CSSProperties {
  const s = imageColorScale(color);
  return {
    "--primary": ld(s.accent),
    "--primary-foreground": ld(s.onAccent),
    "--ring": ld(s.mark),
    "--her-wall": ld(s.wall),
    "--color-accent": ld(s.accent),
    "--color-text-accent": ld(s.accent),
    "--color-icon-accent": ld(s.accent),
    "--color-on-accent": ld(s.onAccent),
    "--her-mark": ld(s.mark),
    "--her-button": ld(s.button.bg),
    "--her-button-fg": ld(s.button.fg),
    "--her-call-deep": s.call.deep,
  } as CSSProperties;
}
