# 16: 工具轮之后，模型把自己的工具调用标记当成回复输出

**What happened:** 对话模型调用一次「回顾剧情」后，引擎在最后一轮不再提供工具（`MAX_TOOL_ROUNDS = 1`，`engine.py` 里最后一轮 `offered = []`）。deepseek-v4.1-flash 这时如果还想再查一次，就会把它原生的工具调用标记当成普通文字输出。这段文字没有 `<ja>`/`<zh>` 标签，解析器把它整个当成一段日语，于是成了角色的回复（语音通话里还会被读出来）：

```
<｜｜DSML｜｜ calls>
<｜｜DSML｜｜ invoke name="recall_story">
<｜｜DSML｜｜ parameter name="query" string="true">決勝前コミュ 決勝前 ステージ前</｜｜DSML｜｜ parameter>
</｜｜DSML｜｜ invoke>
</｜｜DSML｜｜ calls>
```

**Blocked by:** —

**Status:** needs-triage

## 复现（2026-09-25，ticket 13 的真实服务验证中发现）

- 对话模型 deepseek-v4.1-flash，检索、剧情库都是真实服务；Jev 换成总是回答「不需要检索」的桩，让引擎把工具交给模型。
- 问真乃「W.I.N.G.决赛前你在后台说了什么？请先用回顾剧情工具查一下再回答」。
- Chat Completions 和 Responses 接口各跑一次，最终回复都是上面的标记；Anthropic 接口跑一次，正常回答。
- 第二次请求都正确带上了第一轮的调用和工具结果，所以不是适配器的问题，是模型在没有工具可用时仍然想调用。
- 平时 Jev 会把「那次……」类问题提前回顾，模型自己调用工具的情况不常见，但一旦发生回复就坏了。

## 可能的方向（待定）

- 最后一轮仍然提供工具，但告诉服务不许调用（Chat Completions / Responses 的 `tool_choice: "none"`，Anthropic 的 `tool_choice: {"type": "none"}`），需要扩展 `ChatLLM.stream` 的约定；
- 或者在最后一轮的提示词里明确说明「已经不能再查了，请根据已有结果回答」；
- 或者识别并丢弃这类标记，再重新请求一次。
