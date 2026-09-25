"""OpenAI-compatible Chat Completions provider."""

import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

from eidolon.llm import ChatMessage, LLMError, Tool, ToolCall
from eidolon.llm.sse import parse_arguments, stream_events

__all__ = ["LLMError", "OpenAICompatLLM"]


class OpenAICompatLLM:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        client: httpx.AsyncClient | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10))

    async def stream(
        self, messages: Sequence[ChatMessage], tools: Sequence[Tool] = ()
    ) -> AsyncIterator[str | ToolCall]:
        body: dict[str, Any] = {
            "model": self._model,
            "stream": True,
            "messages": [_message(m) for m in messages],
        }
        if self._max_tokens is not None:
            body["max_tokens"] = self._max_tokens
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
        calls: dict[int, dict[str, str]] = {}  # index → id, name and arguments so far
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async for event in stream_events(self._client, self._url, body, headers):
            if event.get("error"):
                raise LLMError(f"模型在流式输出中报错: {event['error']}")
            for choice in event.get("choices") or []:
                delta = choice.get("delta") or {}
                if content := delta.get("content"):
                    yield content
                for fragment in delta.get("tool_calls") or []:
                    call = calls.setdefault(
                        fragment.get("index", 0), {"id": "", "name": "", "arguments": ""}
                    )
                    call["id"] = fragment.get("id") or call["id"]
                    function = fragment.get("function") or {}
                    call["name"] = function.get("name") or call["name"]
                    arguments = function.get("arguments") or ""
                    # A few providers send the arguments as an object rather than JSON text.
                    if not isinstance(arguments, str):
                        arguments = json.dumps(arguments, ensure_ascii=False)
                    call["arguments"] += arguments
        for index, call in sorted(calls.items()):
            call_id = call["id"] or f"call_{index}"  # the tool result must name its call
            yield ToolCall(call_id, call["name"], parse_arguments(call["arguments"]))

    async def aclose(self) -> None:
        await self._client.aclose()


def _message(message: ChatMessage) -> dict[str, Any]:
    if message.role == "tool":
        return {"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content}
    if message.tool_calls:
        return {
            "role": "assistant",
            "content": message.content or None,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments or {}, ensure_ascii=False),
                    },
                }
                for call in message.tool_calls
            ],
        }
    return {"role": message.role, "content": message.content}
