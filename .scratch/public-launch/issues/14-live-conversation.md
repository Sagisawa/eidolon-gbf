# 14: 对话页打开着的对话搬出 React：通话的生命周期和回合的结局

**What to build:** 新建不依赖 React 的 `frontend/src/lib/liveConversation.ts`（`class LiveConversation`），拥有一个对话正在进行的部分：对话记录、文字回合的结局、通话的阶段与结束、草稿、静音。每个对话一个实例，用 `(conversationId, messages)` 创建；注入 `startCall`、`sendTurn`、偏好 port 和角色音轨的回调。页面用 `useSyncExternalStore` 订阅快照、渲染、转发点击。对外行为不变，两处改动：接通中不能发送文字（修掉与通话交错写记录）；为 f584f25（接通中离开页面要挂断）补上测试。

**Blocked by:** —

**Status:** ready-for-agent

- [ ] `LiveConversation` 提供 `snapshot` / `subscribe` / `dispose`，以及 `setDraft`、`submit`、`toggleCall`、`toggleMute`；快照含 `entries`、`phase`（`idle` / `connecting` / `active`）、`hearing`、`busy`、`draft`、`muted`、`failure`
- [ ] 对话记录由 module 拥有，内部沿用 `conversationLog` reducer；`conversationLog.ts` 与它的测试不改
- [ ] 注入的 port：`startCall`、`sendTurn`（签名不改）；偏好 `load` / `save`（真实实现是 `callPreferences`）；角色音轨回调，由页面设置 `<audio>.srcObject`
- [ ] 任何时刻都能 `dispose`：接通中则 `startCall` 返回后立即挂断、不进入 `active`；此时 `startCall` 失败不显示错误；通话中则挂断；文字回合进行中不中止，只是不再发布快照
- [ ] 用户挂断与掉线走同一条结束路径：回到 `idle`、清空 `hearing`、撤回没说完的回复；掉线显示后端 `ended` 的理由，没有就显示「通话已断开」；用户挂断不显示错误
- [ ] 接通中不能 `submit`；文字回合进行中不能开始通话；接通中仍不能取消（UI 不变）
- [ ] 回合失败（`error` 事件、流结束仍没有 `done` →「回复中断了，请再试一次」、抛出异常）都撤回记录、把草稿还原
- [ ] 通话中 `submit` 走 `sendText`，不开文字回合，草稿清空
- [ ] 静音由 module 保存偏好；通话中切换时通知通话；开始通话时带上当前偏好
- [ ] 页面：加载（角色名、最近或新建的对话、消息）与「新对话」留在页面；「新对话」dispose 旧实例、创建新实例；`pageError` 只来自加载与新建对话失败，显示 `pageError ?? snapshot.failure`
- [ ] 新测试 `src/lib/liveConversation.test.ts`（见「测试」），全部写在 `LiveConversation` 的 interface 上
- [ ] 现有测试不改，全部通过；`npm run typecheck` 通过

## 背景（2026-09-27，架构体检候选 3）

1. 通话状态散在 `callState`、`call`、`callEnding`、`disposed`、`hearing`、`muted` 6 处 state / ref；「结束通话」的四步（清 ref、回 `idle`、清 `hearing`、`interrupted`）在 `toggleCall` 的挂断和 `onDropped` 两处各写一遍。
2. 回合结局规则（流没给 `done` 就算「回复中断了」、失败还原输入）只在组件里，零测试。
3. 接通中离开页面会漏挂断：卸载时 `call.current` 还是 `null`。f584f25 已加 `disposed` 标记原地修好，当时约定测试留给本 ticket。
4. 后端不阻止同一对话里文字回合与通话并行；页面只在 `busy` 时禁用通话按钮，接通中仍能发文字。那个文字回合与随后接通的通话写进同一份记录，通话的 `user` 事件会把文字回合里还没被后端接收的回合当成自己的。
5. vitest 跑在 node 环境、没有 jsdom；module 不依赖 React，就能直接测。

## 测试

用假 `startCall`（可手动 resolve / reject，可触发 `onEvent`、`onHearing`、`onDropped`）、脚本化的 `sendTurn`、内存里的偏好：

1. 接通中 `dispose`：`startCall` 返回后立即 `hangUp`，不进入 `active`，也不再发布快照（f584f25）
2. 接通中 `dispose` 后 `startCall` 失败：不显示错误
3. 通话中 `dispose` → `hangUp`
4. 用户挂断与掉线：回到 `idle`、清空 `hearing`、撤回没说完的回复；掉线显示后端理由，没有理由显示「通话已断开」；用户挂断不显示错误
5. 接通失败：回到 `idle`，显示后端给的理由
6. 通话中 `submit` 走 `sendText`，不开文字回合，草稿清空
7. 接通中 `submit` 被拒绝；文字回合进行中不能开始通话
8. 文字回合成功时记下；`error` / 没有 `done` / 抛出异常时撤回记录并还原草稿
9. 文字回合进行中 `dispose`：不中止回合，但不再发布快照
10. 静音：切换时保存偏好；通话中通知通话；开始通话时带上当前偏好

页面本身只做渲染和转发，不单独测，靠 `typecheck`。

## Comments

### 决定（2026-09-27，grilling）

- **范围**：通话的生命周期和文字回合的结局一起搬。两者互相排斥、共用一份记录，这些规则只有在同一个 module 里才测得到。
- **接通中离开照常计入限额**（领域决定）：等连上再挂断，不给 `startCall` 加 abort。离开对话页就是用户挂断，与「用户自己中途离开的照常计入」一致。`CONTEXT.md` 的「通话」已改。
- **接通中不能取消**：保持 UI 不变。以后要做，只需加一个入口，走 `dispose` 的同一条路径。
- **接通中不能发文字**：与「文字回合进行中不能开始通话」对称，同一时间只有一个回合来源。
- **文字回合进行中离开页面不中止**（领域决定）：站内跳转不会断开 `fetch`，回复照常完成并记下；通话必须挂断，是因为麦克风和 WebRTC 还占着。`CONTEXT.md` 的「回合」已澄清「离开」指与回合的连接断开。
- **记录、草稿、静音都归 module**：「撤回」「还原草稿」「通话中切换静音」都是规则，要能在 interface 上断言。
- **加载与「新对话」留在页面**：module 只管对话正在进行的部分；每个对话一个实例。
- **错误**：module 的 `failure` 来自接通失败、掉线、通话中的 `error` 事件、文字回合失败，在它下一次操作（`submit`、`toggleCall`）开始时清除；页面的 `pageError` 只来自加载与新建对话失败。
- **命名**：`liveConversation.ts` / `LiveConversation`，意思是「对话页上打开着的这个对话」。`api.ts` 已有 `Conversation`（后端数据），「会话」在代码里指登录会话。不进 `CONTEXT.md`。
- **边界情况（实现时处理）**：`startCall` 还在接通时触发的 `onDropped` 忽略，由 `startCall` 的失败来处理。
- **不在范围内**：`/api/offer` 走 `redirectFor`、`api.ts` 的 `overLimit` / `describe` / SSE 分帧测试，见 ticket 15。
- 不写 ADR（容易撤回）。一个提交，含 `CONTEXT.md` 改动。
