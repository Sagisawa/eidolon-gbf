# 02: Anthropic 和 Responses 也带回思考内容

**What to build:** 对话模型接的是默认开着思考的 Claude 5.5（Anthropic 协议），或者 OpenAI 推理模型（Responses 协议）时，工具调用之后的那次请求把模型刚才的思考原样带回，「回顾剧情」照常可用，模型也记得自己刚才想了什么。背景见 `../spec.md`「回合内回传思考内容」。

**Blocked by:** 01（思考内容这种流式条目、引擎把它挂在助手消息上、检查走两轮，都在 01）

**Status:** ready-for-agent

**难度：中高。** 接口和引擎在 01 里已经就位，这张票只改两个适配器的读和写，但两种协议的格式各不相同，要手写录制文件。

## 已定的设计（详见 spec）

- Anthropic：保留 `thinking` 和 `redacted_thinking` 块（含 `signature`），按原来的顺序放在 text 和 tool_use 前面写回助手消息。流式时 thinking 块由 `content_block_start`、`thinking_delta`、`signature_delta` 拼出来。
- Responses：保留 `reasoning` item（含 `encrypted_content`），按原来的顺序放在 function_call 前面写回 input。`store` 仍然是 `false`。
- 只带回服务发来的东西；没发就和现在一样。本票不发 `include`，强度设置在 03 里加。

## 验收

- [ ] 适配器测试（Anthropic）：录好的流里有 thinking 块（含签名）和 tool_use，下一次请求的助手消息依次是 thinking、（text）、tool_use，内容和签名原样；有 redacted_thinking 时同样带回。
- [ ] 适配器测试（Responses）：录好的流里有带 `encrypted_content` 的 reasoning item 和 function_call，下一次请求的 input 里，reasoning item 原样排在 function_call 前面。
- [ ] 两种协议流里没有思考内容时，请求体和现在一样。
- [ ] 录制文件放在现有的录制目录，形状以 `../research.md` 第 2 节引用的官方文档为准。
- [ ] `backend/` 下 `pytest` 全部通过，`ruff` 和 `pyright` 没有新的报错。
- [ ] **人工验收（留给用户，有密钥时）**：用 Claude 5.5 或 OpenAI 推理模型实际走一次回顾剧情。
