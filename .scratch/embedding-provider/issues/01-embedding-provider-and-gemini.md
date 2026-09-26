# 01: 向量化服务二选一，接入 Gemini Embedding 2

**What to build:** 部署时用 `EMBEDDING_PROVIDER` 在硅基流动 Qwen3-Embedding 与 Google `gemini-embedding-2` 之间二选一。选 `gemini` 时，剧情库导入、角色资料、记忆和对话中的检索都用 Gemini 向量化；重排仍用硅基流动。已有的硅基流动部署不改配置、不重新向量化，行为完全不变。

**Blocked by:** None (can start immediately)

**Status:** ready-for-human（代码已完成；只剩用真实 key 的小规模验证）

- [x] 配置：`SiliconFlowSettings` 拆成「向量化」与「重排」两部分。新增 `EMBEDDING_PROVIDER`（`siliconflow` | `gemini`，默认 `siliconflow`，其他值启动报错）、`GEMINI_API_KEY`、`GEMINI_BASE_URL`（可选，默认 `https://generativelanguage.googleapis.com/v1beta`）、`EMBEDDING_DIMENSIONS`（只对 gemini 生效，默认 1536，范围 128–3072）；`EMBEDDING_MODEL` 仍可覆盖所选服务的默认模型（gemini 默认 `gemini-embedding-2`）
- [x] 检索与记忆的开启条件改为：所选服务的向量化 key + `SILICONFLOW_API_KEY`（重排）+ Jev；缺任何一项时照旧只凭人设回复
- [x] `GeminiEmbedder`：调用 `models/{model}:batchEmbedContents`，header `x-goog-api-key`；每条文本单独一个 `requests[]` 项（不要把多条放进同一个 `parts`，会被合并成一个向量）；带 `output_dimensionality`；每批条数用常量（先取 100，官方未写上限）；返回数量不符、无法解析、HTTP 错误都抛 `EmbeddingError`，与 `SiliconFlowEmbedder` 一致
- [x] 地区不支持时（Google 返回 location not supported 一类错误）`EmbeddingError` 的消息里提示「Gemini API 不对中国大陆、香港、澳门开放」
- [x] 前缀：查询 `task: search result | query: {text}`；文档 `title: {title} | text: {text}`，无标题用 `title: none`。`Embedder.embed_documents` 需要能拿到每条文档的标题：剧情段落传「出处 + 话标题」，角色资料传该条的 Markdown 标题，记忆传 `None`。`SiliconFlowEmbedder` 忽略标题，行为不变
- [x] 模型标识：`GeminiEmbedder.model` 为 `{model}@{dimensions}`（如 `gemini-embedding-2@1536`）；`SiliconFlowEmbedder.model` 保持裸模型名
- [x] 测试：用 `httpx.MockTransport` 覆盖请求形状（每条一个 `requests[]` 项、前缀、维度、分批）、结果顺序、各类错误；配置解析覆盖默认值、非法 provider、非法维度、缺 key 时检索关闭
- [ ] 用真实 key 做一次小规模验证（几条剧情段落 + 一次查询），确认返回维度和分批行为，在 Comments 记录；如有条件，顺便确认一次 `batchEmbedContents` 在限流里算几次请求

## Comments

2026-09-27 实现完成，等真实 key 验证：

- 配置拆成 `EmbeddingSettings`（`EMBEDDING_PROVIDER` / `SILICONFLOW_API_KEY` 或 `GEMINI_API_KEY` / `EMBEDDING_MODEL` / `GEMINI_BASE_URL` / `EMBEDDING_DIMENSIONS`）与 `RerankSettings`（`SILICONFLOW_API_KEY` / `RERANK_MODEL` / 两个阈值变量）。所选服务的 key 没设时向量化关闭；非法的 provider 或维度在读配置时就报错。导入、同步命令用 `EmbeddingSettings.required_from_env()`，缺 key 时报出所缺的变量名。
- `Embedder.embed_documents` 改为接收 `Document(text, title)`。标题：剧情段落是 `corpus.passage_title`（「出处「话标题」」，与段落开头的那行相同），角色资料是标题路径（角色资料改为 `Fact(title, text)`，`text` 仍以标题开头，库里存的文本不变），记忆是 `None`。
- `GeminiEmbedder` 请求体用 `output_dimensionality`（snake_case，Google 的 REST 接口两种写法都接受）。地区错误按响应里的 `location is not supported` 识别。
- 本机没有 Gemini key，真实验证（返回维度、分批、`batchEmbedContents` 在限流里算几次请求）还没做。

