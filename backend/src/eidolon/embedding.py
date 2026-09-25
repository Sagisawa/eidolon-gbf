"""Text embeddings for the vector index: Qwen3-Embedding on SiliconFlow."""

from collections.abc import Sequence
from typing import Protocol

import httpx

DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_MODEL = "Qwen/Qwen3-Embedding-0.6B"

_BATCH_SIZE = 16
_QUERY_INSTRUCTION = "Instruct: 根据问题，检索相关的剧情片段\nQuery: "


class Embedder(Protocol):
    model: str
    """Vectors from different models are not comparable; the index keeps them apart by this."""

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class EmbeddingError(RuntimeError):
    pass


class SiliconFlowEmbedder:
    """OpenAI-compatible `/embeddings` endpoint. Qwen3-Embedding wants an instruction in
    front of queries and none in front of documents."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self._url = base_url.rstrip("/") + "/embeddings"
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(120, connect=10))

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH_SIZE):
            vectors.extend(await self._embed(texts[start : start + _BATCH_SIZE]))
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([_QUERY_INSTRUCTION + text]))[0]

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        res = await self._client.post(
            self._url,
            json={"model": self.model, "input": list(texts), "encoding_format": "float"},
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        if res.status_code >= 400:
            raise EmbeddingError(f"向量化服务返回 {res.status_code}: {res.text[:500]}")
        data = sorted(res.json()["data"], key=lambda d: d["index"])
        if len(data) != len(texts):
            raise EmbeddingError(f"向量化服务返回了 {len(data)} 个向量，应为 {len(texts)} 个")
        return [d["embedding"] for d in data]
