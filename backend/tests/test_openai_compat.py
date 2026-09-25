"""The OpenAI-compatible Chat Completions adapter, against a recorded stream."""

import json

import httpx
import pytest

from eidolon.llm import ChatMessage
from eidolon.llm.openai_compat import LLMError, OpenAICompatLLM

RECORDED_STREAM = (
    'data: {"id":"c1","object":"chat.completion.chunk","choices":[{"index":0,'
    '"delta":{"role":"assistant","content":""},"finish_reason":null}]}\n\n'
    'data: {"id":"c1","object":"chat.completion.chunk","choices":[{"index":0,'
    '"delta":{"content":"<ja>ほわっ"},"finish_reason":null}]}\n\n'
    ": keep-alive\n\n"
    'data: {"id":"c1","object":"chat.completion.chunk","choices":[{"index":0,'
    '"delta":{"content":"</ja><zh>哇</zh>"},"finish_reason":null}]}\n\n'
    'data: {"id":"c1","object":"chat.completion.chunk","choices":[{"index":0,'
    '"delta":{},"finish_reason":"stop"}]}\n\n'
    'data: {"id":"c1","object":"chat.completion.chunk","choices":[],'
    '"usage":{"prompt_tokens":10,"completion_tokens":5}}\n\n'
    "data: [DONE]\n\n"
)


async def test_streams_content_deltas_and_sends_a_chat_completions_request():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200, text=RECORDED_STREAM, headers={"content-type": "text/event-stream"}
        )

    llm = OpenAICompatLLM(
        "https://llm.example/v1/", "sk-test", "some-model",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    chunks = [c async for c in llm.stream([ChatMessage("user", "你好")])]

    assert chunks == ["<ja>ほわっ", "</ja><zh>哇</zh>"]
    (request,) = requests
    assert str(request.url) == "https://llm.example/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer sk-test"
    assert json.loads(request.content) == {
        "model": "some-model",
        "stream": True,
        "messages": [{"role": "user", "content": "你好"}],
    }


async def test_error_status_is_raised_with_the_provider_message():
    llm = OpenAICompatLLM(
        "https://llm.example/v1", "sk-bad", "some-model",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(401, json={"error": {"message": "invalid api key"}})
            )
        ),
    )

    with pytest.raises(LLMError, match="401.*invalid api key"):
        [c async for c in llm.stream([ChatMessage("user", "你好")])]


async def test_error_sent_inside_the_stream_is_raised():
    stream = (
        'data: {"choices":[{"delta":{"content":"<ja>ほわ"}}]}\n\n'
        'data: {"error":{"message":"upstream overloaded"}}\n\n'
    )
    llm = OpenAICompatLLM(
        "https://llm.example/v1", "sk-test", "some-model",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, text=stream))
        ),
    )

    with pytest.raises(LLMError, match="upstream overloaded"):
        [c async for c in llm.stream([ChatMessage("user", "你好")])]
