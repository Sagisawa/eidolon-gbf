# 04: 文档

**What to build:** 部署的人读完文档就知道怎么在 Qwen 与 Gemini 之间选、选了 Gemini 要注意什么、换模型后要做什么，以及重排默认模型和阈值的变化。

**Blocked by:** 01, 02, 03

**Status:** ready-for-agent

- [ ] `.env.example`：`EMBEDDING_PROVIDER`、`GEMINI_API_KEY`、`GEMINI_BASE_URL`、`EMBEDDING_DIMENSIONS`、`RERANK_MIN_RELEVANCE`、`RERANK_MEMORY_MIN_RELEVANCE` 及说明；把「更换后需要重新导入剧情库」改为「更换后运行 `eidolon reembed`」；注明免费层数据会被 Google 用于改进产品、Gemini API 不对中国大陆和港澳开放、重排仍需 `SILICONFLOW_API_KEY`；`RERANK_MODEL` 默认值改为 4B
- [ ] 三份 README（中、英、日）：特性、架构图、检索与记忆一节的开启条件，致谢里加上 Google Gemini；与 01–03 的实际行为一致
- [ ] `docs/deploy.md`：选择向量化服务、VPS 地区要求、换模型/换维度的步骤（改配置 → 重启 → `eidolon reembed`）、校准命令的用途
- [ ] 核对 ADR-0005 与最终实现一致（如实现中改了决定，更新 ADR）

## Comments
