"""The Gemini embedder speaks Google's native `batchEmbedContents`: one request item per
text, told apart from queries by prefixes, since Gemini Embedding 2 takes no task type."""

import json

import httpx
import pytest

from eidolon.embedding import Document, EmbeddingError, GeminiEmbedder


def embedder(
    requests: list[dict], response: httpx.Response | None = None, dimensions: int = 1536
) -> GeminiEmbedder:
    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append({"url": str(request.url), "key": request.headers["x-goog-api-key"], **body})
        if response is not None:
            return response
        # Each vector says which text it came from: its first value is the text's position.
        embeddings = [{"values": [float(i), 1.0]} for i in range(len(body["requests"]))]
        return httpx.Response(200, json={"embeddings": embeddings})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    return GeminiEmbedder(
        "gm-key", "gemini-embedding-2", dimensions, "http://gemini.test/v1beta", client
    )


async def test_each_document_is_its_own_request_item_with_its_title():
    requests: list[dict] = []

    vectors = await embedder(requests).embed_documents([
        Document("真乃：ほわっ", "W.I.N.G.編「公園の歌声」"),
        Document("制作人养了一只猫"),
    ])

    [request] = requests
    assert request["url"] == "http://gemini.test/v1beta/models/gemini-embedding-2:batchEmbedContents"
    assert request["key"] == "gm-key"
    assert request["requests"] == [
        {
            "model": "models/gemini-embedding-2",
            "content": {"parts": [{"text": "title: W.I.N.G.編「公園の歌声」 | text: 真乃：ほわっ"}]},
            "output_dimensionality": 1536,
        },
        {
            "model": "models/gemini-embedding-2",
            "content": {"parts": [{"text": "title: none | text: 制作人养了一只猫"}]},
            "output_dimensionality": 1536,
        },
    ]
    assert vectors == [[0.0, 1.0], [1.0, 1.0]]


async def test_queries_carry_the_search_task_prefix():
    requests: list[dict] = []

    await embedder(requests, dimensions=768).embed_query("那次拍写真集是怎么回事")

    [item] = requests[0]["requests"]
    assert item["content"]["parts"] == [{"text": "task: search result | query: 那次拍写真集是怎么回事"}]
    assert item["output_dimensionality"] == 768


async def test_documents_are_embedded_in_batches_and_kept_in_order():
    requests: list[dict] = []

    vectors = await embedder(requests).embed_documents([Document(f"doc {i}") for i in range(250)])

    assert [len(r["requests"]) for r in requests] == [100, 100, 50]
    assert [v[0] for v in vectors] == [float(i % 100) for i in range(250)]


def test_the_stored_model_carries_the_dimensions():
    assert embedder([], dimensions=768).model == "gemini-embedding-2@768"


@pytest.mark.parametrize(
    "response, error",
    [
        (httpx.Response(403, text="PERMISSION_DENIED"), "403"),
        (httpx.Response(200, json={"oops": []}), "无法解析"),
        (httpx.Response(200, json={"embeddings": [{"values": [1.0]}] * 2}), "2 个向量"),
    ],
)
async def test_service_errors_are_reported(response: httpx.Response, error: str):
    with pytest.raises(EmbeddingError, match=error):
        await embedder([], response).embed_documents([Document("doc")])


async def test_an_unsupported_region_is_explained():
    refused = httpx.Response(
        400,
        json={"error": {"code": 400, "status": "FAILED_PRECONDITION",
                        "message": "User location is not supported for the API use."}},
    )

    with pytest.raises(EmbeddingError, match="不对中国大陆、香港、澳门开放"):
        await embedder([], refused).embed_query("在吗")


async def test_an_unreachable_service_is_reported():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    gemini = GeminiEmbedder("k", "gemini-embedding-2", 1536, "http://gemini.test/v1beta", client)

    with pytest.raises(EmbeddingError, match="无法连接"):
        await gemini.embed_query("在吗")
