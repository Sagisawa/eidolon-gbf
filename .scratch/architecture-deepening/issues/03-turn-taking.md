# 03: 补充、打断、开口的规则抽成纯状态机 TurnTaking

**What to build:** 新建 `backend/src/eidolon/turn_taking.py`，里面是 `TurnTaking` 类：一个纯同步的状态机，负责通话中「当前回合」的轮替规则。`CallTurns`（`backend/src/eidolon/call.py:581-847`）改成 adapter，只做三件事：把 Pipecat 帧和回复任务的进展翻译成事件交给 `TurnTaking`，执行它返回的指令，以及管理它原本就负责、但不属于轮替规则的部分。

**行为不变是硬约束。** 规则的依据是 `CONTEXT.md` 的「回合」「补充」「打断」三条，以及 `.scratch/call-turn-taking/spec.md` 的 Decisions。背景见 `../spec.md`（这是 2026-09-28 架构审查的候选 2，这张 ticket 的设计在同一天的 grilling 中定下）。

**Blocked by:** None (can start immediately)（01 已合入 main）

**Status:** ready-for-agent

## Problem

轮替规则现在散落在三处：

- 12 个标志位：`_spoken`、`_sent_to_tts`、`_complete`、`_following_on`、`_voicing`、`_bot_speaking`、`_muted`、`_ended` 等；
- 两个 `asyncio.Event`：`_stop`、`_heard`；
- 回复任务自身的状态：`_reply.done()` / `cancelled()`。

判断逻辑分布在 `process_frame` 的分支、`_take_up`、`_open_to_follow_ons`、`_reply_to` 和 `_on_its_way_to_tts` 里。call-turn-taking 的 01–05 五张票每张都在改这些标志位。测试只能通过 Pipecat 的 `run_test` 跑，还要用 `SleepFrame(0.05)` 把帧隔开，免得前后顺序乱掉。

## 已定的设计（2026-09-28 grilling）

- **范围（C）**：`TurnTaking` 只管当前回合的轮替规则：
  - 补充和打断的判定；
  - 开口：出声时看声音开始播放，只看文字时看第一句出现，已经记下的也算开口；
  - 完整的一段；
  - 迟到的声音不算下一条回复开口；上一条的声音还在播时，下一条回复送出第一批字就算开口；
  - 补充落空后按原文重新回复；
  - 只看文字；
  - 挂断以后说的话都不再处理。

  **留在 `CallTurns`（adapter）的**：
  - 输入队列和工作协程；
  - 时长计时和回合上限；
  - 向 `CallOutcome` 报事件；
  - 管道启停（`StartFrame` / `EndFrame` / `CancelFrame`）；
  - 调用 `engine.turn()`、创建和取消回复任务；
  - 推帧、发 RTVI 消息。
- **纯同步，不碰时钟和 asyncio（A）**：`turn_taking.py` 不导入 asyncio、Pipecat 和 engine。每个事件方法都是同步的，返回一串指令。
  - 补充的转写超时（`FOLLOW_ON_TIMEOUT`）由 adapter 计时：`TurnTaking` 发出"开始等补充"的指令，adapter 到点后报"补充落空"事件。
  - 常量 `FOLLOW_ON_TIMEOUT` 可以留在 `call.py`。
- **只看文字的开关由 `TurnTaking` 持有**：`mute` 消息作为事件报给它。每条回复开始时由它决定出不出声，并写进"回复"指令里（`voiced`）。打断之后这条回复不再出声，这条规则也在它里面。
- **"通话正在结束"是一个事件**：adapter 在 `_end` 时报给 `TurnTaking`，之后的输入一律不响应，也不打断角色最后那段声音。
- **事件**（名字由实现者决定），至少要能表达：
  - 用户开口（`InterruptionFrame`）；
  - 听到了一点（`InterimTranscriptionFrame`，用来延长补充的等待）；
  - 转写定稿（可能为空）；
  - 发出打好的字；
  - 只看文字的开关变化；
  - 一个回合开始（带文字）；
  - 回复送出第一批日语给 TTS；
  - 回复的第一句显示（不出声时）；
  - 一段完整（`SegmentComplete`）；
  - 回复已记下（`TurnDone`）；
  - 回复结束（记下、失败或被拒）；
  - 回复被放下（任务取消完成）；
  - 声音开始播放 / 停止播放（`BotStarted` / `BotStoppedSpeakingFrame`）；
  - 补充落空；
  - 通话正在结束。
