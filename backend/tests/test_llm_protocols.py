"""The OpenAI Responses and Anthropic Messages adapters, against streams recorded from a real
service (deepseek-v4.1-flash, which also streams its reasoning: the adapters must skip it)."""

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from eidolon.llm import ChatLLM, ChatMessage, LLMError, Tool, ToolCall
from eidolon.llm.anthropic import AnthropicLLM
from eidolon.llm.responses import ResponsesLLM
from eidolon.reply_format import ReplyParser, Segment

RECORDINGS = Path(__file__).parent / "recordings"

RECALL = Tool(
    "recall_story",
    "回顾剧情",
    {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
)

Adapter = Callable[[httpx.AsyncClient], ChatLLM]
ADAPTERS: dict[str, Adapter] = {
    "responses": lambda client: ResponsesLLM(
        "https://llm.example/v1/", "sk-test", "some-model", client=client
    ),
    "anthropic": lambda client: AnthropicLLM(
        "https://llm.example/v1/", "sk-test", "some-model", client=client
    ),
}


def recorded(name: str) -> str:
    return (RECORDINGS / f"{name}.sse").read_text(encoding="utf-8")


def serving(
    body: str | Callable[[httpx.Request], httpx.Response], requests: list[httpx.Request]
) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if callable(body):
            return body(request)
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def collect(llm: ChatLLM, messages: list[ChatMessage], tools: list[Tool] = []) -> list:
    return [item async for item in llm.stream(messages, tools)]


@pytest.mark.parametrize("protocol", ADAPTERS)
async def test_the_structured_reply_streams_through_leaving_the_reasoning_out(protocol: str):
    llm = ADAPTERS[protocol](serving(recorded(f"{protocol}_text"), []))

    items = await collect(llm, [ChatMessage("user", "你好")])

    assert all(isinstance(i, str) for i in items)
    assert len(items) > 3  # streamed in pieces, not all at once
    parser = ReplyParser()
    for item in items:
        parser.feed(item)
    parser.finish()
    expected = {
        "responses": [
            Segment("こんにちは。", "你好。"),
            Segment("今日はどのようにお手伝いしましょうか。", "今天我能怎么帮你？"),
        ],
        "anthropic": [Segment("こんにちは。", "你好。")],
    }
    assert parser.segments == expected[protocol]


@pytest.mark.parametrize("protocol", ADAPTERS)
async def test_a_recorded_tool_call_is_assembled(protocol: str):
    llm = ADAPTERS[protocol](serving(recorded(f"{protocol}_tool"), []))

    items = await collect(llm, [ChatMessage("user", "那次拍写真集")], [RECALL])

    call_ids = {
        "responses": "call_00_AB1TVlVKx4vdJplfOG716557",
        "anthropic": "call_00_T2lkblEVfvBy77TaH2jI2468",
    }
    assert items == [ToolCall(call_ids[protocol], "recall_story", {"query": "拍写真集"})]


PROMPT = [
    ChatMessage("system", "你是櫻木真乃。"),
    ChatMessage("user", "你好"),
    ChatMessage("assistant", "<ja>ほわっ</ja><zh>哇</zh>"),
    ChatMessage("user", "那次拍写真集"),
    ChatMessage(
        "assistant",
        "我查一下",
        tool_calls=(
            ToolCall("call_a", "recall_story", {"query": "写真集"}),
            ToolCall("call_b", "recall_story", None),
        ),
    ),
    ChatMessage("tool", "## 剧情……", tool_call_id="call_a"),
    ChatMessage("tool", "调用参数有误", tool_call_id="call_b"),
]


async def test_responses_request_carries_the_prompt_tools_and_tool_round_trip():
    requests: list[httpx.Request] = []
    llm = ADAPTERS["responses"](serving(recorded("responses_text"), requests))

    await collect(llm, PROMPT, [RECALL])

    (request,) = requests
    assert str(request.url) == "https://llm.example/v1/responses"
    assert request.headers["authorization"] == "Bearer sk-test"
    assert json.loads(request.content) == {
        "model": "some-model",
        "stream": True,
        "store": False,
        "instructions": "你是櫻木真乃。",
        "input": [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "<ja>ほわっ</ja><zh>哇</zh>"},
            {"role": "user", "content": "那次拍写真集"},
            {"role": "assistant", "content": "我查一下"},
            {
                "type": "function_call",
                "call_id": "call_a",
                "name": "recall_story",
                "arguments": '{"query": "写真集"}',
            },
            {
                "type": "function_call",
                "call_id": "call_b",
                "name": "recall_story",
                "arguments": "{}",
            },
            {"type": "function_call_output", "call_id": "call_a", "output": "## 剧情……"},
            {"type": "function_call_output", "call_id": "call_b", "output": "调用参数有误"},
        ],
        "tools": [
            {
                "type": "function",
                "name": "recall_story",
                "description": "回顾剧情",
                "parameters": RECALL.parameters,
            }
        ],
    }


async def test_anthropic_request_carries_the_prompt_tools_and_tool_round_trip():
    requests: list[httpx.Request] = []
    llm = ADAPTERS["anthropic"](serving(recorded("anthropic_text"), requests))

    await collect(llm, PROMPT, [RECALL])

    (request,) = requests
    assert str(request.url) == "https://llm.example/v1/messages"
    assert request.headers["x-api-key"] == "sk-test"
    assert request.headers["anthropic-version"] == "2023-06-01"
    body = json.loads(request.content)
    assert body == {
        "model": "some-model",
        "stream": True,
        "max_tokens": body["max_tokens"],
        "system": "你是櫻木真乃。",
        "messages": [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "<ja>ほわっ</ja><zh>哇</zh>"},
            {"role": "user", "content": "那次拍写真集"},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "我查一下"},
                    {
                        "type": "tool_use",
                        "id": "call_a",
                        "name": "recall_story",
                        "input": {"query": "写真集"},
                    },
                    {"type": "tool_use", "id": "call_b", "name": "recall_story", "input": {}},
                ],
            },
            {  # results of one round go back together, in one user message
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "call_a", "content": "## 剧情……"},
                    {"type": "tool_result", "tool_use_id": "call_b", "content": "调用参数有误"},
                ],
            },
        ],
        "tools": [
            {"name": "recall_story", "description": "回顾剧情", "input_schema": RECALL.parameters}
        ],
    }
    assert body["max_tokens"] >= 4096  # Anthropic requires one; long drafts need room


