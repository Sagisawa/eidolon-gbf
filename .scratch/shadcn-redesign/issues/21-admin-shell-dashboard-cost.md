# 21: 后台外壳换成 Sidebar，看板与花费换新

**What to build:** 后台的页框换成 shadcn `Sidebar`（16rem，菜单「看板 / 配置 / 用户」，底部「返回设置」，手机上收进 Sheet）。内容区顶上是 48px 的页首（`SidebarTrigger` 加面包屑）。内容列限宽、靠中：看板和用户最宽 1200px，配置和详情最宽 960px。**只有这一张改后台的 layout**，换完后删掉对旧 `AdminShell` 的使用。

看板按 `DESIGN.md` 的后台几节重做：范围用 `Tabs` 切换；数字卡分「此刻」「{范围}内」两组；服务健康只给出问题的项加琥珀色或红色的点；手写 SVG 的 `TrendChart` 和比例条只用 `--foreground` 一种颜色，悬停的槽位高亮、其余降到半透明；结果表、按角色、通话时长、花费各装一张 Card；宽表在窄屏换成 `divide-y` 的行。不引入 TanStack Table。

属于第 4 波，和 20、22、23 并行。后台各页共用一个布局，按「一屏不混搭」的要求，21、22、23 三张必须在第 4 波结束前一起合入；在此之前，新内容装在旧外壳里只是过渡状态。

**Blocked by:** 16

**Status:** ready-for-agent

- [ ] 后台的 layout、`AdminDashboard`、`DashboardParts`、`TrendChart`、`CostSection` 里没有 `@astryxdesign` 的引用
- [ ] 验收清单第 27 行：侧栏菜单和当前项、「返回设置」、手机上的 Sheet、面包屑
- [ ] 验收清单第 28–29 行：范围切换；数字卡在宽屏、中屏、手机上的排法；「数据截至」；趋势图悬停；状态点；各张表在窄屏换成行
- [ ] 验收清单第 30 行：花费
- [ ] 以上每行都在浅色、深色，手机宽度、电脑宽度下各看一遍
- [ ] CI 的 grep 检查脚本通过
- [ ] `typecheck`、`test` 通过，`next build` 成功
- [ ] 开工前已把 main 合进 `feat/shadcn-redesign`，冲突在分支里解决
