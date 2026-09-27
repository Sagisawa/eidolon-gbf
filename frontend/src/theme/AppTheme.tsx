"use client";

import { Theme } from "@astryxdesign/core/theme";
import type { ReactNode } from "react";

import { eidolonNotebookTheme } from "./built/eidolon-notebook";

/**
 * 全站的 Astryx 主题，明暗跟随系统。用的是 `npm run theme:build` 预构建的主题：
 * 令牌和组件覆盖都在根布局引入的 built/notebookTheme.css 里，服务端渲染的首屏就带着，
 * 不会在水合后才注入而闪一下。主题对象里有图标（React 元素），所以在客户端组件里取用。
 */
export function AppTheme({ children }: { children: ReactNode }) {
  return (
    <Theme theme={eidolonNotebookTheme} mode="system">
      {children}
    </Theme>
  );
}