async def test_anthropic_max_tokens_can_be_configured():
    requests: list[httpx.Request] = []
    llm = AnthropicLLM(
        "https://llm.example/v1", "sk-test", "some-model",
        client=serving(recorded("anthropic_text"), requests), max_tokens=2000,
    )

    await collect(llm, [ChatMessage("user", "你好")])

    assert json.loads(requests[0].content)["max_tokens"] == 2000


async def test_anthropic_system_messages_are_joined_and_an_empty_assistant_text_is_left_out():
    requests: list[httpx.Request] = []
    llm = ADAPTERS["anthropic"](serving(recorded("anthropic_text"), requests))

    await collect(
        llm,
        [
            ChatMessage("system", "甲"),
            ChatMessage("system", "乙"),
            ChatMessage("user", "你好"),
            ChatMessage("assistant", "", tool_calls=(ToolCall("c", "recall_story", {}),)),
            ChatMessage("tool", "结果", tool_call_id="c"),
        ],
        [RECALL],
    )

    body = json.loads(requests[0].content)
    assert body["system"] == "甲\n\n乙"
    assert body["messages"][1]["content"] == [
        {"type": "tool_use", "id": "c", "name": "recall_story", "input": {}}
    ]


@pytest.mark.parametrize("protocol", ADAPTERS)
async def test_error_status_is_raised_with_the_provider_message(protocol: str):
    llm = ADAPTERS[protocol](
        serving(lambda _: httpx.Response(401, json={"error": {"message": "invalid api key"}}), [])
    )

    with pytest.raises(LLMError, match="401.*invalid api key"):
        await collect(llm, [ChatMessage("user", "你好")])


ERROR_IN_STREAM = {
    "responses": (
        'event: response.output_text.delta\n'
        'data: {"type":"response.output_text.delta","delta":"<ja>ほわ"}\n\n'
        'event: error\n'
        'data: {"type":"error","code":"server_error","message":"upstream overloaded"}\n\n'
    ),
    "anthropic": (
        'event: content_block_delta\n'
        'data: {"type":"content_block_delta","index":0,'
        '"delta":{"type":"text_delta","text":"<ja>ほわ"}}\n\n'
        'event: error\n'
        'data: {"type":"error","error":{"type":"overloaded_error",'
        '"message":"upstream overloaded"}}\n\n'
    ),
}


@pytest.mark.parametrize("protocol", ADAPTERS)
async def test_error_sent_inside_the_stream_is_raised(protocol: str):
    llm = ADAPTERS[protocol](serving(ERROR_IN_STREAM[protocol], []))

    with pytest.raises(LLMError, match="upstream overloaded"):
        await collect(llm, [ChatMessage("user", "你好")])


async def test_a_failed_response_is_raised():
    stream = (
        'event: response.failed\n'
        'data: {"type":"response.failed","response":{"status":"failed",'
        '"error":{"code":"server_error","message":"the model crashed"}}}\n\n'
    )
    llm = ADAPTERS["responses"](serving(stream, []))

    with pytest.raises(LLMError, match="the model crashed"):
        await collect(llm, [ChatMessage("user", "你好")])


NOT_STREAMED = {
    "responses": {"id": "r1", "object": "response", "output": []},
    "anthropic": {"id": "m1", "type": "message", "content": [{"type": "text", "text": "hi"}]},
}


@pytest.mark.parametrize("protocol", ADAPTERS)
async def test_a_reply_that_is_not_streamed_is_an_error(protocol: str):
    llm = ADAPTERS[protocol](
        serving(lambda _: httpx.Response(200, json=NOT_STREAMED[protocol]), [])
    )

    with pytest.raises(LLMError, match="流式"):
        await collect(llm, [ChatMessage("user", "你好")])


@pytest.mark.parametrize("protocol", ADAPTERS)
async def test_tool_call_arguments_that_are_not_json_are_passed_on_as_malformed(protocol: str):
    stream = {
        "responses": (
            'data: {"type":"response.output_item.added","output_index":0,"item":'
            '{"type":"function_call","call_id":"call_x","name":"recall_story","arguments":""}}\n\n'
            'data: {"type":"response.function_call_arguments.delta","output_index":0,'
            '"delta":"{\\"query\\": "}\n\n'
            'data: {"type":"response.completed","response":{"status":"completed"}}\n\n'
        ),
        "anthropic": (
            'data: {"type":"content_block_start","index":0,"content_block":'
            '{"type":"tool_use","id":"call_x","name":"recall_story","input":{}}}\n\n'
            'data: {"type":"content_block_delta","index":0,'
            '"delta":{"type":"input_json_delta","partial_json":"{\\"query\\": "}}\n\n'
            'data: {"type":"message_stop"}\n\n'
        ),
    }[protocol]
    llm = ADAPTERS[protocol](serving(stream, []))

    items = await collect(llm, [ChatMessage("user", "你好")], [RECALL])

    assert items == [ToolCall("call_x", "recall_story", None)]
