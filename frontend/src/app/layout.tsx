import "./globals.css";

import type { Metadata } from "next";
import { LINE_Seed_JP, Noto_Sans_SC } from "next/font/google";

import { copy } from "@/i18n";

// 中文正文用 Noto Sans SC，她的日语原文用 LINE Seed JP（经 <Ja> 取用）。
// 两者都是很大的 CJK 字体，Google Fonts 按 unicode-range 切片按需下载；不预载，避免首屏拉整套字。
const zh = Noto_Sans_SC({ weight: ["400", "500", "600", "700"], subsets: ["latin"], variable: "--font-zh", preload: false });
// LINE Seed JP 在 next/font 里没有 fallback 度量，构建时会提示一句，无害。
const ja = LINE_Seed_JP({ weight: ["400", "700"], subsets: ["latin"], variable: "--font-ja", preload: false });

export const metadata: Metadata = {
  title: copy.app.name,
  description: copy.app.description,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className={`${zh.variable} ${ja.variable}`}>
      <body>{children}</body>
    </html>
  );
}
