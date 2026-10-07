"""Anthropic Messages provider."""

import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

from eidolon.llm import ChatMessage, LLMError, Tool, ToolCall
from eidolon.llm.sse import parse_arguments, stream_events

log = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 16384
"""The Messages API requires a cap on the reply's length; a drafted character sheet runs to
several thousand tokens, and the model's reasoning, if it streams any, counts too."""

API_VERSION = "2023-06-01"


class AnthropicLLM:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        client: httpx.AsyncClient | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self._url = base_url.rstrip("/") + "/messages"
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens or DEFAULT_MAX_TOKENS
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10))

    async def stream(
        self, messages: Sequence[ChatMessage], tools: Sequence[Tool] = ()
    ) -> AsyncIterator[str | ToolCall]:
        body: dict[str, Any] = {
            "model": self._model,
            "stream": True,
            "max_tokens": self._max_tokens,
        }
        if system := "\n\n".join(m.content for m in messages if m.role == "system"):
            body["system"] = system
        body["messages"] = _messages([m for m in messages if m.role != "system"])
        if tools:
            body["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in tools
            ]
        calls: dict[int, dict[str, Any]] = {}  # content block index → the tool_use so far
        headers = {"x-api-key": self._api_key, "anthropic-version": API_VERSION}
        async for event in stream_events(self._client, self._url, body, headers):
            kind = event.get("type")
            if kind == "content_block_start":
                block = event.get("content_block") or {}
                if block.get("type") == "tool_use":
                    calls[event.get("index", len(calls))] = {
                        "id": block.get("id") or "",
                        "name": block.get("name") or "",
                        "input": block.get("input") or {},
                        "json": "",
                    }
            elif kind == "content_block_delta":
                delta = event.get("delta") or {}
                if delta.get("type") == "text_delta":
                    if text := delta.get("text"):
                        yield text
                elif delta.get("type") == "input_json_delta":
                    if (call := calls.get(event.get("index", -1))) is not None:
                        call["json"] += delta.get("partial_json") or ""
            elif kind == "message_delta":
                stop = (event.get("delta") or {}).get("stop_reason")
                if stop in ("max_tokens", "refusal"):
                    log.warning("the model stopped early: %s", stop)
            elif kind == "error":
                error = event.get("error") or {}
                raise LLMError(f"模型在流式输出中报错: {error.get('message') or event}")
        for index, call in sorted(calls.items()):
            call_id = call["id"] or f"call_{index}"  # the tool result must name its call
            # Without any input deltas, the input the block started with is all there is.
            arguments = (
                parse_arguments(call["json"])
                if call["json"]
                else call["input"] if isinstance(call["input"], dict) else None
            )
            yield ToolCall(call_id, call["name"], arguments)

    async def aclose(self) -> None:
        await self._client.aclose()


def _messages(messages: Sequence[ChatMessage]) -> list[dict[str, Any]]:
    """Messages API turns; the results of one round of tool calls go back together, in the
    user turn that follows the calls."""
    turns: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "tool":
            result = {
                "type": "tool_result",
                "tool_use_id": message.tool_call_id,
                "content": message.content,
            }
            last = turns[-1] if turns else None
            if last and last["role"] == "user" and isinstance(last["content"], list):
                last["content"].append(result)
            else:
                turns.append({"role": "user", "content": [result]})
        elif message.tool_calls:
            content: list[dict[str, Any]] = []
            if message.content:
                content.append({"type": "text", "text": message.content})
            content.extend(
                {"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments or {}}
                for c in message.tool_calls
            )
            turns.append({"role": "assistant", "content": content})
        elif message.content:  # the Messages API rejects empty text
            turns.append({"role": message.role, "content": message.content})
    return turns
