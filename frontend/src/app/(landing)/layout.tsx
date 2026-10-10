import "../globals.css";
import "./landing.css";

import type { Metadata } from "next";

import { copy } from "@/i18n";

export const metadata: Metadata = {
  title: copy.app.name,
  description: copy.app.description,
};

/**
 * 落地页自己的根 layout（ADR-0016 修订）：不加载应用根 layout 里 next/font 的 CJK 字体，那些切片 CSS
 * 会阻塞首屏；全局样式表只为登录面板和按钮（shadcn）引入。永远深色，不跟随系统。
 * 和应用之间跳转是整页加载。
 */
export default function LandingLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className="dark">
      <body>{children}</body>
    </html>
  );
}
