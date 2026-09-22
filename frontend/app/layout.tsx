// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
import { Pwa } from "@/components/pwa";
import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Clipo · 你的个人知识空间",
  description: "自托管的个人笔记空间，让有价值的内容留在自己手中。",
  icons: { icon: "/icon.svg", apple: "/icon-192.png" },
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, title: "Clipo", statusBarStyle: "default" },
};

export const viewport: Viewport = { themeColor: "#226552" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <Pwa />
        {children}
      </body>
    </html>
  );
}
