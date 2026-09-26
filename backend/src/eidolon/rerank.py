"""Reranking retrieved text against the query: Qwen3-Reranker on SiliconFlow."""

from collections.abc import Sequence
from typing import Protocol

import httpx


class Reranker(Protocol):
    async def rerank(
        self, query: str, documents: Sequence[str], top_n: int
    ) -> list[tuple[int, float]]:
        """Indexes into `documents` of the (at most) `top_n` most relevant, best first, with
        their relevance scores (0 to 1)."""
        ...


class RerankError(RuntimeError):
    pass


class SiliconFlowReranker:
    """SiliconFlow's `/rerank` endpoint."""

    def __init__(
        self, api_key: str, model: str, base_url: str, client: httpx.AsyncClient | None = None
    ) -> None:
        self.model = model
        self._url = base_url.rstrip("/") + "/rerank"
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(30, connect=10))

    async def rerank(
        self, query: str, documents: Sequence[str], top_n: int
    ) -> list[tuple[int, float]]:
        try:
            res = await self._client.post(
                self._url,
                json={
                    "model": self.model,
                    "query": query,
                    "documents": list(documents),
                    "top_n": top_n,
                    "return_documents": False,
                },
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        except httpx.HTTPError as e:
            raise RerankError(f"无法连接重排服务：{e!r}") from e
        if res.status_code >= 400:
            raise RerankError(f"重排服务返回 {res.status_code}: {res.text[:500]}")
        try:
            results = sorted(res.json()["results"], key=lambda r: -r["relevance_score"])
            ranked = [(int(r["index"]), float(r["relevance_score"])) for r in results]
        except (ValueError, KeyError, TypeError) as e:
            raise RerankError(f"重排服务的返回无法解析：{res.text[:500]}") from e
        if any(not 0 <= i < len(documents) for i, _ in ranked):
            raise RerankError(f"重排服务返回了不存在的文档编号：{[i for i, _ in ranked]}")
        return ranked[:top_n]

    async def aclose(self) -> None:
        await self._client.aclose()
