import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Eidolon-SC",
  description: "和 283 事务所的偶像说说话",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
