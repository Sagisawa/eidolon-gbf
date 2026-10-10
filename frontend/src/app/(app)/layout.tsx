import "../globals.css";

import type { Metadata } from "next";
import { LINE_Seed_JP, Noto_Sans_SC } from "next/font/google";

import { copy } from "@/i18n";

// 中文正文用 Noto Sans SC，她的日语原文用 LINE Seed JP（经 <Ja> 取用）。
// 两者都是很大的 CJK 字体，Google Fonts 按 unicode-range 切片按需下载；不预载，避免首屏拉整套字。
// 每个字重的每个切片各一条 @font-face，都在阻塞渲染的 CSS 里。Noto Sans SC 不给字重就是可变字体（wght 100–900），
// 一套切片覆盖界面用到的 400–700，字体 CSS 少四分之三。
const zh = Noto_Sans_SC({ subsets: ["latin"], variable: "--font-zh", preload: false });
// 日语只用到 400（<Ja> 外面最粗是 font-medium，在 400/700 里本来就取 400），不载 700，少一半字体 CSS。
// LINE Seed JP 在 next/font 里没有 fallback 度量，构建时会提示一句，无害。
const ja = LINE_Seed_JP({ weight: "400", subsets: ["latin"], variable: "--font-ja", preload: false });

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
