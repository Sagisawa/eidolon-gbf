"""Text embeddings for the vector index: Qwen3-Embedding on SiliconFlow."""

from collections.abc import Sequence
from typing import Protocol

import httpx
import numpy as np

_REQUEST_BATCH = 16
"""Texts sent in one request."""
_QUERY_INSTRUCTION = "Instruct: 根据问题，检索相关的剧情台词\nQuery: "


class Embedder(Protocol):
    model: str
    """Vectors from different models are not comparable; the index keeps them apart by this."""

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class EmbeddingError(RuntimeError):
    pass


class NoEmbedder:
    """For reading the story corpus without searching it or adding to it."""

    model = "none"

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        raise EmbeddingError("没有配置向量化服务")

    async def embed_query(self, text: str) -> list[float]:
        raise EmbeddingError("没有配置向量化服务")


class SiliconFlowEmbedder:
    """OpenAI-compatible `/embeddings` endpoint. Qwen3-Embedding wants an instruction in
    front of queries and none in front of documents."""

    def __init__(
        self, api_key: str, model: str, base_url: str, client: httpx.AsyncClient | None = None
    ) -> None:
        self.model = model
        self._url = base_url.rstrip("/") + "/embeddings"
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(120, connect=10))

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _REQUEST_BATCH):
            vectors.extend(await self._embed(texts[start : start + _REQUEST_BATCH]))
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([_QUERY_INSTRUCTION + text]))[0]

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        try:
            res = await self._client.post(
                self._url,
                json={"model": self.model, "input": list(texts), "encoding_format": "float"},
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        except httpx.HTTPError as e:
            raise EmbeddingError(f"无法连接向量化服务：{e!r}") from e
        if res.status_code >= 400:
            raise EmbeddingError(f"向量化服务返回 {res.status_code}: {res.text[:500]}")
        try:
            data = sorted(res.json()["data"], key=lambda d: d["index"])
        except (ValueError, KeyError, TypeError) as e:
            raise EmbeddingError(f"向量化服务的返回无法解析：{res.text[:500]}") from e
        if len(data) != len(texts):
            raise EmbeddingError(f"向量化服务返回了 {len(data)} 个向量，应为 {len(texts)} 个")
        return [d["embedding"] for d in data]


def nearest(
    vectors: Sequence[bytes], query: Sequence[float], limit: int
) -> list[tuple[int, float]]:
    """Indexes of the stored `vectors` most similar to `query` by cosine similarity, best
    first, with their scores."""
    if not vectors:
        return []
    query_vector = np.asarray(query, dtype=np.float32)
    matrix = np.stack([np.frombuffer(v, dtype=np.float32) for v in vectors])
    scores = matrix @ query_vector / (
        np.linalg.norm(matrix, axis=1) * np.linalg.norm(query_vector) + 1e-12
    )
    return [(int(i), float(scores[i])) for i in np.argsort(-scores)[:limit]]


def to_blob(vector: Sequence[float]) -> bytes:
    """A vector as stored in SQLite."""
    return np.asarray(vector, dtype=np.float32).tobytes()
