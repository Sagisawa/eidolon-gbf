import { Avatar } from "@astryxdesign/core/Avatar";
import type { CSSProperties } from "react";

import { herVars } from "@/theme/herVars";

type Props = {
  name: string;
  src?: string | null;
  /** 她的印象色；没有（例如来源角色已不在）时不画描边。 */
  color?: string | null;
  size?: "sm" | "md" | "lg";
};

/**
 * 角色头像，外面一圈 2px 她的 mark 色描边（DESIGN.md「Avatar ring」）。
 * 颜色经 herVars() 注入，只取成对校验过的 `--her-mark`，不直接用原色。
 */
export function MarkedAvatar({ name, src, color, size = "lg" }: Props) {
  const ring: CSSProperties | undefined = color
    ? { ...herVars(color), boxShadow: "0 0 0 var(--spacing-0-5) var(--her-mark)" }
    : undefined;
  return <Avatar name={name} src={src ?? undefined} size={size} tooltip={false} style={ring} />;
}
