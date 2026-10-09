# 24: 清理：移除 Astryx，最后完整走一遍

**What to build:** 仓库里只剩一套组件体系，分支可以合进 main。要删掉的：

- `@astryxdesign/*`、`@stylexjs/stylex` 两个依赖；
- 共存用的层顺序和 base 层重置；
- 临时示例路由；
- 旧版共用件和不再使用的旧组件（如 `AdminPlaceholder`）；
- `astryxIcons.ts`、`notebookTheme.ts`；
- `notebookTheme.test.ts` 和剩下的旧断言（`--color-accent` 等），以及还没删的旧颜色对；
- `theme:build`/`theme:check` 两个脚本、CI 里的 `theme:check` 一步，以及 `theme/built/`。

CI 的 grep 脚本加入 `@astryxdesign`。删掉根目录 `AGENTS.md` 和 `frontend/AGENTS.md` 里的 Astryx 部分（包括 Astryx CLI 的说明），保留「shadcn 纪律」一节。`README.md` 里关于手帐主题、通话便利贴的描述改成现在的样子。新共用件不搬家、不改名。属于第 5 波。

**Blocked by:** 17、18、19、20、21、22、23

**Status:** ready-for-agent

- [ ] `grep -r @astryxdesign src` 结果为零，CI 的 grep 脚本把它当作违规
- [ ] 依赖、脚本、生成产物、旧测试都已删掉，剩下的测试全部通过
- [ ] 验收清单第 35 行：用 `next build` + `next start` 把清单第 5–34 行从头走一遍（浅色、深色，手机、电脑；用户侧、后台、法务），CI 全绿
- [ ] 截图脚本把全部页面重拍一套，附在合进 main 的 PR 里
- [ ] `typecheck`、`test` 通过，`next build` 成功
- [ ] 开工前已把 main 合进 `feat/shadcn-redesign`，冲突在分支里解决
