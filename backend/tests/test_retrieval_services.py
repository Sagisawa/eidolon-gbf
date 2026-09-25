"""The retrieval services' own protocols: SiliconFlow's rerank endpoint, and Jev through
Vercel AI Gateway's Chat Completions endpoint."""

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

    assert best == [2, 1]
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


def judge_answering(requests: list[dict], answer: str | None) -> JevJudge:
    body = {"choices": [{"message": {"role": "assistant", "content": answer}}]}
    return JevJudge(
        "gw-key", "jev", "http://gateway.test/v1",
        client(recording(requests, httpx.Response(200, json=body))),
    )


@pytest.mark.parametrize("answer, expected", [("YES", True), ("yes.", True), ("NO", False), (None, False)])
async def test_jev_answers_whether_to_retrieve(answer: str | None, expected: bool):
    requests: list[dict] = []

    assert await judge_answering(requests, answer).needs_retrieval(MANO, [], "那次比赛") is expected
    [request] = requests
    assert request["url"] == "http://gateway.test/v1/chat/completions"
    assert request["auth"] == "Bearer gw-key"
    assert request["model"] == "jev"


async def test_jev_sees_the_latest_messages_and_what_was_just_said():
    requests: list[dict] = []
    history = [message("user", f"old {i}") for i in range(5)] + [message("character", "ほわっ")]

    await judge_answering(requests, "NO").needs_retrieval(MANO, history, "那次比赛")

    prompt = requests[0]["messages"][-1]["content"]
    assert "櫻木真乃：ほわっ" in prompt and "制作人：old 4" in prompt
    assert "old 1" not in prompt
    assert prompt.endswith("那次比赛")


async def test_jev_errors_are_reported():
    judge = JevJudge("k", "jev", "http://gateway.test/v1",
                     client(lambda _: httpx.Response(503, text="busy")))

    with pytest.raises(JudgeError, match="503"):
        await judge.needs_retrieval(MANO, [], "在吗")
