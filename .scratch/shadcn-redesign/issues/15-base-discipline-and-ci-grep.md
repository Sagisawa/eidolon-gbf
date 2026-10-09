# 15: 底座④：组件纪律写进文档，加 CI grep 检查

**What to build:** 后面各波的 agent 一打开 `frontend/AGENTS.md`，就能读到新代码要守的写法，CI 也会拦下违规写法。

- `frontend/AGENTS.md` 新增「shadcn 纪律（新代码）」一节，内容照抄 `../spec.md` 的「组件纪律」：布局直接写 div 加 Tailwind 类；颜色只用具名 token；有名字的尺寸用 token，任意值只用于布局约束；`ui/` 可以直接改，改处加 `// eidolon:` 标记，`shadcn add` 不带 `--overwrite`；调用处不改外观、禁止 `!`；共用件放 `components/app/`；`cn` 从 `@/lib/utils` 导入。
- 根目录 `AGENTS.md` 的 Astryx 说明保留，加一句「只适用于还没迁移的屏」。
- CI 前端 job 新增一个 grep 脚本，禁止三样：`from "cn"`（`lib/utils.ts` 除外）、任意值里的颜色（`-\[(#|oklch|rgb|hsl|var\(--)`）、`!` 前缀的 important 类。

可以和 14 并行。属于第 1 波（底座）。

**Blocked by:** 13

**Status:** ready-for-agent

- [ ] 纪律一节写入 `frontend/AGENTS.md`，`spec.md` 那边不重复写
- [ ] grep 脚本对现有代码通过；故意写一个违规样例，脚本会报错（交付时说明怎么验证的）
- [ ] CI 前端 job 的顺序是 `typecheck` → `npm test` → `theme:check` → grep 脚本
- [ ] `typecheck`、`test` 通过，`next build` 成功
- [ ] 开工前已把 main 合进 `feat/shadcn-redesign`，冲突在分支里解决
