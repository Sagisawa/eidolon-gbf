"""The SiliconFlow embedder speaks the OpenAI-compatible embeddings protocol."""

import json

import httpx
import pytest

from eidolon.embedding import EmbeddingError, SiliconFlowEmbedder


def embedder(requests: list[dict], status: int = 200) -> SiliconFlowEmbedder:
    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append({"auth": request.headers["Authorization"], **body})
        # Out of order on purpose: the index says which input each vector belongs to.
        data = [{"index": i, "embedding": [float(i), 1.0]} for i in range(len(body["input"]))]
        return httpx.Response(status, json={"data": data[::-1]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    return SiliconFlowEmbedder("sk-test", "Qwen/Qwen3-Embedding-0.6B", "http://sf.test/v1", client)


async def test_documents_are_embedded_in_batches_and_kept_in_order():
    requests: list[dict] = []

    vectors = await embedder(requests).embed_documents([f"doc {i}" for i in range(20)])

    assert [len(r["input"]) for r in requests] == [16, 4]
    assert requests[0]["model"] == "Qwen/Qwen3-Embedding-0.6B"
    assert requests[0]["auth"] == "Bearer sk-test"
    assert requests[0]["input"][0] == "doc 0"
    assert [v[0] for v in vectors] == [float(i) for i in range(16)] + [0.0, 1.0, 2.0, 3.0]


async def test_queries_carry_an_instruction_documents_do_not():
    requests: list[dict] = []

    await embedder(requests).embed_query("那次拍写真集是怎么回事")

    assert requests[0]["input"][0].startswith("Instruct: ")
    assert requests[0]["input"][0].endswith("Query: 那次拍写真集是怎么回事")


async def test_a_service_error_is_reported():
    with pytest.raises(EmbeddingError, match="401"):
        await embedder([], status=401).embed_documents(["doc"])


async def test_an_unreachable_service_is_reported():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    embedder = SiliconFlowEmbedder("sk-test", "m", "http://sf.test/v1", client)

    with pytest.raises(EmbeddingError, match="无法连接"):
        await embedder.embed_query("在吗")
