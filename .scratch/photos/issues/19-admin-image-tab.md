# 19: 后台「生图」标签页

**What to build:** 部署者不用改 `.env`，在后台新开的「生图」标签页就能配好生图：选接口形式（NovelAI 官方格式或 OpenAI 图像格式），填地址、key、模型、同时生成几张和画风。保存时真生成一张来检查，填错了或者中转会换尺寸，都当场拦下。画风对整个部署的照片生效。规格见 `../spec.md`「生成：生图客户端」的两种接口形式和网络、「后台配置」一节，以及 `11-art-style-prototype.md` 的 Answer。

**Blocked by:** 16

**Status:** ready-for-agent

- [ ] **OpenAI 图像格式**：
  - 地址填到 `/v1`，服务器拼 `/images/generations`，带 `response_format: "b64_json"` 和顶层的 `size`、`negative_prompt`。
  - 收 `b64_json`（带不带 `data:` 前缀都行）；回 `url` 就用同一个客户端立刻下载，耗时算进 90 秒。chat 形状的返回不认。
  - 切换接口形式时不自动改地址。
- [ ] **环境变量**：认 `NOVELAI_API_FORMAT`（`novelai` 或 `openai`，默认 `novelai`）、`NOVELAI_CONCURRENCY`（默认 1）、`NOVELAI_STYLE`（默认空）。
- [ ] **后台**：「生图」标签页放在「语音」后面，只有一张生图卡：接口形式、接口地址、key、模型、同时生成几张、画风。
  - 模型是下拉加手填：下拉里放 V5 Curated/Full、V4.5 Curated/Full、V4 Curated/Full，默认 `nai-diffusion-5-curated`。
- [ ] **保存时的检查**：只在这张卡改了时，用固定的提示词带上画风，按正式的尺寸真生成一张，验 key、接口形式、返回能不能解开、宽高对不对。这张图不计用量、不进运行记录。失败时提示「试调失败，没有保存：…」。
- [ ] **画风**：原样插在作品 tag 后面、外貌 tag 前面，不清洗，可以带数值加权和多位画师；空着就整段不出现。
- [ ] **并发**：「同时生成几张」替换 16 里写死的 1。
- [ ] **代理**：`ProxiedService` 加 `image`，勾上就全走代理，接入点不受限制。`EIDOLON_PROXY_SERVICES` 认 `image`，代理卡加上这一项。
- [ ] 新加一项服务时照现有的那份清单都要动：设置、后台配置项、前端的后台配置。
- [ ] **测试**：
  - 两种接口形式的请求体（OpenAI 形式的顶层参数）和返回（`b64_json`、带 `data:` 前缀的、`url`）。
  - 保存检查：成功、key 错、尺寸不对时不保存。
  - 画风出现在提示词的位置；后台覆盖 `.env`；并发上限生效；代理开关。
  - 先例是 `test_live_config_services.py`、`test_proxy.py`；前端是 `adminConfig.test.ts`。
- [ ] **验收**：本地构建版上用 Playwright 看生图标签页，保存检查走假服务。用户的中转真生成一张，放在验收清单里交给用户点（花用户的额度）。
- [ ] `uv run pytest`、`uv run pyright`、`npm test`、`npm run typecheck` 全部通过。
