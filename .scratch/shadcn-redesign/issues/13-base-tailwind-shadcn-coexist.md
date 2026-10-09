# 13: 底座②：Tailwind + shadcn 与 Astryx 并存

**What to build:** 在旧页面一个像素都不变的前提下接入新底座：

- Tailwind v4（`@tailwindcss/postcss`）。
- `shadcn init -b base -p nova`（底层 Base UI，样式 `base-nova`）。init 会把根布局字体换成 Geist、生成自引用的 `--font-sans`，都要撤掉。CLI 报 `EALLOWSCRIPTS` 时，用 `NPM_CONFIG_USERCONFIG` 指向一份临时 npmrc 绕开。
- 主题以 shadcn neutral 为底，只覆盖 `--destructive`（挂断红）和深色浮层边线，并把 `notebookTheme.ts` 里还成立的深色修补和对比度决定搬进来。
- 共存用的 CSS 层顺序：`reset, theme, base, astryx-base, astryx-theme, components, utilities`。
- 在 Tailwind 的 `base` 层把 `h1`–`h6`、`p`、`small` 改回 `color: inherit; font: inherit`。

新增主题对比度测试（替代 `notebookTheme.test.ts` 的角色，旧测试先保留）。

每一步单独提交，每个提交都要和基准图像素零差异。属于第 1 波（底座）。

**Blocked by:** 12（字体已经确认，基准图已经拍好）

**Status:** ready-for-agent

- [ ] `components.json` 是 `base-nova`，`cn` 从 `@/lib/utils` 导出
- [ ] 主题对比度测试覆盖：`--muted-foreground` 在 `--background` 和 `--muted` 上 ≥ 4.5；`--destructive` 上的白字 ≥ 4.5；深色浮层边线和浮层底、页面底都 ≥ 3。浅色、深色两种模式都测
- [ ] `notebookTheme.test.ts`、`herVars.test.ts` 的旧断言和 CI 的 `theme:check` 照常通过
- [ ] 截图脚本重拍后，和第 12 张拍的基准图像素零差异（范围：登录、法务、后台各页的静态部分）
- [ ] `typecheck`、`test` 通过，`next build` 成功
- [ ] 开工前已把 main 合进 `feat/shadcn-redesign`，冲突在分支里解决
