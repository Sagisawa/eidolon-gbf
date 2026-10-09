"use client";

// 过渡用（shadcn-redesign 第 4 波）：旧版后台页（用户列表、用户详情、封禁和限额对话框、配置、单价）还在用的
// Astryx 按钮和触控尺寸，原来在 DashboardParts 里。21 把 DashboardParts 换成了 shadcn，这几样挪到这里，
// 由 DashboardParts 转出，旧页面不用改；22、23 换掉那几页后没人再用，到时连同这个文件删掉。
import { Button } from "@astryxdesign/core/Button";
import type { ComponentProps, CSSProperties } from "react";

import { useMediaQuery } from "@/hooks/useMediaQuery";

/** 触控区下限 44px（`--spacing-11`），宽高都不小于它。 */
export const TOUCH_TARGET: CSSProperties = { minHeight: "var(--spacing-11)", minWidth: "var(--spacing-11)" };

/** 单独成行的文字链接（页内链接、返回链接）的触控区：撑到 44px 高，字仍在这一行里居中。 */
export const TOUCH_LINK: CSSProperties = { ...TOUCH_TARGET, display: "inline-flex", alignItems: "center" };

/** 后台的按钮：Astryx `Button`，手机或触屏上撑到 44px（md 默认 32px、sm 28px）。 */
export function TouchButton({ style, ...props }: ComponentProps<typeof Button>) {
  const coarse = useMediaQuery("(pointer: coarse)", false);
  const phone = !useMediaQuery("(min-width: 768px)", true);
  return <Button {...props} style={coarse || phone ?{ ...TOUCH_TARGET, ...style } : style} />;
}
