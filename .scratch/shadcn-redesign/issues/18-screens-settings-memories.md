# 18: 设置、记忆换新

**What to build:** 设置页的每一节（制作人档案、登录方式、通话设置、自带密钥、删除账号、管理者才看得到的后台入口）和记忆页改用新版共用件和 shadcn 组件，整屏不再出现 Astryx 组件，视觉按 `DESIGN.md`。删除类确认框里真正执行的那一下用 `destructive`（挂断红）。麦克风选择的当前项铺中性的 `bg-muted`。行为、文案不变。属于第 3 波，和 17、19 并行。

**Blocked by:** 16

**Status:** ready-for-agent

- [ ] 设置页、记忆页及其组件（`ProducerProfileSettings`、`SignInSettings`、`CallSettings`、`OwnKeysSettings`、`DeleteAccount`、`AdminEntry`）里没有 `@astryxdesign` 的引用
- [ ] 验收清单第 8–11 行：制作人档案的查看、修改和保存失败；登录方式的绑定、解绑和失败；通话设置；自带密钥的填写、保存和失败；删除账号的确认；管理者看得到后台入口，普通用户看不到
- [ ] 验收清单第 12 行：记忆列表、空状态、加载失败、删除一条的确认、清空的确认
- [ ] 以上每行都在浅色、深色，手机宽度、电脑宽度下各看一遍
- [ ] CI 的 grep 检查脚本通过
- [ ] `typecheck`、`test` 通过，`next build` 成功
- [ ] 开工前已把 main 合进 `feat/shadcn-redesign`，冲突在分支里解决
