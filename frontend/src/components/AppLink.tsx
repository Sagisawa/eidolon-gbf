"use client";

import { Link, type LinkProps } from "@astryxdesign/core/Link";
import NextLink from "next/link";

/**
 * 站内链接：Astryx Link 的样式，Next 的客户端跳转。
 * 包成客户端组件，服务端渲染的页面（隐私政策、使用条款）也能用：组件本身不能作为 prop 从服务端传给客户端。
 *
 * 句中的链接默认带下划线：全站只有一种墨水（DESIGN.md「The One Ink Rule」），强调色和正文同色，
 * 不画线就看不出是链接。独立成行的链接（isStandalone）不画。
 */
export function AppLink({ hasUnderline, isStandalone, ...props }: Omit<LinkProps, "as">) {
  return (
    <Link {...props} isStandalone={isStandalone} hasUnderline={hasUnderline ?? !isStandalone} as={NextLink} />
  );
}
