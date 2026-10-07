# 01: 测试经 `FakeServiceClients` 走生产路径

**What to build:** 部署者的扮演、记忆、判断模型一律由 `LiveConfig` 经 `ServiceClients` 造出，测试改为配置 `FakeServiceClients`。`build()` 去掉 `chat_llm`、`background_llm`、`retrieval_judge`、`emotion_judge` 四个参数，`LiveConfig` 去掉只为测试留的分支。经 `build()` 的测试从此经过 `LiveRetrievalJudge` → `ModelRetrievalJudge`、`LiveConfig.lease` 里的情绪判断和阈值，和生产走同一条路。

这是保持行为不变的重构：对用户、管理者都没有变化。背景见 `../spec.md`。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

## 已定的设计（2026-10-07 grilling，详见 spec）

- **`build()`** 去掉四个参数。`.env` 的记忆模型也经 `clients.memory_llm` 造，不再在 `build` 里 `open_llm`。
- **`LiveConfig`**：
  - 去掉 `chat_llm` / `background_llm` 构造参数和 `live_judge` / `live_emotions`：配了判断模型，就一律由它造判断模型、由它判断通话中的情绪。
  - `Swappable` 的 `owned` 参数删掉：里面的客户端都归它关。
- **删掉** `Backend.emotions`、`Calls` 的 `emotions` 参数、`call.py` 里 `keys.emotions or self._emotions` 的回退。`metered_retrieval` 不再处理判断模型，嵌入和重排照旧。
- **假件（`tests/fakes.py`）**：
  - `FakeServiceClients` 能接收测试指定的扮演、记忆、判断模型假件；按 key 记录每次请求。
  - 判断模型的假件在 `JudgeModel` 这一层按剧本作答：给定 `Need`，或者按段排好的情绪答案（含失败、`HANG`、一直失败），答出能让 `ModelRetrievalJudge` / `ModelEmotionJudge` 按阈值得出同样结论的概率（1.0 / 0.0，或剧本里给定的）。记下每次被问到的内容。
- **`make_client` 保留简写**：`retrieval_judge=`、`emotion_judge=`、`background_llm=` 照旧可传，在 `make_client` 内部接到 `FakeServiceClients` 上；传了判断模型时，给 settings 配一个 jev 的判断模型（jev 的阈值和兜底值相同，判定结果不变）。`Turns.take`、`CallUnderTest` 同理。上百处调用处不动。
- **只改写法、不改验证内容的断言**：
  - 约 8 处断言 `FakeJudge.asked` / `.segments` 的，改为断言判断模型被问到的内容（哪个角色、哪句话、哪一段）；
  - `test_call_turns.py:250, 309` 逐条比较消息列表的，滤掉 emotion 消息；
  - `test_live_config_services.py` 里区分 `.env` 的记忆模型和后台换上的记忆模型的 3 处（约 109、133、153 行），改为按 key 断言；
  - `CallUnderTest` 不再读 `backend.emotions`，改用 `admission.keys.emotions`。
- 直接测某个 module 本身的单元测试（例如直接构造 `Retrieval`、`EmotionJudging` 的）可以继续用协议层的假件；只有经 `build()` 的测试必须走 `FakeServiceClients`。

## 验收

- [ ] `build()` 的签名里没有 `chat_llm`、`background_llm`、`retrieval_judge`、`emotion_judge`；`LiveConfig` 里没有 `owned`、`live_judge`、`live_emotions`；`Backend` 没有 `emotions`；`Calls` 没有 `emotions` 参数。
- [ ] `test_assembly.py` 补一条：配了判断模型时，检索判断和通话的情绪判断都由 `FakeServiceClients` 造的判断模型作答，用的是生效的阈值（后台改了阈值覆盖后，结论跟着变）。
- [ ] 除上面列出的断言写法，现有测试的断言不改就全部通过；如果哪条必须改，在 Comments 里写明原因。
- [ ] `backend/` 下 `pytest` 全部通过，`ruff` 和 `pyright` 没有新的报错。
- [ ] **人工验收（留给用户）**：本地用真的 `.env` 起服务（`ProviderClients`），确认：
  - 文字回合正常回复，记忆照常写下；
  - 配了判断模型时，检索照常（问一个需要查剧情的问题），通话里立绘照常换表情；
  - 后台换扮演模型、换判断模型，新回合立刻用上，看板的服务调用照常记录。

## Comments
