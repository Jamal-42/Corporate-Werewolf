import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI 职场狼人杀 Agent Arena",
  description: "多智能体协作与博弈观战驾驶舱"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
