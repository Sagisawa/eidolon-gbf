"""OpenAI Responses provider."""

import json
import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

from eidolon.billing import bill
from eidolon.llm import ChatMessage, LLMError, Streamed, Tool, ToolCall
from eidolon.llm.sse import parse_arguments, stream_events

log = logging.getLogger(__name__)


class ResponsesLLM:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        client: httpx.AsyncClient | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self._url = base_url.rstrip("/") + "/responses"
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10))

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[Tool] = (),
        *,
        forbid_calls: bool = False,
    ) -> AsyncIterator[Streamed]:
        body: dict[str, Any] = {
            "model": self._model,
            "stream": True,
            "store": False,  # every request carries the whole conversation
        }
        if system := "\n\n".join(m.content for m in messages if m.role == "system"):
            body["instructions"] = system
        body["input"] = [item for m in messages if m.role != "system" for item in _items(m)]
        if self._max_tokens is not None:
            body["max_output_tokens"] = self._max_tokens
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                }
                for t in tools
            ]
            if forbid_calls:
                body["tool_choice"] = "none"
        calls: dict[int, dict[str, str]] = {}  # output index → call id, name and arguments
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async for event in stream_events(self._client, self._url, body, headers):
            kind = event.get("type")
            if kind == "response.output_text.delta":
                if delta := event.get("delta"):
                    yield delta
            elif kind in ("response.output_item.added", "response.output_item.done"):
                item = event.get("item") or {}
                if item.get("type") == "function_call":
                    call = calls.setdefault(
                        event.get("output_index", len(calls)),
                        {"id": "", "name": "", "arguments": ""},
                    )
                    call["id"] = item.get("call_id") or call["id"]
                    call["name"] = item.get("name") or call["name"]
                    # Once done, the item carries the arguments in full.
                    call["arguments"] = item.get("arguments") or call["arguments"]
            elif kind == "response.function_call_arguments.delta":
                if (call := calls.get(event.get("output_index", -1))) is not None:
                    call["arguments"] += event.get("delta") or ""
            elif kind == "error":
                raise LLMError(f"模型在流式输出中报错: {event.get('message') or event}")
            elif kind == "response.failed":
                error = (event.get("response") or {}).get("error") or event
                raise LLMError(f"模型生成失败: {error}")
            elif kind == "response.incomplete":
                details = (event.get("response") or {}).get("incomplete_details")
                log.warning("the model's reply is incomplete: %s", details)
            if kind in ("response.completed", "response.incomplete"):
                usage = (event.get("response") or {}).get("usage")
                if isinstance(usage, dict):
                    bill("tokens", usage.get("input_tokens"), usage.get("output_tokens"))
        for index, call in sorted(calls.items()):
            call_id = call["id"] or f"call_{index}"  # the tool result must name its call
            yield ToolCall(call_id, call["name"], parse_arguments(call["arguments"]))

    async def aclose(self) -> None:
        await self._client.aclose()


def _items(message: ChatMessage) -> list[dict[str, Any]]:
    if message.role == "tool":
        return [
            {
                "type": "function_call_output",
                "call_id": message.tool_call_id,
                "output": message.content,
            }
        ]
    items: list[dict[str, Any]] = []
    if message.content:
        items.append({"role": message.role, "content": message.content})
    items.extend(
        {
            "type": "function_call",
            "call_id": call.id,
            "name": call.name,
            "arguments": json.dumps(call.arguments or {}, ensure_ascii=False),
        }
        for call in message.tool_calls
    )
    return items
