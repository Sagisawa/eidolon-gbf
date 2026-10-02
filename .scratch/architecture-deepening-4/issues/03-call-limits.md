# 03: 通话的上限与收尾归 CallOutcome

**What to build:** 通话的时长上限、回合数上限、回合计数和完整的 `ended` 文案都归 `CallOutcome`（`backend/src/eidolon/call_outcome.py`）。`CallTurns`（`backend/src/eidolon/call.py`）只报告接通、记下一个回合、时间到了，在回合之间问一句到上限了没有，到了就照它给的消息挂断。浏览器收到的消息逐字不变。背景和取舍见 `../spec-03-call-limits.md`。

**Blocked by:** None (can start immediately)。只改 `backend/`，可以和 01 并行，各开一个 worktree。

**Status:** ready-for-agent

## 已定的设计（2026-10-02 grilling）

- **`CallOutcome` 构造时收下 `CallLimits`**（`Calls.start` 交给它），回合数只在这里记一份。
- **`CallTurns` 不再收 `limits`**：删掉 `_recorded`、`_time_up`、回合上限的比较和文案。
- **`CallOutcome` 的 interface**：
  - `connected()`、`turn_recorded()`、`time_up()`（新）：只报告，返回 None。
  - `time_limit: timedelta | None`：给 `CallTurns` 的计时用。
  - `limit_reached() -> LimitReached | None`：不带参数。没到上限返回 None；到了返回 `LimitReached(why, ended)`，`why` 给 `EndWorkerFrame` 当 reason，`ended` 是完整的浏览器消息，已经告知过时为 None。
  - 时间到了和回合满了同时成立，先报时间。
- **计时**：`CallTurns` 接通后照旧 `asyncio.sleep(outcome.time_limit)`，醒来调 `outcome.time_up()`，再叫醒处理回合的循环。不用 Clock 比较时间（单调时钟和墙上时钟可能差一点，判成「还没到」通话就挂不断），不注入 sleep。
- **`CallTurns` 问的时机**：一个回合完全结束之后，以及被计时任务叫醒时；拿到 `LimitReached` 就照现在 `_end` 的顺序收尾（`TurnTaking` 进入结束 → 发 `ended`（有的话）→ 推 `EndWorkerFrame`）。
- **不动的**：`TurnTaking.ending` 的外部读取、`Calls.ice_servers` 的 `maxCallSeconds`、`ended` 消息的形状和文案、`CallOutcome` 其余的规矩、前端。
- **不改 `CONTEXT.md`，不写 ADR**。更新 `CallOutcome` 和 `CallTurns` 的 docstring：上限和文案在 `CallOutcome`。

## 验收

- [ ] **按 TDD**：先在 `test_call_outcome.py` 写下面的纯测试，看到它们失败，再改实现。`limiter` fixture 的 `call(...)` 要能带上限。
- [ ] **新增纯测试**：
  - 回合数到上限才返回 `LimitReached`，没到返回 None；
  - `time_up()` 之后返回带「这次通话已经满 N 分钟了，先挂断啦。想接着聊可以重新拨打。」的完整消息；
  - 两个上限同时成立，先报时间；
  - 没有上限，永远返回 None；
  - 浏览器已被告知过，`ended` 为 None，`why` 照给。
- [ ] **改走新的 interface，不叠加**：`test_a_call_that_reaches_its_limits_is_kept`、`test_a_call_that_reaches_its_time_before_any_turn_is_kept`、`test_the_browser_is_told_why_only_once` 改成带上限构造、报告事件，文案断言写全；和新测试重合的合成一条。
- [ ] **`test_call_turns.py`**：
  - 删掉 `test_a_call_on_the_users_own_keys_alone_says_it_does_not_count_when_it_ends`；
  - 保留 `test_call_hangs_up_after_its_last_allowed_turn`、`test_call_hangs_up_when_time_is_up_once_the_reply_in_progress_is_done`、`test_a_calls_time_is_counted_from_when_it_connects`、`test_turns_that_fail_or_are_rejected_do_not_count_and_the_call_goes_on`，只断言 `reason` 和消息顺序，去掉「2 轮」「分钟」这类文案断言。
- [ ] `CallTurns` 里不再有回合计数、上限的比较和任何 `ended` 文案；`CallOutcome` 是唯一数回合的地方。
- [ ] `backend/` 下 `pytest` 全部通过。
- [ ] **人工验收（留给用户）**：把时长上限和每通回合数临时调小，打真实电话；用户验过之后再标 `resolved`。
  - 说满回合数：最后那句念完才挂断，结束页文案和以前逐字一样，限额照常计数；
  - 到了时长：正在说的回复说完才挂断，结束页文案和以前逐字一样；
  - 只用自带密钥时，结束页说明这一通不算限额。

## Comments
