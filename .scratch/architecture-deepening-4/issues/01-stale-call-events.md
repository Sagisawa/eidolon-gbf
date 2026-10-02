# 01: 过期通话的事件一律挡住

**What to build:** 一次通话结束以后，不论是用户挂断、掉线、后端挂断，还是下一通已经开始，它迟到的任何消息都不再改动对话页：不进对话记录、不设错误、不改结束原因、不改正在听写的文字、不动立绘、不刷新对话列表。这道闸只设在 `LiveConversation`（`frontend/src/lib/liveConversation.ts`）一处。背景和取舍见 `../spec.md`。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

## 已定的设计（2026-10-02 grilling）

- **过期只有一个定义**：这次拨号已经不是当前这一通。
  - 任何一种结束都让它过期：用户挂断、掉线、后端说明原因后掉线、拨号失败、离开对话页。
  - 现在只有挂断和离开对话页会清掉当前的拨号。掉线和拨号失败走的那条结束路径也要清掉它，结束路径是 `ended()`。
- **一道闸**：拨号时交给通话的 handler 统一先判断「这次拨号还是当前这一通」，不是就直接返回。覆盖的 handler：
  - 通话事件；
  - 正在听写的文字；
  - 掉线；
  - 麦克风丢失。

  播放角色声音的 handler 原样直通 port，不在本轮范围。
- **闸后面删掉的判断**：
  - 通话事件处理里的「当前且通话在进行」：立绘那一路直接用事件推进。
  - 掉线、麦克风丢失里「这一通还是不是当前的通话」的比较。
- **保留的例外**：拨号中途掉线仍然不做事，由拨号失败说明原因。这一条留在掉线 handler 里，作为闸之后的第二个条件。
- **挂断那一刻迟到的「回复记下」也挡住**，包括不再刷新对话列表。这是有意接受的取舍，见 spec。
- **不动的**：
  - 通话 adapter（`lib/call.ts`）；
  - `conversationLog`、`standDirection` 两个 reducer；
  - 快照的形状；
  - 通话层的收起和展开、只看文字、麦克风；
  - 后端。
- **不改 `CONTEXT.md`，不写 ADR**。更新 `startCall`、通话事件处理和 `ended()` 附近的注释，写明过期的规则只在闸里。

## 验收

- [ ] **按 TDD**：先在 `liveConversation.test.ts` 写下面两条测试，看到它们失败，再改实现。
- [ ] **表驱动测试：过期通话的消息改不了任何东西**。两个维度交叉：
  - **这一通怎么结束**：用户挂断；掉线；后端先送「为什么挂断」、再掉线；下一通已经接通。
  - **迟到的是什么**：用户说的话、回复的增量、回复记下、出错、后端说明为什么挂断、正在听写的文字、麦克风丢失、一个只影响立绘的事件（如她开始出声）。

  断言：迟到的消息送达前后，`live.snapshot()` 深相等，`onListChanged` 没有被再次调用。「下一通已经接通」这一行的快照里，下一通进行中的回合要还在。
- [ ] **上一通迟到的结束原因不串到下一通**：下一通接通后，上一通才送来「后端说明为什么挂断」；下一通随后掉线，结束原因仍是这一通自己的「掉线」。它和现有的 `does not give a new call's drop the reason an earlier call was ended for` 互补：那条测两通先后发生，这条测上一通的消息在下一通里迟到。
- [ ] **替换，不叠加**：
  - 删掉 `is not moved on by the last call's events once the next one is under way`（her emotions 组）。
  - `is cleared when the call %s, the next call starting calm`（the stand 组）只删掉最后「the old call's, too late」那一句事件和紧跟的断言；其余保留。
- [ ] **现有测试一律原样通过**，尤其是：
  - `leaves a call that drops while dialing to fail to connect`；
  - `does not give a new call's drop the reason an earlier call was ended for`；
  - `says a call that drops with no word from the backend counted, unless it was exempt`；
  - `opens up again when the call ends while it is collapsed`；
  - 麦克风丢失和切换的几条。
- [ ] `LiveConversation` 里判断「是不是当前这一通」的写法只剩闸那一处。拨号中途掉线的例外除外，它判断的是「接通了没有」。
- [ ] `frontend/` 下 `npm test` 和 `npm run typecheck` 都通过。
- [ ] **人工验收（留给用户）**：打几通真实电话，确认日常流程和以前一样。用户验过之后再标 `resolved`。
  - 正常挂断，回到对话页，对话记录完整；
  - 说完一句话的同时挂断，不留下一直转圈的「正在回复」；
  - 挂断后马上重拨，新通话里的回合正常；
  - 收起通话层时挂断；
  - 后端到点自动挂断（可把时长上限临时调短），结束页显示的原因正确。

## Comments
