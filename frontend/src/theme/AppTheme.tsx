"use client";

import { InternationalizationProvider } from "@astryxdesign/core/i18n";
import zhCN from "@astryxdesign/core/locales/zh-CN.json";
import { Theme } from "@astryxdesign/core/theme";
import type { ReactNode } from "react";

import { eidolonNotebookTheme } from "./built/eidolon-notebook";

/**
 * 全站的 Astryx 主题，明暗跟随系统。用的是 `npm run theme:build` 预构建的主题：
 * 令牌和组件覆盖都在根布局引入的 built/notebookTheme.css 里，服务端渲染的首屏就带着，
 * 不会在水合后才注入而闪一下。主题对象里有图标（React 元素），所以在客户端组件里取用。
 *
 * Astryx 组件自带的文字（输入框占位、「更多选项」「发送」「滚动到底部」等）用它随包附带的
 * 简体中文目录，界面语言与 `@/i18n` 一致。以后加日语界面时，这里跟着换 locale。
 */
export function AppTheme({ children }: { children: ReactNode }) {
  return (
    <InternationalizationProvider locale="zh-CN" messages={{ "zh-CN": zhCN }}>
      <Theme theme={eidolonNotebookTheme} mode="system">
        {children}
      </Theme>
    </InternationalizationProvider>
  );
}
