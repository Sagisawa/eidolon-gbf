# 01: 通话算不算限额，收进 CallOutcome

**What to build:** 新建 `backend/src/eidolon/call_outcome.py`，里面放 `CallOutcome` 类。它负责一次通话从 `take` 到 `give_back` 的全部判断，以及整条 `ended` 消息的组装。`call.py` 里散在五处的对应逻辑都改成向它报事件。背景和约定见 `../spec.md`。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

## 已定的设计（2026-09-28 grilling）

- **范围**：只处理通话。`app.py:298-306` 的文字回合不动。
- **不导入 Pipecat**：`call_outcome.py` 不导入 Pipecat 和 aiortc，它的测试也不加载它们。
- **由它 `take`**：在 `Calls.start` 里创建 `CallOutcome`，传入 `UsageLimiter`、`user_id` 和 `CallKeys`（或其中需要的 `exempt`）。构造时就 `take`，用户超限时抛出 `OverLimit`，行为和现在一样。
- **事件**：用方法表示，名字由实现者决定，含义如下：
  - 建立失败：对应 `Calls.start` 里 `answer is None or not started` 的分支；
  - 接通：对应 `on_client_connected`；
  - 记下一个回合：对应 `CallTurns` 收到 `TurnDone`；
  - 服务出错：参数是出错的那项自带密钥服务（`Service`），不是自带密钥时为 `None`；
  - 到上限：参数是 `EndReason`（`duration_limit` 或 `turn_limit`）和那句原因（`why`）；
  - 收尾：对应 `_serve` 的 `finally`。
- **返回值**：每个事件方法返回"要发给浏览器的 `ended` 消息 dict，或者 `None`"，由调用方发送。
  - 只告诉浏览器一次：第二次需要发消息的事件返回 `None`。这取代现在的 `_told_why`。
  - **没接通时出错，不返回消息**。现在的 `failed` 处理不管有没有接通都会发，统一以后这条消息不再发送；反正它送不到浏览器，浏览器靠连接断开得知通话结束。
- **规则**：都要和 CONTEXT.md「限额」「接通」一致，也和现在的行为一致：
  - 没接通（没收到"接通"就收尾）：还回去。
  - 接通后、记下任何回合之前服务出错：还回去，`reason = not_connected`；如果是自带密钥出错，`reason = own_key`。两种情况 `counts` 都是 false。
  - 记下至少一个回合后服务出错：不还，`reason = dropped` 或 `own_key`，`counts = not exempt`。
  - 到上限：不还，`counts = not exempt`。消息文本是 `f"{why}，先挂断啦。想接着聊可以重新拨打。"`，和 `CallTurns._end` 现在的一样。
  - 用户挂断、被封禁或删除时挂断、关服时挂断：接通了就计入，没接通就还回去。
  - `own_key` 的 message 仍然用 `OwnKeyFailed(service, "通话已结束").message`。
  - 收尾可以重复调用，`give_back` 最多发生一次（`Use.give_back` 本身也是幂等的）。
- **`ended()` 函数和 `EndReason`**：可以搬进 `call_outcome.py`，也可以留在原地，只要消息格式不变。
- **`CallTurns`**：
  - 把公开的 `recorded` 改成私有计数，只用来判断每次通话的回合上限（`call.py:780`）；
  - 每记下一个回合，就向 `CallOutcome` 报一次；
  - 在 `_end` 里改为向 `CallOutcome` 报"到上限"，再发出它返回的消息。
- **`_LiveCall`**：
  - 去掉 `_told_why` 和 `_service_failed`，也不再读 `CallTurns` 的计数；
  - `failed` 处理和 `_serve` 的 `except` 分支都改为报"服务出错"，拿到消息就用 `send_app_message` 发出去；
  - `finally` 里报"收尾"。
- **不得改变的**：`ended` 消息的格式和取值；`CallsUnavailable`、`OwnKeyFailed`、`OverLimit`、`CallFailed` 的抛出时机；`ice_servers` 的行为。

## 验收

- [ ] 新建 `backend/tests/test_call_outcome.py`，用真实的 `UsageLimiter`（SQLite，沿用 conftest 里现有的做法）或最小的 fake，覆盖整张结果矩阵：
  - 超限时构造就抛出 `OverLimit`；免限额（exempt）时照常创建；
  - 建立失败：还回去，不返回消息；
  - 没接通就收尾：还回去；
  - 没接通时服务出错：还回去，不返回消息；
  - 接通、记下 0 个回合、部署者的服务出错：`not_connected`，`counts=false`，还回去；
  - 接通、记下 0 个回合、自带密钥出错：`own_key`，`counts=false`，还回去；
  - 记下 1 个回合后服务出错：`dropped` 或 `own_key`，`counts` 取决于 exempt，不还；
  - 时长上限和回合上限：`counts` 取决于 exempt，不还，消息文本正确；
  - 接通后用户挂断：计入；
  - 连续两次需要发消息的事件：第二次返回 `None`；
  - 收尾调用两次：只还一次。
- [ ] `backend/tests/test_call.py` 按"替换而不是叠加"处理：
  - 保留能证明事件来源接对了的端到端测试：
    - `test_a_call_that_never_connects_does_not_count`；
    - `test_a_call_whose_voice_services_cannot_be_made_is_refused_and_does_not_count`；
    - `test_a_call_whose_voice_service_fails_before_any_turn_does_not_count`；
    - `test_a_call_hung_up_by_the_user_counts`。
  - 删掉 `test_a_call_that_took_a_turn_counts_even_if_a_service_fails_later` 和 `test_a_call_that_ends_on_its_own_limits_counts`，它们改由单元测试覆盖。如果删掉后某条接线（比如"记下回合"这个事件是否真的报出去了）没有任何测试覆盖，就保留对应的测试，并在 Comments 里说明原因。
- [ ] `backend/tests/test_call_turns.py` 保留 `test_a_call_on_the_users_own_keys_alone_says_it_does_not_count_when_it_ends`，并且照常通过。如果 `CallUnderTest` 需要给 `CallTurns` 注入 `CallOutcome`，就在 fixture 里接好。
- [ ] `call.py` 里不再出现 `_told_why`、`_service_failed`，也不再有公开的 `recorded`；`give_back` 只出现在 `call_outcome.py` 里。
- [ ] `Calls` 类的 docstring 和 `_tell_why_failed` 相关的注释，改为指向 `CallOutcome`。
- [ ] 在 `backend/` 下运行 `uv run pytest` 和 `uv run pyright`，全部通过。
- [ ] 按 TDD 做：先写 `test_call_outcome.py` 并让它失败，再实现。

## Comments
