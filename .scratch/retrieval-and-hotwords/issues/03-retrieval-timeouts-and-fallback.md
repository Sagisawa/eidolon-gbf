# 03: 检索的超时、重试和退路

**What to build:** 向量化或重排服务卡住时，角色最多停顿几秒就照常回答，而不是半分钟不出声；重排出故障时，角色仍凭向量最接近的剧情和资料回答。回合里的查询向量化和重排超时缩到几秒，超时、连接失败、429 和 5xx 时立刻重试一次；重排仍然失败时按下面的退路处理。剧情库导入这类批量向量化不受影响。背景见 `../spec.md`「超时、重试和退路（票 03）」一节。

**Blocked by:** 02（两张票改的是检索流程的同一段代码）

**Status:** ready-for-agent

## 已定的设计（详见 spec）

- 超时初定 3 秒（线上 99% 分位：向量化约 0.8 s，重排约 0.8 s），写成常量并注明依据。批量向量化（剧情库导入、`eidolon reembed`、作品资料同步）保持长超时。
- 超时、连接失败、429、5xx 重试一次；其他 4xx 和返回无法解析时不重试。重试也记进看板。
- 重排重试后仍然失败：
  - 剧情和资料：按向量相似度取最近的 3 条，不套重排分数线；
  - 记忆：不带；
  - 判断模型触发的回忆和回顾剧情工具：取向量最近的一段剧情（有的话再加最近的演出或唱片条目），照常附上剧情目录。
- 向量化重试后仍然失败：照旧什么都不带。
- 判断模型自己的超时不改。

## 验收

- [x] 服务客户端测试：查询向量化和重排超时后重试一次，第二次成功就正常返回；429 和 5xx 同样重试；其他 4xx 不重试；两次都失败才报错。
- [x] 服务客户端测试：批量向量化仍用长超时。
- [x] 文字回合测试：重排服务故障时，系统提示词里带的是向量最近的 3 条剧情和资料，没有记忆，回合照常完成。（假重排服务加一个故障开关。）
- [x] 文字回合测试：重排服务故障时，判断模型触发的回忆和回顾剧情工具都返回向量最近的一段剧情和它在剧情目录里的位置。
- [x] 文字回合测试：向量化服务故障时，回合照常完成、不带资料和记忆（已有的测试继续通过）。
- [x] `backend/` 下 `pytest` 全部通过，`ruff` 和 `pyright` 没有新的报错。

## Comments

**实现（2026-10-14，agent）**

- 新模块 `retry.py`：`TURN_TIMEOUT = 3.0`（注明了线上 99% 分位的依据）；`ServiceError` 带 `transient`，`EmbeddingError`、`RerankError` 都改成它的子类；`retry_once` 在 transient 错误时立刻再做一次。超时、连不上、429、5xx 算 transient；其他 4xx、返回无法解析不算。
- 超时和重试放在服务客户端里：SiliconFlow 和 Gemini 的 `embed_query`、SiliconFlow 的 `rerank` 每次请求用 `asyncio.timeout` 限 3 秒（整次请求的上限，不是 httpx 分阶段的超时），失败就重试一次。`embed_documents` 不变：没有新超时、不重试，Gemini 文档照旧等限流。构造参数 `query_timeout`（向量化）和 `timeout`（重排）让测试能调短。Gemini 查询遇到 429 以前直接报错，现在也立刻重试一次（仍然不等 `retryDelay`）。
- 重试计入看板：客户端重试前经 contextvar（`retry.telling_retries`，和 `billing` 同一种做法）告诉 `activity.timed`，失败的那次单独记一条服务调用，带上它的错误类型。
- 退路：`Reference` 加了 `similarity`（和查询向量的余弦相似度）；`EmbeddedTexts.search` 改成返回位置和相似度。重排失败时：资料按相似度取最近的 `FALLBACK_REFERENCES = 3` 条，不套分数线；记忆本来重排失败就不带，没改；判断模型触发的回忆和回顾剧情工具取相似度最高的那段剧情，再加最近的一条演出或唱片（回顾剧情工具没有作品资料），照常附剧情目录。
- 影响范围：`eidolon eval rerank` 和写记忆时给背景模型看的查询也走同一个客户端，所以也是 3 秒加重试一次。
- 测试：`test_embedding.py` 加了脚本化的假服务（`scripted`、`HANG`），测查询超时、连不上、429、5xx 都重试一次，两次都失败才报错，其他 4xx 和无法解析不重试，文档不受短超时限制；`test_gemini_embedding.py`、`test_retrieval_services.py` 对 Gemini 查询和重排测了同样的情况；`test_activity_records.py` 测重排 503 一次后看板记两次调用、一次 `server_error`。`FakeReranker` 加了 `down`；`test_retrieval.py`（最近 3 条、没有记忆）、`test_recall_story.py`（判断模型触发的回忆和回顾剧情工具都只回一段最近的剧情，附剧情目录）、`test_world_retrieval.py`（回忆加上最近的演出）。
- 完整 `pytest` 1375 条全部通过，`ruff check`、`pyright` 无报错。
