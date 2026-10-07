# 14: 单价从在线目录自动获取

**What to build:** 单价不再只靠写死的预设：后端定期从 models.dev（`https://models.dev/api.json`）和 OpenRouter（`https://openrouter.ai/api/v1/models?output_modalities=all`）拉取模型目录，按「服务地址的主机名 + 模型名」自动匹配出单价，用来估算花费。生效顺序是 **后台设的价格 > 在线目录 > 代码里的预设 > 未设单价**。预设退为离线时的兜底，以及目录里没有的单价（按字节、按秒计费的，和目录没收录的模型）。做法参照 magpie（`yetone/magpie` 的 `internal/catalog/`）。见 `../spec.md` 的「看板与单价」一节和 `../research.md` 的第 11 节。

**Blocked by:** 10

**Status:** ready-for-agent

已定下的：

- DeepSeek 等目录里有的模型，直接用目录的价格（models.dev 给的是一套美元价），不区分高峰和低谷；想用别的价，在后台覆盖。
- 花费和现在一样，按查看时生效的单价计算；单价变了，过去的花费也跟着变（magpie 也是这样），不在运行记录里存单价。
- 服务地址的主机名在目录里对不上提供方时（中转、代理），拿规整后的模型名到原厂提供方里找；找到就按原厂价格估算，并在界面上标注「按原厂价格估算」。
- 后台有「立即从目录刷新」按钮。
- VPS 的后端容器可以直接访问两个地址，不需要代理（2026-10-07 实测，见 research.md）。

- [ ] 拉取：用 httpx 带 `Accept-Encoding: gzip` 拉取（models.dev 的 JSON 解压后约 5.3 MB，不压缩时宿主机下载要 30 秒，压缩后 1～3 秒），超时 60 秒。只保留按 token 计价、带 `cost` 的条目，存进数据库新表（例如 `price_catalog`：来源、提供方、模型、输入价、输出价、拉取时间），在 `database.py` 登记为不是用户数据。另记最近一次拉取成功的时间，以及最近一次失败的时间和原因。
- [ ] 刷新时机：进程启动后在后台拉取一次（不阻塞启动）；之后每小时检查一次，目录超过 24 小时就重新拉取；看板或单价页遇到没有单价的模型，而上次拉取已超过 6 小时，就在后台补拉一次。同一时间最多一次拉取。拉取失败只写日志、记下原因，继续用上一份目录；从没拉成功过就只用预设。看板和单价页的接口不等网络。
- [ ] 主机名对到提供方：OpenRouter（`openrouter.ai`）用 OpenRouter 自己的 API，因为 Jev、Clef 在 models.dev 上没有价格。OpenRouter 的 `pricing.prompt` 和 `pricing.completion` 是 USD/token，要乘以 1,000,000。其他主机名优先和 models.dev 提供方的 `api` 字段里的主机名比较（例如 `api.deepseek.com`、`api.siliconflow.cn`）；没有 `api` 字段的原厂提供方写一张小映射表：`api.openai.com` → `openai`，`api.anthropic.com` → `anthropic`，`generativelanguage.googleapis.com` → `google`。
- [ ] 模型名匹配，照 magpie 的 `PricedBy` 一级级放宽，命中就停。运行记录里模型名带的 `@维度` 后缀（`gemini-embedding-2@1536`）先去掉，和现在找预设的做法一样。然后：原样 → 转成小写并去掉路径前缀（`openai/GPT-6-Sol` → `gpt-6-sol`）→ 再去掉 `:tag` 和 `(variant)` → 把 `.` 和 `-` 当成同一个字符（`claude-opus-4.6` ↔ `claude-opus-4-6`）。同一级命中多条时，按键名排序取第一条，保证结果确定。
- [ ] 主机名对不上任何提供方时，按上面的规则在原厂提供方（`openai`、`anthropic`、`google`、`deepseek`，以及 models.dev 上其他模型名带厂商前缀、能认出原厂的）里找，命中的单价标为「按原厂价格估算」。
- [ ] 只用目录的 `input` 和 `output`（USD，每百万 token），不管 cache 价和按上下文长度分档的价格（`tiers`），和现在「短上下文、不算缓存折扣」的口径一致。目录只用于计费单位是 `tokens` 的调用；`bytes`、`seconds` 只看后台设的价格和预设。
- [ ] `Prices.effective()`（或它的替代）返回每个单价的来源：`override`、`catalog`、`catalog_upstream`（按原厂价格估算）、`preset`，并带 `as_of`。目录的单价用拉取日期作 `as_of`。看板花费一节的「价格整理于某日」改为按来源说明，例如「目录价格更新于某日；部分为预设，整理于 2026-10-07」。
- [ ] 后台单价页：每一行显示生效价格和它的来源，目录价和预设价并列显示（便于对比，例如 DeepSeek 预设的人民币价和目录的美元价）。顶部显示目录的拉取时间和最近一次失败的原因，以及「立即从目录刷新」按钮，对应新接口 `POST /api/admin/prices/refresh`：同步拉取，返回结果，已经在拉就等它拉完。「未设单价的模型」一节只列目录和预设都匹配不到的模型。
- [ ] 预设 `PRESETS` 保留不删；代码注释和 `research.md` 说明预设现在只是兜底。
- [ ] 前端的显示规则（来源的文案、拉取时间和失败的显示）写在 `lib/adminPrices.ts`，并有单元测试。
- [ ] 测试（HTTP API，目录用假的 HTTP 响应注入，不访问网络）：目录价格优先于预设、后台设的价格优先于目录；四级模型名规整各命中一次；主机名对不上时按原厂价格估算并标注；OpenRouter 的单价按每 token 换算对了；拉取失败时继续用上一份目录、记下原因；从没拉成功过时退回预设；目录超过 24 小时会重新拉取，没有单价的模型最多每 6 小时触发一次补拉；`bytes`、`seconds` 单位不受目录影响；手动刷新接口只有管理者能用。
- [ ] 文档：`docs/deploy.md` 写明后端会定期访问 models.dev 和 openrouter.ai 拉取公开的价格目录，请求里不带任何用户数据；访问不了时，花费按预设和后台设的价格估算。

## Comments
