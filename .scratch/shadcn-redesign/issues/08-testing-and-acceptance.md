# 08: 测试替换与每波验收方式

Type: grilling
Blocked by: 04
Status: open

## Question

现有 vitest 测试里依赖 Astryx 的部分（例如 `notebookTheme.test.ts`，以及 CI 里检查 `theme:build` 有没有重新运行的步骤）要删除、改写，还是换成针对 shadcn 主题变量和印象色注入的新测试？「迁移策略」（`04-migration-strategy.md`）定了两件事：每波结束时应用要能 build 并且能人工逐页验收，底座波的验收标准是旧页面没被污染。在此基础上，每波的验收是只靠人工逐页看，还是加截图对比（Playwright 截图，按浅色、深色两种模式）？截图对比的话，基准图从哪里来，算不算实现 ticket 的完成条件？
