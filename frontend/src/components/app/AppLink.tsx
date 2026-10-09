"use client";

import NextLink from "next/link";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

type Props = ComponentProps<typeof NextLink> & {
  /** 独立成行的链接（页内导航、「返回列表」）：不画下划线，悬停才画。 */
  isStandalone?: boolean;
};

/**
 * 站内链接：Next 的客户端跳转，前景色。句中的链接画下划线，否则和正文分不出来；独立成行的不画。
 * 包成客户端组件，服务端渲染的页面（隐私政策、使用条款）也能用。
 */
export function AppLink({ isStandalone = false, className, ...props }: Props) {
  return (
    <NextLink
      {...props}
      className={cn(
        "rounded-sm text-foreground underline-offset-4 outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
        isStandalone ? "font-medium hover:underline" : "underline",
        className,
      )}
    />
  );
}
