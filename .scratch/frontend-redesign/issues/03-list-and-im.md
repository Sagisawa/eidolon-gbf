# 03: 消息列表和 IM 对话页

**What to build:** 首页改成微信式消息列表；进入一位角色就是 IM 对话页。电脑上左右双栏（左列表、右对话），手机上两级页面。打字对话的全部现有行为保留（流式回复、日语加字幕、失败时把原文放回输入框、新对话）。规则见 `../spec.md`「信息架构」，视觉见 `DESIGN.md`。

**Prototype:** 原型参见 `prototype/frontend-redesign` 分支的 `frontend/src/app/prototype/`（`git switch prototype/frontend-redesign` 后 `npm run dev` 打开 `/prototype`，右下角「原型控制台」可以跳到任意状态）。 对应文件：`ConversationList.tsx`、`Conversation.tsx`、`page.tsx`。

**Blocked by:** 01, 02

**Status:** ready-for-agent

- [ ] 路由：列表和对话共用一个双栏外壳。电脑宽度（≥ 768px）下，对话在右栏打开，列表保留；手机宽度下为两级页面，带返回
- [ ] 列表每行：头像（外圈用她的 `mark` 色）、名字、最新一次对话的最后一句（她的话显示字幕，自己的话前面加「你：」）、时间。选中行铺她的 `paper` 色，次要字用 `paperMuted`
  - 如果现有接口拿不到每位角色最后一句和时间，就在后端补一个（例如 `/api/characters` 或对话列表返回摘要），不要在前端逐个拉全部消息
- [ ] 对话页头部：实心底色和分隔线；头像、名字、通话按钮（她的 `button` 色）、`⋯` 菜单里放「新对话」。菜单等 Astryx 组件的默认英文标签都要换成中文
- [ ] 消息区铺横线纸（只在消息区）；气泡用 Astryx 默认的 `ChatMessageBubble` 形状，制作人的气泡用事务所深蓝，她的用她的 `paper` 色，日语大一级，字幕用 `paperMuted`。不加索引签、不自绘气泡尖角
- [ ] 输入栏用 Astryx 的 `ChatComposer`；消息从顶部往下排，新消息出现时滚到最新
- [ ] 继续用 `liveConversation` / `conversationLog` 的状态，不重写；现有测试保持通过
- [ ] 空对话、加载中、失败（含自带密钥出错、限额）的状态都有；失败提示遵守 `CONTEXT.md` 的语义，说明算不算限额
- [ ] 浅色和深色模式、手机和电脑各截图检查一遍，所有文字和图标都看得清

## Comments
