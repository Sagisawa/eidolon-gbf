# 01: 接入 Astryx，搭好应用外壳和视觉底座

**What to build:** 把原型里定下的视觉底座搬进正式代码：Astryx 主题（手帐纸面、事务所深蓝墨水、明暗两套）、字体、Lucide 图标、按角色注入颜色的机制，以及全站共用的页面外壳。做完之后，任何页面都能用这套底座来写；旧页面暂时保持原样。视觉以 `DESIGN.md` 为准，规则见 `../spec.md`。

**Prototype:** 原型参见 `prototype/frontend-redesign` 分支的 `frontend/src/app/prototype/`（`git switch prototype/frontend-redesign` 后 `npm run dev` 打开 `/prototype`，右下角「原型控制台」可以跳到任意状态）。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] 在根布局引入 `@astryxdesign/core/reset.css`、`astryx.css`，挂上主题（`mode="system"`）。主题从 `frontend/src/app/prototype/theme.tsx` 搬过来，放到正式位置（例如 `frontend/src/theme/`）
  - 深色模式下 Astryx 默认颜色有几处看不清，覆盖都要带上：危险红、弹层底色、弹层边线（组件覆盖的键名就是稳定类名 `.astryx-<键>`，例如 `"bottom-sheet"`）
  - 生产环境考虑用 `astryx theme build` 预构建，避免首屏闪烁
- [ ] 字体用 `next/font`：日语 M PLUS 1p（`--font-ja`），中文 Noto Sans SC（`--font-zh`）。日语原文统一用带 `lang="ja"` 的包装组件（参考原型的 `Ja.tsx`）
- [ ] 图标只用 `lucide-react`，并在主题的 `icons` 里注册 Astryx 自带图标名。不手绘 SVG
- [ ] `frontend/src/lib/imageColor.ts` 和测试保留，作为唯一的角色取色来源。原型的 `herVars.ts` 搬进正式代码，成为给子树注入角色颜色的唯一入口；界面上不得直接使用原色值
- [ ] 界面文案集中管理（例如 `frontend/src/i18n/zh.ts`），这次只有简体中文；本 ticket 建好结构，之后各 ticket 的新界面都从这里取文案
- [ ] 旧的 `globals.css` 仍放在 `@layer legacy` 里，旧页面不变；等 06 迁完所有页面后删除
- [ ] `@stylexjs/stylex` 保持为显式依赖（Astryx 运行时需要，不需要编译插件）
- [ ] 从实现分支里删除原型：`frontend/src/app/prototype/`、`frontend/public/prototype/`（包括只用于配色压力测试的「風野灯織」）。原型本身保留在 `prototype/frontend-redesign` 分支上，之后以它和 `DESIGN.md` 为参照
- [ ] `npm run typecheck`、`npm test`、`next build` 都通过

## Comments
