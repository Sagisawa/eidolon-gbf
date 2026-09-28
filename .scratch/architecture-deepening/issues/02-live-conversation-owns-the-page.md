# 02: 对话页的状态都交给 LiveConversation

**What to build:** 把 `ConversationView` 里带规则的状态和 effect 搬进 `frontend/src/lib/liveConversation.ts`，React 这边只负责渲染快照、把操作转给它。搬的内容包括：打开对话、开新对话、通话层的收起、选麦克风、页面错误、列表刷新的时机和消息时间。背景和约定见 `../spec.md`。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

## 已定的设计（2026-09-28 grilling）

- **生命周期：每位角色一个**。改成 `new LiveConversation(characterId, ports)`，由它自己负责打开：有对话就打开最新的一个（`listConversations`），没有就新建（`createConversation`），再用 `listMessages` 载入消息。
  - 快照里要能看出"打开中"。打开失败时（包括未登录，`failure.signedOut`），失败原因放在快照的 `failure` 里。页面现有的"打不开"空状态和重新登录按钮照旧，只是改为从快照取数据。
  - `startNewConversation()` 也移到它身上：新建对话，清空日志，重置 `callFrom` 等按对话计的状态。按钮禁用的条件保持现状（回合进行中、通话中、未登录时禁用）。
  - `dispose()` 的语义不变：离开页面就挂断通话，拨号中的也挂断。正在打开时 dispose，打开的结果被丢弃，不再发出 `onListChanged` 之外的任何更新。至于这种情况下"已经新建了对话"要不要仍然调用 `onListChanged`，由实现者决定并在 Comments 里写明。
  - 页面 `ConversationView` 以 `character.id` 作 key，所以一位角色对应一个实例（`app/(conversations)/conversation/[characterId]/page.tsx:24`）。
- **Ports 新增**：
  - `listConversations`、`createConversation`、`listMessages`，直接对应 `@/lib/api` 里的同名函数；
  - `onListChanged(): void`，在两种情况下调用：一个回合**记下了**（收到 `done`，文字回合和通话里的回合都算），以及新建了一个对话（包括打开时因为没有对话而新建）。
- **快照新增或调整**：
  - `collapsed`：通话层收起了。规则：`call.phase` 变成 `ended` 时自动展开；拨号时展开。另外提供 `collapse()` 和 `expand()` 两个方法。
  - `pickingMic`：麦克风列表开着。规则：通话一旦不在 `connected`，就自动关上。另外提供打开和关闭的方法。
  - `failure`：页面唯一的错误。`pageError` 删掉，打开失败、开新对话失败都写进它。拨号时清掉它（现在的 `dial()` 就是这样做的）。
- **消息时间**：`Entry` 加一个 `at: string` 字段（ISO 格式）。
  - `loaded` 的消息用它们的 `created_at`；
  - `done` 换成已记下的回复时，用 `message.created_at`；
  - 用户那条在 `submitted` 或 `user` 时，由 `LiveConversation` 用 `ports.now` 盖上时间。作法是在这两个 `LogAction` 上加一个 `at` 参数，`conversationLog` 保持纯函数；
  - 进行中的回复，时间可以先用开始的时刻，也可以留空，由实现者决定。
  - 删掉 `ConversationView` 里的 `useEntryTimes`，改为直接用 `entry.at`。
- **留在 React 的**：
  - `useShownCall`：只是为了让收起动画在挂断后还有东西可收，属于渲染细节。
  - 目录的 `setCall` 镜像 effect（`ConversationView.tsx:118-122`）保持原样。
  - `isFullScreen`、`isReducedMotion`、`<audio>` 的 ref，以及通过 `onCharacterAudio` 接到 `<audio>` 的那部分接线。
- **删掉的**：数 settled 条目刷新列表的那段代码（`ConversationView.tsx:133-140`，包括 `seen` ref）、两个 phase effect（`:124-131`）、打开对话的 effect（`:84-101`）、`startNewConversation` 里的 React 状态操作、`pageError`。
- **不碰的**：`failure.ts`、`callEnd.ts`、`call.ts`、`microphone.ts`、`CallLayer.tsx` 的接口（props 名可以跟着快照调整，但不要改它的行为）、限额相关的文案，以及后端。

## 验收

- [ ] 在 `frontend/src/lib/liveConversation.test.ts` 里，给 fake Ports 补上三个 list/create 函数和 `onListChanged` 计数器，新增测试：
  - 有对话时打开最新的一个，消息载入，**不**调用 `onListChanged`；
  - 没有对话时新建一个，调用 `onListChanged` 一次；
  - 打开失败（普通错误，以及 `signedOut`）时，失败原因出现在快照的 `failure` 里；
  - 开新对话：日志清空，调用 `onListChanged` 一次；
  - 一个成功的文字回合只调用 `onListChanged` 一次，而且是在 `done` 之后，提交时不调用；
  - 通话里记下一个回合时调用一次；
  - 失败的回合、被撤回的回合不调用；
  - 用固定时钟测时间：新回复的 `at` 等于 `done.message.created_at`，用户那条的 `at` 等于提交时的 `now`；
  - 收起时通话因故结束，会自动展开；
  - 拨号会展开，并清掉之前的 `failure`；
  - 麦克风列表开着时通话断开或结束，列表会自动关上；
  - 打开过程中 dispose，之后不再更新快照。
- [ ] 现有的 `liveConversation.test.ts` 按新的构造方式调整，全部照常通过。
- [ ] `frontend/src/lib/conversationLog.test.ts`：给 `at` 补断言，覆盖 `loaded`、`submitted`、`user` 和 `done` 四种情况。
- [ ] `ConversationView.tsx` 里不再出现 `pageError`、`useEntryTimes`、`seen`、`setCollapsed` 和 `setPickingMic` 这几个 React state，也不再有处理通话 phase 的 effect。
- [ ] 手动验证（用 `run` skill 或 Playwright 均可）：
  - 进入一位角色的对话，发一句话，列表那一行只在回复记下后更新一次（看网络请求 `latest` 的次数）；
  - 气泡下的时间正确；
  - 打电话、收起、挂断、再拨号，行为和改动前一致。
- [ ] 在 `frontend/` 下运行 `npm test` 和 `npm run typecheck`，全部通过。有 lint 脚本的话也跑一遍。
- [ ] 按 TDD 做：先写失败的测试，再实现。

## Comments
