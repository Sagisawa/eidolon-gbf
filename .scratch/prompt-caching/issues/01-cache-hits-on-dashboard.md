# 01: 运行记录记下缓存命中，看板显示命中率、按缓存价估算花费

**What to build:** 管理者在看板上能看到每个 LLM 的缓存命中率，花费里命中缓存的那部分输入按缓存命中价估算；价格页能看到、能改每个模型的缓存命中价，目录里有的自动带出。背景见 `../spec.md`「测量」，各家字段见 `../research.md`。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

**难度：中。** 三个适配器各读一个字段、计量多一个数、服务调用表补一列、价格多一项（预设、两个目录、管理者设定、价格页）、估算和看板。不碰回合和提示词，可以和 02、03 并行；和 02 都改适配器，合并时注意。

## 已定的设计（详见 spec）

- 只记命中，不记写入。命中是总输入的一部分；Anthropic 的总输入仍是三项之和。
- Chat Completions：`usage.prompt_tokens_details.cached_tokens` → `prompt_cache_hit_tokens` → `usage.cached_tokens`；Responses：`usage.input_tokens_details.cached_tokens`；Anthropic：`cache_read_input_tokens`。都没有记为空（「没报」）。
- 服务调用表补一列「命中的输入」，可为空。
- 价格多一项缓存命中价，可为空：models.dev `cost.cache_read`、OpenRouter `pricing.input_cache_read`（乘一百万）、预设里查得到官方价的补上、管理者可设。
- 估算：（总输入 − 命中）× 输入价 + 命中 ×（缓存命中价，没有就输入价）；没报命中按 0。
- 看板 LLM 行显示命中率 = 命中 ÷ 总输入，没报的按 0 计入。自带密钥照样记，看板照旧只显示「自带」。

## 验收

- [ ] 适配器测试：三种协议从各自字段读出命中数，Chat Completions 三个候选字段各一例；没报时为空；总输入口径不变。
- [ ] 运行记录测试（真的 `ActivityLog`、临时库）：一次 LLM 调用记下命中数；旧表启动时补上这一列，旧记录为空。
- [ ] 价格目录测试：models.dev 和 OpenRouter 都读出缓存命中价，缺这一项时为空。
- [ ] 估算测试：按缓存价算命中部分；缺缓存价按输入价；没报命中按 0；管理者设的缓存价优先。
- [ ] 看板测试：用量里有命中数，LLM 行有命中率；非 LLM 行不变。
- [ ] 前端纯函数测试：价格页的缓存命中价显示和保存；看板命中率。
- [ ] 改表结构前，提醒用户按 VPS 部署的惯例先手动备份线上库。
- [ ] 实测：本地构建版接真实 `deepseek-flash`，同一位角色连发几个文字回合，看板出现命中率，价格页出现缓存命中价。
- [ ] `backend/` 下 `pytest`、`frontend/` 下 `npm test` 全部通过，`ruff`、`pyright`、`tsc` 没有新的报错。

## Comments
