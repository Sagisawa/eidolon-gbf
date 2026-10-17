# 22: 列表最后一句的相机图标

**What to build:** 对话列表和历史对话面板里，最后一条是她发出来的照片时，最后一句前面有一个相机图标，后面照旧是她的话。用户一眼就知道她最后发了照片。规格见 `../spec.md`「接口和事件」的最后一句一条、「前端」的列表一条。

**Blocked by:** 14

**Status:** ready-for-agent

- [ ] **后端**：最后一条是带照片、而且照片发出来了的回复时，列表接口的最后一句带上一个标记。照片没发出来、还在生成时不带。
- [ ] **前端**：最后一句带这个标记时，前面加一个 14px 的 muted 相机图标，写法和对话事件「图标加原文」一样。对话列表和历史对话面板的行都这样。
- [ ] **`DESIGN.md`**：补上列表最后一句的写法。
- [ ] **测试**：
  - 后端：发出来了的带标记；生成中的、失败的不带（先例是 `test_conversation_summaries.py`、`test_past_conversations.py`）。
  - 前端：`conversationList.test.ts`。
- [ ] `uv run pytest`、`uv run pyright`、`npm test`、`npm run typecheck` 全部通过。
