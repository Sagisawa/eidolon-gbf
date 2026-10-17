# 20: 自带生图

**What to build:** 有自己 NovelAI token 或中转的用户，可以在设置页「自带密钥」里填上生图。key 只存在自己的浏览器里，保存前会真生成一张来检查。之后照片花用户自己的钱，不占每小时的次数；部署者没配生图时，用户也能收到照片。自带的 key 失败时，照片的位置写着「你的生图密钥没能用」，并有一个去设置页的链接，不会悄悄改用部署者的 key。规格见 `../spec.md`「自带生图」「能不能发照片」「生成：生图客户端」的网络一条、「限额」的免限额一条，以及 ADR-0017、ADR-0022。

**Blocked by:** 18, 19

**Status:** ready-for-agent

- [ ] **设置页**：「自带密钥」加一项生图，填接口形式、接口地址、key、模型四项，默认值和后台一样，只存在浏览器里。不出「同时生成几张」和画风。这一项一直显示。
- [ ] **保存前检查**：调 `POST /api/account/keys/image/check`，花用户自己的钱真生成一张，规则和后台的检查一样，不计用量、不进运行记录。部署没有判断模型时直接拒绝：「这个部署发不了照片」，不生成。
- [ ] **随请求带上**：文字回合的请求体加上自带生图，通话本来就带全部。
- [ ] **照片资格**：
  - 带了自带生图就用自带的。部署者没配也能发；限额为 0 的用户也能发。
  - 自带的 token 固定一次一张，各排各的。
  - 部署者的画风照样生效。
- [ ] **失败**：自带 key 失败时记成 `own_key_failed`，不改用部署者的，错误里的 key 打码。
- [ ] **免限额**：
  - 用自带生图生成的照片不计入次数（用量照写一行，标成不计入）。
  - 带了自带 LLM 但没带生图 key：回合照旧不计入，照片照样计入。
  - 「生图」不进免限额密钥：`Service` 加上 `image`，但免限额密钥仍然只有 LLM、语音合成、语音识别三项。
- [ ] **网络和 SSRF**：
  - `ProxiedService` 加 `own_image`。只有 HTTPS 的 `image.novelai.net` 算已知服务商，勾上才走代理；其他地址一律直连。
  - 公开部署里自带的地址必须是 HTTPS 的公网地址，每次连接都查，下载 `url` 时也一样（复用现有的公网检查后端）。
  - `EIDOLON_PROXY_SERVICES` 认 `own_image`，代理卡加上这一项。
- [ ] **测试**：
  - 检查接口的成功、失败，以及没有判断模型时拒绝。
  - 带了自带生图时用它、不计入次数；没配部署者生图也能发；限额为 0 也能发。
  - `own_key_failed` 时不改用部署者的、key 打码。
  - 免限额密钥里没有生图。
  - 内网地址被拒；只对官方地址走代理。
  - 先例是 `test_own_llm.py`、`test_own_speech_keys.py`、`test_exempting_keys.py`、`test_proxy.py`、`test_own_keys_in_logs.py`；前端是 `localOwnKeys.test.ts`、`api.test.ts`。
- [ ] **验收**：本地构建版上用 Playwright：设置页填自带生图（检查走假服务）、要一张照片、自带 key 失败时的说明和链接。
- [ ] `uv run pytest`、`uv run pyright`、`npm test`、`npm run typecheck` 全部通过。

## Comments

**票 15 留下的（2026-10-17）。** 生图调用记在运行记录的 `image` 下，`Origin` 现在只有部署者的 `activity.image_origin(settings)`（地址的 host 加模型名，`own_key=False`）。自带生图要另给一个 `own_key=True` 的 `Origin`，`prices.cost` 才会只统计、不计价；服务商和模型记成什么要定：照 ADR-0017 自带 LLM 一律记 `OWN`，自带生图的地址也可能是用户自己的中转，建议同样记 `OWN`（`activity._forget_own_llms` 只管 LLM，别漏）。张数靠 `ImageGenerator.generate` 里的 `bill("images", …)`，自带的客户端沿用它就自然有。
