import type { CSSProperties } from "react";

import { imageColorScale, type ModePair } from "@/lib/imageColor";

/** 按系统明暗取一对颜色中的一个。 */
export const ld = (p: ModePair) => `light-dark(${p.light}, ${p.dark})`;

/**
 * 把她的印象色注入一个子树（DESIGN.md「The Scoped Colour Rule」）：shadcn 的 `--primary`/`--primary-foreground`
 * 换成她的 accent/onAccent，`--ring` 换成她的 mark（不碰 `--accent`，那是悬停底色）；迁移期间 Astryx 的强调色也照旧换。
 * 另以 `--her-*` 给出 imageColorScale() 成对校验过的颜色。这是界面取用她颜色的唯一入口，
 * 官方原色只作通话层头像背后的光晕（`--her-call-glow`，纯装饰）。
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
    "--color-accent-muted": ld(s.paper),
    "--color-text-accent": ld(s.accent),
    "--color-icon-accent": ld(s.accent),
    "--color-on-accent": ld(s.onAccent),
    "--her-mark": ld(s.mark),
    "--her-paper": ld(s.paper),
    "--her-paper-muted": ld(s.paperMuted),
    "--her-button": ld(s.button.bg),
    "--her-button-fg": ld(s.button.fg),
    "--her-call-top": s.call.top,
    "--her-call-deep": s.call.deep,
    "--her-call-glow": s.call.glow,
    "--her-call-rule": s.call.rule,
  } as CSSProperties;
}

/**
 * 消息列表里她那一行（通话中的麦克风列表也用它）：这些行不在她的子树里，所以每行只带上自己要用的颜色。
 * 头像描边取 `--her-mark`；选中行铺她的 paper，行里的次要字换成 paperMuted（DESIGN.md「Conversation list」）。
 */
export function listRow(color: string, selected: boolean): CSSProperties {
  const s = imageColorScale(color);
  return {
    "--her-mark": ld(s.mark),
    ...(selected && { background: ld(s.paper), "--color-text-secondary": ld(s.paperMuted) }),
  } as CSSProperties;
}