- **指令**：每种一个冻结的 dataclass，事件方法返回 `list[...]`，adapter 用 `match` 逐条执行。名字由实现者决定，至少要能表达：
  - 放下当前回复（取消任务，不留痕迹）；
  - 停止当前回复（设置 stop，只记完整的段）；
  - 清掉已送去 TTS 但还没播出的声音（往下游推 `InterruptionFrame`）；
  - 用某段文字（重新）回复，带 `voiced`；
  - 开始等补充；
  - 把某句话排成下一个回合。
- **时序**：现在 `_take_up` 靠"先改状态、再 await 取消"避免竞态。改成同步状态机后，状态在事件方法里就已经改完，指令之后才执行，所以这一点由结构本身保证。adapter 执行指令时不能破坏这一点，例如不能在执行指令之前 await。
- **名字**：`TurnTaking`，文件 `turn_taking.py`。**CONTEXT.md 不改**。
- **不碰的**：`CallOutcome`、`_LiveCall`、`Calls`、`InterruptsFirst` / `FishTTS`、engine、前端、`mute` 消息在线上的格式。

## 验收

- [ ] **先证明行为不变**：`backend/tests/test_call_turns.py` 一行不改，在新实现上全部通过（25 个左右）。在 Comments 里记下这一步的结果。
- [ ] 新建 `backend/tests/test_turn_taking.py`：表格测试，每条都是"事件序列 → 指令序列（和必要的状态）"，不用 sleep，也不用事件循环。`.scratch/call-turn-taking/spec.md` 的 Decisions 里，属于本 module 范围的每一条至少对应一个测试，包括：
  - 开口前说的话是补充：放下回复，合并后重新回复，文字用换行连接；
  - 开口前打的字是补充，还要清掉 TTS 里没播完的部分；
  - 补充次数不设上限；
  - 已经开口但还没有完整一段时，仍然算补充；只看文字时，已显示第一句但还没有完整一段时，也仍然算补充；
  - 已开口并有完整一段后，说话算打断：停止回复，这句话排成下一个回合；
  - 打字的打断同样要清掉没播完的声音；
  - 回复记下后、声音还在播时打字，会让声音立刻停下，这句话排成新回合；
  - 连着快速发两条：第一条打断，第二条按补充处理；
  - 补充落空后按原文重新回复；
  - 被放下的回复的声音迟到开始，不算下一条回复开口；
  - 上一条声音还在播时，下一条回复送出第一批字就算开口；
  - 只看文字的开关只影响之后的回复；
  - 通话正在结束后，说话和打字都不响应，也不打断最后那段声音。
- [ ] 然后按"替换而不是叠加"拆分 `test_call_turns.py`：
  - 断言某条**规则**的测试，搬进 `test_turn_taking.py` 后删掉；
  - 断言**帧接线**的测试留下。例如：打字会往下游推 `InterruptionFrame`；只看文字时不往 TTS 送字；每条回复就是一次 TTS 回复；空输入被忽略；到上限就挂断；时长从接通算起；只用自带密钥的通话说不计入；失败和被拒的回合不计入、通话继续；补充落空后用真实计时按原文重新回复。

  在 Comments 里列一张表：每条原有测试是"留下"还是"移到哪条表格测试"。拿不准的就留下。
- [ ] `CallTurns` 里不再有这些轮替标志位：`_spoken`、`_sent_to_tts`、`_complete`、`_following_on`、`_voicing`、`_bot_speaking`、`_muted`、`_ended`、`_stop` / `_heard` 的判定用途。adapter 需要的 `asyncio.Event`（例如传给 `engine.turn` 的 stop、等补充的计时）可以保留，但它们何时 set，要由指令决定。
- [ ] `CallTurns` 的 docstring 改为指向 `TurnTaking`，规则的叙述搬到 `TurnTaking` 的 docstring。
- [ ] `backend/` 下 `uv run pytest` 和 `uv run pyright` 都通过。`test_characters.py::test_missing_character_sheet_is_reported_with_its_path` 在 Windows 上本来就失败（路径是反斜杠），不算在内。
- [ ] 按 TDD：先写 `test_turn_taking.py` 并看到它失败，再实现。

## Comments
