# 01: JUDGE_PROVIDER 二选一，直连 Cloudflare Clef

**What to build:** 部署时用 `JUDGE_PROVIDER=jev|cloudflare` 选判断模型。选 `cloudflare` 时，检索判断和通话中的情绪判断都直连 Workers AI 上的 Clef 或 Clef-flash。已有的部署不改配置，行为完全不变。调研见 `../research.md`。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] 配置：
  - `JUDGE_PROVIDER`：`jev` | `cloudflare`，不填为 `jev`，其他值启动报错。
  - `jev`：沿用 `JevSettings`，`JEV_*` 变量和 `AI_GATEWAY_API_KEY` 改名报错都不变。
  - `cloudflare`：`CLOUDFLARE_API_TOKEN`、`CLOUDFLARE_ACCOUNT_ID` 两个都必填，缺一个就启动报错并说出变量名；`CLOUDFLARE_JUDGE_MODEL` 取 `clef` | `clef-flash`，不填为 `clef-flash`，其他值启动报错。
  - 选了 `cloudflare` 却配着 `JEV_API_KEY` 时，不报错，`JEV_*` 被忽略。
- [ ] 检索和情绪判断的开启条件：「有 Jev」改为「有所选的判断模型」。`assembly.py` 的说明和缺配置时的提示同步修改。
- [ ] 新增一个 Cloudflare 的判断实现，和 `JevJudge` 有相同的 `judge` / `ask` 能力（`JevEmotionJudge` 能接在它上面，或者把两者抽成一个共同的接口）：
  - 请求：`POST https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/cloudflare/{model}`，`Authorization: Bearer <token>`，body `{model: "clef"|"clef-flash", state, questions}`。
  - 读 `res.json()["result"]["answers"]`。HTTP 错误、`success: false`、信封或答案无法解析时都抛 `JudgeError`，消息里带上 `errors` 的内容。
  - 超时和 `JevJudge` 一样（5s，连接 3s）。
  - 额度用完时（Cloudflare 的错误里能看出是 neurons 或额度用完），`JudgeError` 的消息要说清楚是每日免费额度用完。
- [ ] 问题定义（三个是/否题、情绪和点头两道多选题）两家共用一份，不复制。
- [ ] 启动检查（只在 `cloudflare` 时）：用最小的请求问一个 `noul` 题。
  - 401/403 报「CLOUDFLARE_API_TOKEN 无效或缺少 Workers AI 权限」，拒绝启动；
  - 404 或账号不存在的错误报「CLOUDFLARE_ACCOUNT_ID 不对」，拒绝启动；
  - 超时或连不上只打警告，照常启动。
- [ ] 测试（`httpx.MockTransport`）：
  - 请求的 URL、header 和 body；
  - 从信封里取答案；
  - `success: false`、HTTP 错误、无法解析时的报错；
  - 配置解析：默认值、非法的 provider 和 model、缺 token 或 account id；
  - 启动检查的三种结果；
  - `JUDGE_PROVIDER=cloudflare` 时，检索和情绪判断都接上了 Cloudflare 的实现。
- [ ] 全部测试通过，pyright 和 ruff 无错误。

真实 key 的验收放在 04。
