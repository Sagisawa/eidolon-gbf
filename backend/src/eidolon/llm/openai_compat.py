"""OpenAI-compatible Chat Completions provider."""

import json
from collections.abc import AsyncIterator, Sequence

import httpx

from eidolon.llm import ChatMessage


class OpenAICompatLLM:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10))

    async def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        body = {
            "model": self._model,
            "stream": True,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with self._client.stream("POST", self._url, json=body, headers=headers) as res:
            if res.status_code >= 400:
                await res.aread()
                raise LLMError(f"对话模型返回 {res.status_code}: {res.text[:500]}")
            async for line in res.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if data == "[DONE]":
                    break
                event = json.loads(data)
                if event.get("error"):
                    raise LLMError(f"对话模型在流式输出中报错: {event['error']}")
                for choice in event.get("choices") or []:
                    content = (choice.get("delta") or {}).get("content")
                    if content:
                        yield content

    async def aclose(self) -> None:
        await self._client.aclose()


class LLMError(RuntimeError):
    pass
