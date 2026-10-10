# 01: 应用根 layout 的 CJK 字体拖慢所有页面的 LCP

**Status:** needs-triage

**Blocked by:** None

## 现象

应用的根 layout（`frontend/src/app/layout.tsx`）用 `next/font/google` 加载 Noto Sans SC 和 LINE Seed JP。Google Fonts 按 unicode-range 把 CJK 字体切成很多片，next/font 为这些切片生成的 `@font-face` CSS 会阻塞渲染。

在落地页原型（`prototype/landing-page` 分支的 `3d07693`）的测量中顺带发现：`/privacy` 在手机 4G 节流下 LCP 约 3 秒，拦掉这些 CSS 后约 0.6 秒。所有挂在根 layout 下的页面都受影响。复测脚本在原型分支的 `frontend/scripts/landing-prototype-measure.mjs`。

## 范围

不并进落地页的规格：落地页会拆出自己的根 layout、自托管字体子集（ADR-0016 的 2026-10-10 修订），不受这个问题影响。这里只管应用本身的页面。

## 待定

- 应用里的中文和日文是动态内容（对话、记忆、角色回复），不能像落地页那样按固定文本做子集。可选的方向有：自托管 Google 的切片但让 CSS 不阻塞渲染、只预载最常用的切片、或者正文退回系统字体，只给日语原文用 web font。
- 改完要对照 DESIGN.md 的字体规范，确认视觉没有变化。

## Comments
