import "@astryxdesign/core/reset.css";
import "@astryxdesign/core/astryx.css";

import type { Metadata } from "next";
import { M_PLUS_1p, Noto_Sans_SC } from "next/font/google";

import { PrototypeTheme } from "./PrototypeTheme";

const ja = M_PLUS_1p({ weight: ["400", "500", "700"], subsets: ["latin"], variable: "--font-ja", preload: false });
const zh = Noto_Sans_SC({ weight: ["400", "500", "700"], subsets: ["latin"], variable: "--font-zh", preload: false });

export const metadata: Metadata = { title: "原型 · Eidolon-SC", robots: { index: false } };

export default function PrototypeLayout({ children }: { children: React.ReactNode }) {
  return (
    <PrototypeTheme className={`${ja.variable} ${zh.variable}`}>{children}</PrototypeTheme>
  );
}
