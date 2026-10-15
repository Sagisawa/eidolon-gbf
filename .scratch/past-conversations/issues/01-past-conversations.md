# 01: 历史对话面板、只读的历史对话和菜单图标

**What to build:** 对话页「更多」菜单加一项「历史对话」。点开后宽屏是 Dialog、窄屏是 Drawer，列出和她的所有对话，当前对话在最上面；点一段就在 `?c=<id>` 下只读地翻看，页首写这是哪天的对话，底部是「回到当前对话」的只读卡。礼物一律记进当前对话；当前对话是空的时「新对话」禁用；两个菜单的每一项都加上图标。见 `../spec.md` 的 Solution 和 Implementation Decisions。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

### 后端

- [ ] `GET /api/conversations?character_id=` 每条多带 `last_message`（同 `/latest` 的形状，跳过结束事件，空对话为 null）和 `ended`
- [ ] `add_gift` 不再接收对话 id：记进她最新的对话，那段已结束就新开一段；送礼接口的请求体去掉 `conversation_id`（带了也忽略）

### 前端

- [ ] `api.ts` 的 `Conversation` 类型跟上；`giveGift`、`giftsHref`、`giftsFor` 和礼物页去掉对话 id，旧链接里的 `conversation` 忽略
- [ ] LiveConversation：当前对话一条记录都没有时 `canStartNew` 为假
- [ ] `theme/icons.ts` 加 `NewConversationIcon`、`PastConversationsIcon`、`UnpinIcon`、`HideIcon`、`ShowIcon`；更多菜单（新对话、历史对话、换衣装）和对话列表长按菜单（置顶/取消置顶、隐藏/显示）每一项前面加图标
- [ ] 历史面板：宽屏 Dialog、窄屏 Drawer，都用她的颜色；每次打开都重新读，读的时候显示 Spinner；当前对话排第一行标「当前」，不列空的历史对话；每行显示日期（北京时间）、「当前」或「她结束了」的标记、最后一句（和对话列表复用同一段写法）；只有当前对话时写一句说明
- [ ] 历史对话视图：按 `?c` 读这段的记录，只读地画在消息区；页首在名字下面加日期；电话键禁用并带提示；输入栏换成只读卡；不碰 LiveConversation，通话条和通话层照常工作
- [ ] 回到当前对话：只读卡的按钮、窄屏返回键、浏览器返回都回到当前对话（上一条浏览历史就是当前对话时退回，否则换掉地址）；`c` 无效时换回不带 `c` 的地址
- [ ] 文案进 `zh.ts`；按 `frontend/AGENTS.md` 的 shadcn 纪律写；DESIGN.md 补上更多菜单、历史面板、历史对话的页首和只读卡、长按菜单图标，并改掉「从对话页跳来」那段

### 测试

- [ ] 后端：列表接口的两项新字段；送礼的落点（最新且没结束 / 最新已结束就新开，带不带对话 id 都一样）
- [ ] `liveConversation.test.ts`：当前对话是空的时 `canStartNew` 为假
- [ ] 面板行的纯逻辑如果抽成了函数，就给它写单测
- [ ] 本地构建版 Playwright（宽屏、手机）：菜单图标；面板；打开一段历史对话后的页首和只读卡、电话键禁用；返回键和浏览器返回；刷新后还在同一段；呼叫中打开历史对话后通话条还在；空的当前对话里「新对话」禁用
- [ ] 后端完整测试、前端类型检查和测试、`sh scripts/check-discipline.sh` 都通过

## Comments
