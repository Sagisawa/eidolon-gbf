"""Building a model slot's provider from its settings, and checking the chat model can do
what conversations need of it."""

import httpx

from eidolon.config import LLMProtocol, LLMSettings
from eidolon.llm import ChatLLM, ChatMessage, LLMError, Reasoning, Tool, ToolCall
from eidolon.llm.anthropic import AnthropicLLM
from eidolon.llm.openai_compat import OpenAICompatLLM
from eidolon.llm.responses import ResponsesLLM

_PROVIDERS: dict[LLMProtocol, type[OpenAICompatLLM | ResponsesLLM | AnthropicLLM]] = {
    "chat-completions": OpenAICompatLLM,
    "responses": ResponsesLLM,
    "anthropic": AnthropicLLM,
}


def open_llm(settings: LLMSettings, client: httpx.AsyncClient | None = None) -> ChatLLM:
    provider = _PROVIDERS[settings.protocol]
    return provider(
        settings.base_url,
        settings.api_key,
        settings.model,
        client=client,
        max_tokens=settings.max_tokens,
    )


_PROBE_TOOL = Tool(
    "ping",
    "检查工具调用是否可用。",
    {"type": "object", "properties": {"ok": {"type": "boolean"}}},
)
_PROBE = [ChatMessage("user", "这是一次连通性检查，请调用 ping 工具，不用回复其他内容。")]
_PROBE_RESULT = '{"ok": true}'


async def check_chat_llm(llm: ChatLLM) -> None:
    """Raise an `LLMError` saying what is missing unless the model streams its reply to a
    request that offers it a tool, and, if it calls the tool, to the result of the call,
    as a turn's last round asks it: the same tools offered, none to be called. Whether it
    calls the tool is up to the model."""
    try:
        await _probe(llm, [_PROBE_TOOL])
        return
    except LLMError as e:
        with_tool = e
    try:  # the same request without the tool tells the two failures apart
        await _probe(llm, [])
    except LLMError:
        raise LLMError(
            f"对话模型需要支持流式输出和工具调用，但检查请求失败：{with_tool}"
        ) from None
    try:  # the first failure may have been passing, say a timeout or a rate limit
        await _probe(llm, [_PROBE_TOOL])
        return
    except LLMError as e:
        raise LLMError(
            f"对话模型不支持工具调用（不提供工具时可以正常回复），无法使用「回顾剧情」：{e}"
        ) from None


async def _probe(llm: ChatLLM, tools: list[Tool]) -> None:
    said = ""
    calls: list[ToolCall] = []
    reasoning: list[Reasoning] = []
    async for item in llm.stream(_PROBE, tools):
        if isinstance(item, ToolCall):
            calls.append(item)
        elif isinstance(item, Reasoning):
            reasoning.append(item)
        else:
            said += item
    if not calls:
        return
    answered = [
        *_PROBE,
        ChatMessage("assistant", said, tuple(calls), reasoning=tuple(reasoning)),
        *(ChatMessage("tool", _PROBE_RESULT, tool_call_id=c.id) for c in calls),
    ]
    async for _ in llm.stream(answered, tools, forbid_calls=True):
        pass
