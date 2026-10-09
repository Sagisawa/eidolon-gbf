# 23: 后台配置与单价换新

**What to build:** 配置页每一项一张 Card：标题旁边用 Badge 标出「已被后台覆盖」（`secondary`）或「覆盖没有生效」（`outline`）；右上角 `CardAction` 放「修改」。没有覆盖时内容是定义列表；有覆盖时是「项 / .env 的值 / 当前生效」的表，被盖掉的 .env 值划掉。点「修改」就在这张卡里展开 `FieldGroup` 表单，全页同一时间只开一张；「恢复成 .env 的值」放在 `CardFooter`。单价也是一张卡，「修改」在被修改的那一行下面展开（这是全后台唯一一处行展开）。提交键用 `default`，取消用 ghost。行为不变。

属于第 4 波。后台各页共用一个布局，按「一屏不混搭」的要求，21、22、23 三张必须在第 4 波结束前一起合入；在此之前，新内容装在旧外壳里只是过渡状态。

**Blocked by:** 16

**Status:** ready-for-agent

- [ ] `AdminConfig`、`AdminPrices`、`OpenForm` 里没有 `@astryxdesign` 的引用
- [ ] 验收清单第 33 行：每项一张卡、两种 Badge、展开表单、同时只开一张、「试调并保存」和失败提示、恢复成 .env 的值
- [ ] 验收清单第 34 行：单价表行下展开修改、保存、取消
- [ ] 以上每行都在浅色、深色，手机宽度、电脑宽度下各看一遍
- [ ] CI 的 grep 检查脚本通过
- [ ] `typecheck`、`test` 通过，`next build` 成功
- [ ] 开工前已把 main 合进 `feat/shadcn-redesign`，冲突在分支里解决
