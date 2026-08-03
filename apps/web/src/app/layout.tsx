import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI 产品设计与验证平台",
  description: "Documentation First 的 AI 产品设计与验证工作台",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
