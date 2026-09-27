// 层的先后要在任何样式之前声明，所以 layers.css 必须第一个引入。
import "./layers.css";
import "@astryxdesign/core/reset.css";
import "@astryxdesign/core/astryx.css";
import "@/theme/built/notebookTheme.css";

import type { Metadata } from "next";
import { M_PLUS_1p, Noto_Sans_SC } from "next/font/google";

import { copy } from "@/i18n";
import { AppTheme } from "@/theme/AppTheme";

// 中文正文用 Noto Sans SC，她的日语原文用 M PLUS 1p（经 <Ja> 取用）。
// 两者都是很大的 CJK 字体，Google Fonts 按 unicode-range 切片按需下载；不预载，避免首屏拉整套字。
const zh = Noto_Sans_SC({ weight: ["400", "500", "700"], subsets: ["latin"], variable: "--font-zh", preload: false });
const ja = M_PLUS_1p({ weight: ["400", "500", "700"], subsets: ["latin"], variable: "--font-ja", preload: false });

export const metadata: Metadata = {
  title: copy.app.name,
  description: copy.app.description,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className={`${zh.variable} ${ja.variable}`}>
      <body>
        <AppTheme>{children}</AppTheme>
      </body>
    </html>
  );
}
