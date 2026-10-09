# 22: 后台用户列表、用户详情换新

**What to build:** 用户列表改成装在 Card 里的 shadcn `Table`：排序沿用后端的三档、点表头切换；状态用 Badge（「已封禁」`destructive`，「管理者」`secondary`，「自带密钥：…」「单独限额：…」`outline`）；有分页；宽度小于 1280px 时换成 `divide-y` 的行。

用户详情：资料是 Card 里的两列定义列表，单独限额的按钮在 `CardFooter`；近期用量一张表；删除单独一张 Card。`BanUserDialog`、`UserLimitsDialog` 和删除确认框换新，打开确认框的入口用 `outline`，真正执行的那一下用 `destructive`。行为不变。

属于第 4 波。后台各页共用一个布局，按「一屏不混搭」的要求，21、22、23 三张必须在第 4 波结束前一起合入；在此之前，新内容装在旧外壳里只是过渡状态。

**Blocked by:** 16

**Status:** ready-for-agent

- [ ] `AdminUserList`、`AdminUserDetails`、`BanUserDialog`、`UserLimitsDialog` 里没有 `@astryxdesign` 的引用；`adminUsers.test.ts` 如果引用了 Astryx 的东西，一并改掉并通过
- [ ] 验收清单第 31 行：三种排序、Badge、分页、窄屏换成行
- [ ] 验收清单第 32 行：资料、近期用量、封禁 / 解封、单独限额、删除用户的确认
- [ ] 以上每行都在浅色、深色，手机宽度、电脑宽度下各看一遍
- [ ] CI 的 grep 检查脚本通过
- [ ] `typecheck`、`test` 通过，`next build` 成功
- [ ] 开工前已把 main 合进 `feat/shadcn-redesign`，冲突在分支里解决
