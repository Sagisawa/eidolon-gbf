# 16: 共用件：新版组件建在旧版旁边

**What to build:** 后面各屏要用的新版共用件全部就位，但还没有任何页面在用。

- 用 `shadcn add` 加入要用的 `ui/` 组件：Button、Alert、Empty、Dialog、AlertDialog、Drawer、Sheet、Field、Toggle Group、Tabs、Sidebar、Card、Badge、Table、Resizable、DropdownMenu、Popover，以及官方聊天组件（Message、Bubble、Message Scroller），按需取用。生成的 `from "cn"` 当场改掉；改过的地方加 `// eidolon:`。
- 在 `components/app/` 新建项目共用件，文件名和旧版相同：页框 `PageShell`、页首 `SubpageHeader`、区块卡 `SettingsSection`、失败提示 `FailureNotice`、链接 `AppLink`、带标记的头像 `MarkedAvatar`。
- 在 `components/app/admin/` 新建 `AdminPage`、统计卡、Sidebar 外壳。
- 再补上盘点里要自己写的通用件：StatusDot、Timestamp、MetadataList、NumberInput、`useMediaQuery`。

全部在示例路由里展示一遍（浅色、深色）。旧组件一个都不动。视觉按 `DESIGN.md`。属于第 2 波。

**Blocked by:** 14、15

**Status:** ready-for-agent

- [ ] 验收清单第 4 行：示例路由里每个共用件在浅色、深色下都正常；旧页面不受影响
- [ ] 后台 Card 保留默认的 `ring-1` 细线，用户侧的东西不加描边环、不投影（Flat Rule）
- [ ] 截图脚本重拍后，和第 12 张拍的基准图像素零差异（范围：登录、法务、后台各页的静态部分）
- [ ] CI 的 grep 检查脚本通过
- [ ] `typecheck`、`test` 通过，`next build` 成功
- [ ] 开工前已把 main 合进 `feat/shadcn-redesign`，冲突在分支里解决
