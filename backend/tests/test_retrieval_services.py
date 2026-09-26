"""The retrieval services' own protocols: SiliconFlow's rerank endpoint, and Jev through
Vercel AI Gateway's evaluation endpoint."""

import json
from collections.abc import Callable

import httpx
import pytest

from eidolon.characters import Character
from eidolon.rerank import RerankError, SiliconFlowReranker
from eidolon.retrieval import JevJudge, JudgeError
from eidolon.store import Message

Handler = Callable[[httpx.Request], httpx.Response]


def client(handle: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handle))


def recording(requests: list[dict], response: httpx.Response) -> Handler:
    def handle(request: httpx.Request) -> httpx.Response:
        requests.append({"url": str(request.url), "auth": request.headers["Authorization"],
                         **json.loads(request.content)})
        return response

    return handle


async def test_reranker_returns_the_best_documents_first():
    requests: list[dict] = []
    # Not sorted on purpose: the order comes from the scores.
    results = [{"index": 0, "relevance_score": 0.1}, {"index": 2, "relevance_score": 0.9},
               {"index": 1, "relevance_score": 0.5}]
    reranker = SiliconFlowReranker(
        "sk-test", "Qwen/Qwen3-Reranker-0.6B", "http://sf.test/v1",
        client(recording(requests, httpx.Response(200, json={"results": results}))),
    )

    best = await reranker.rerank("鳩の話", ["a", "b", "c"], top_n=2)

    assert best == [(2, 0.9), (1, 0.5)]
    [request] = requests
    assert request["url"] == "http://sf.test/v1/rerank"
    assert request["auth"] == "Bearer sk-test"
    assert (request["model"], request["query"], request["documents"], request["top_n"]) == (
        "Qwen/Qwen3-Reranker-0.6B", "鳩の話", ["a", "b", "c"], 2
    )


@pytest.mark.parametrize(
    "response, error",
    [
        (httpx.Response(401, text="unauthorized"), "401"),
        (httpx.Response(200, json={"oops": []}), "无法解析"),
        (httpx.Response(200, json={"results": [{"index": 7, "relevance_score": 1}]}), "不存在"),
    ],
)
async def test_reranker_errors_are_reported(response: httpx.Response, error: str):
    reranker = SiliconFlowReranker("k", "m", "http://sf.test/v1", client(lambda _: response))

    with pytest.raises(RerankError, match=error):
        await reranker.rerank("q", ["a"], top_n=1)


MANO = Character("mano", "櫻木真乃", "", "voice", "sheet", None)


def message(role: str, text: str) -> Message:
    if role == "user":
        return Message(1, "user", text, None, None, "2026-09-25T00:00:00+00:00")
    return Message(2, "character", None, text, "", "2026-09-25T00:00:00+00:00")


def judge_answering(
    requests: list[dict], retrieve: float, recall: float = 0.01, about_producer: float = 0.02
) -> JevJudge:
    body = {
        "model": "jev",
        "answers": {
            "needs_retrieval": {"type": "boolean", "probability": retrieve},
            "recall": {"type": "boolean", "probability": recall},
            "about_producer": {"type": "boolean", "probability": about_producer},
        },
        "usage": {"inputTokens": 500, "outputTokens": 0},
    }
    return JevJudge(
        "gw-key", "jev", "http://gateway.test/v1",
        client(recording(requests, httpx.Response(200, json=body))),
    )


@pytest.mark.parametrize(
    "retrieve, recall, about_producer, expected",
    [
        (0.89, 0.03, 0.1, "references"),
        (0.5, 0.2, 0.1, "references"),
        (0.89, 0.03, 0.95, "references"),  # which carries memories too
        (0.21, 0.01, 0.1, "nothing"),
        (0.21, 0.01, 0.95, "memories"),
        (0.91, 0.96, 0.95, "recall"),
        (0.4, 0.5, 0.1, "recall"),
    ],
)
async def test_jev_answers_what_the_turn_needs(
    retrieve: float, recall: float, about_producer: float, expected: str
):
    requests: list[dict] = []

    judge = judge_answering(requests, retrieve, recall, about_producer)
    assert await judge.judge(MANO, [], "那次比赛") == expected
    [request] = requests  # all questions in one call
    assert request["url"] == "http://gateway.test/v1/evaluate"
    assert request["auth"] == "Bearer gw-key"
    assert request["model"] == "jev"
    assert request["questions"]["needs_retrieval"]["type"] == "boolean"
    assert request["questions"]["recall"]["type"] == "boolean"
    assert request["questions"]["about_producer"]["type"] == "boolean"


async def test_jev_sees_the_latest_messages_and_what_was_just_said():
    requests: list[dict] = []
    history = [message("user", f"old {i}") for i in range(5)] + [message("character", "ほわっ")]

    await judge_answering(requests, 0.1).judge(MANO, history, "那次比赛")

    state = requests[0]["state"]
    assert state["角色"] == "櫻木真乃"
    assert state["上文"][-1] == "櫻木真乃：ほわっ" and "制作人：old 4" in state["上文"]
    assert "制作人：old 1" not in state["上文"]
    assert state["制作人最新的一句话"] == "那次比赛"


async def test_jev_errors_are_reported():
    judge = JevJudge("k", "jev", "http://gateway.test/v1",
                     client(lambda _: httpx.Response(503, text="busy")))

    with pytest.raises(JudgeError, match="503"):
        await judge.judge(MANO, [], "在吗")


async def test_unparsable_jev_answers_are_reported():
    judge = JevJudge("k", "jev", "http://gateway.test/v1",
                     client(lambda _: httpx.Response(200, json={"answers": {}})))

    with pytest.raises(JudgeError, match="无法解析"):
        await judge.judge(MANO, [], "在吗")
