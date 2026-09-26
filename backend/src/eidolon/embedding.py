"""Text embeddings for the vector index: Qwen3-Embedding on SiliconFlow, or Gemini
Embedding on Google's own API, whichever the deployment chose (ADR-0005)."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import httpx
import numpy as np

from eidolon.config import EmbeddingSettings

_REQUEST_BATCH = 16
"""Texts sent in one request to SiliconFlow."""
_QUERY_INSTRUCTION = "Instruct: 根据问题，检索相关的剧情台词\nQuery: "

GEMINI_BATCH = 100
"""Texts sent in one `batchEmbedContents` request; Google documents no limit."""


@dataclass(frozen=True)
class Document:
    """Text to embed for the index, with where it comes from: an episode's card or event and
    title for a story passage, a fact's headings for a character fact, None for a memory."""

    text: str
    title: str | None = None


class Embedder(Protocol):
    model: str
    """Vectors from different models are not comparable; the index keeps them apart by this."""

    async def embed_documents(self, documents: Sequence[Document]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class ClosableEmbedder(Embedder, Protocol):
    async def aclose(self) -> None: ...


class EmbeddingError(RuntimeError):
    pass


class NoEmbedder:
    """For reading the story corpus without searching it or adding to it."""

    model = "none"

    async def embed_documents(self, documents: Sequence[Document]) -> list[list[float]]:
        raise EmbeddingError("没有配置向量化服务")

    async def embed_query(self, text: str) -> list[float]:
        raise EmbeddingError("没有配置向量化服务")


class SiliconFlowEmbedder:
    """OpenAI-compatible `/embeddings` endpoint. Qwen3-Embedding wants an instruction in
    front of queries and none in front of documents, whose titles it is not given."""

    def __init__(
        self, api_key: str, model: str, base_url: str, client: httpx.AsyncClient | None = None
    ) -> None:
        self.model = model
        self._url = base_url.rstrip("/") + "/embeddings"
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(120, connect=10))

    async def embed_documents(self, documents: Sequence[Document]) -> list[list[float]]:
        texts = [d.text for d in documents]
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


class GeminiEmbedder:
    """Google's native `batchEmbedContents`, where each text is a request item of its own
    (texts sharing one item's `parts` would make one vector). Gemini Embedding 2 takes no
    task type, so queries and documents are told apart by prefixes. The model it stores
    vectors under carries the dimensions, so vectors of different lengths never mix."""

    def __init__(
        self,
        api_key: str,
        model: str,
        dimensions: int,
        base_url: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = f"{model}@{dimensions}"
        self._name = f"models/{model}"
        self._dimensions = dimensions
        self._url = f"{base_url.rstrip('/')}/{self._name}:batchEmbedContents"
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(120, connect=10))

    async def embed_documents(self, documents: Sequence[Document]) -> list[list[float]]:
        texts = [f"title: {d.title or 'none'} | text: {d.text}" for d in documents]
        vectors: list[list[float]] = []
        for start in range(0, len(texts), GEMINI_BATCH):
            vectors.extend(await self._embed(texts[start : start + GEMINI_BATCH]))
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([f"task: search result | query: {text}"]))[0]

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        requests = [
            {
                "model": self._name,
                "content": {"parts": [{"text": text}]},
                "output_dimensionality": self._dimensions,
            }
            for text in texts
        ]
        try:
            res = await self._client.post(
                self._url, json={"requests": requests}, headers={"x-goog-api-key": self._api_key}
            )
        except httpx.HTTPError as e:
            raise EmbeddingError(f"无法连接向量化服务：{e!r}") from e
        if res.status_code >= 400:
            hint = (
                "（Gemini API 不对中国大陆、香港、澳门开放，服务器需要在其他地区）"
                if "location is not supported" in res.text.lower()
                else ""
            )
            raise EmbeddingError(f"向量化服务返回 {res.status_code}{hint}: {res.text[:500]}")
        try:
            vectors = [e["values"] for e in res.json()["embeddings"]]
        except (ValueError, KeyError, TypeError) as e:
            raise EmbeddingError(f"向量化服务的返回无法解析：{res.text[:500]}") from e
        if len(vectors) != len(texts):
            raise EmbeddingError(f"向量化服务返回了 {len(vectors)} 个向量，应为 {len(texts)} 个")
        return vectors


def open_embedder(settings: EmbeddingSettings) -> ClosableEmbedder:
    """The embedder of the service the deployment chose."""
    if settings.provider == "gemini":
        assert settings.dimensions is not None, "Gemini's settings always carry dimensions"
        return GeminiEmbedder(
            settings.api_key, settings.model, settings.dimensions, settings.base_url
        )
    return SiliconFlowEmbedder(settings.api_key, settings.model, settings.base_url)


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
