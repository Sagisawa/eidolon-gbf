# 02: 通话收尾时，由 `CallOutcome` 收掉开着的回合

**What to build:** `CallOutcome` 记住通话里开着的回合（`turn_begun` 返回的 `TurnOutcome`），通话收尾时先用回合判定把它收掉：通话因故障结束的记失败，否则记离开。运行记录写入时不再自己把没收尾的回合补成离开。

对管理者的变化：因语音服务故障结束的通话里，被截断的回合即使晚于通话收尾，也记为失败（现在会在取消卡住超过 pipeline 取消超时时被写成「离开」，已复现）。背景见 `../spec.md`。

**Blocked by:** 01（回合结果一处判定，文字回合和通话回合共用）

**Status:** ready-for-agent

## 已定的设计（2026-10-08 grilling，详见 spec）

- `CallOutcome.turn_begun(own_llm)` 返回这个回合的 `TurnOutcome`，并记住它直到它收尾。
- `CallOutcome` 新增一个只读的「通话是否因故障结束」（`ended_by` 为 failed）。`CallTurns` 回合结束时调 `turn.over(这个值)`。
- `CallOutcome.settle()` 先把还开着的回合按同样的值收掉，再收通话。回合之后自己的收尾不起作用（只收尾一次）。
- 删掉 `turn_cut_short()`。
- `ActivityLog._write` 删掉把没收尾的回合补成离开的那段，只写入；已有的「写入时必须有结果」的断言覆盖。
- 超时后 `CallTurns` 的后台任务仍在运行，不在本 ticket 内，见 `.scratch/call-teardown/issues/01-call-turns-worker-outlives-settle.md`。

## 验收

- [ ] `test_call_outcome.py` 补：收尾时开着的回合，通话因故障结束的记失败，被挂断、离开、封禁、到达上限等结束的记离开；已经收尾的回合不再改。
- [ ] 通话层回归测试：管道里 `CallTurns` 上游有一个卡住 `CancelFrame` 的处理器、取消超时设得很短，回复挂住，通话因语音服务故障结束；通话先于回合收尾，回合在运行记录里记为失败。
- [ ] 代码里没有 `turn_cut_short`；`ActivityLog` 写入时不再决定回合结果。
- [ ] 现有测试的断言不改就全部通过；如果哪条必须改，在 Comments 里写明原因。
- [ ] `backend/` 下 `pytest` 全部通过，`ruff` 和 `pyright` 没有新的报错。
- [ ] **人工验收（留给用户）**：本地起服务打一通电话，说一句后在角色回复时挂断，看板上这个回合记为离开、通话记为成功。
