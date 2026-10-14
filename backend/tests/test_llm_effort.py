"""A model's reasoning effort and extra request body (ADR-0019): each protocol sends the
effort as it writes it, nothing when it is unset; the extra body is merged in last, deep,
so it may override what the adapter wrote, but may not touch what makes the request."""

import json

import httpx
import pytest

from eidolon.config import (
    REASONING_EFFORTS,
    LLMProtocol,
    LLMSettings,
    ReasoningEffort,
    checked_extra_body,
)
from eidolon.llm import ChatMessage, Tool
from eidolon.llm.providers import open_llm
from tests.test_llm_protocols import recorded

STREAMS: dict[LLMProtocol, str] = {
    "chat-completions": 'data: {"choices":[{"delta":{"content":"はい"}}]}\n\n',
    "responses": recorded("responses_text"),
    "anthropic": recorded("anthropic_text"),
}

PING = Tool("ping", "检查", {"type": "object", "properties": {}})

# What the adapters write besides the prompt, model and stream, for each protocol.
UNSET: dict[LLMProtocol, dict] = {
    "chat-completions": {"stream_options": {"include_usage": True}},
    "responses": {"store": False},
    "anthropic": {"max_tokens": 16384},
}


async def sent(
    protocol: LLMProtocol,
    effort: ReasoningEffort | None = None,
    extra_body: dict | None = None,
    tools: list[Tool] | None = None,
) -> dict:
    """The body of the request a model with these settings sends."""
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, text=STREAMS[protocol])

    settings = LLMSettings(
        "https://llm.example/v1", "k", "m", protocol,
        reasoning_effort=effort, extra_body=extra_body,
    )
    llm = open_llm(settings, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    async for _ in llm.stream([ChatMessage("user", "你好")], tools or []):
        pass
    await llm.aclose()
    return bodies[0]


def written(protocol: LLMProtocol, body: dict) -> dict:
    """What `body` carries beyond the prompt, the model and that it streams."""
    left_out = {"model", "stream", "messages", "input", "instructions", "system"}
    return {k: v for k, v in body.items() if k not in left_out}


@pytest.mark.parametrize("protocol", UNSET)
async def test_an_unset_effort_sends_nothing_of_it(protocol: LLMProtocol):
    assert written(protocol, await sent(protocol)) == UNSET[protocol]


EFFORTS = [e for e in REASONING_EFFORTS if e != "none"]


@pytest.mark.parametrize("effort", REASONING_EFFORTS)
async def test_chat_completions_sends_the_effort_as_reasoning_effort(effort: ReasoningEffort):
    body = await sent("chat-completions", effort)

    assert written("chat-completions", body) == UNSET["chat-completions"] | {
        "reasoning_effort": effort
    }


@pytest.mark.parametrize("effort", REASONING_EFFORTS)
async def test_responses_sends_the_effort_and_asks_for_the_encrypted_reasoning(
    effort: ReasoningEffort,
):
    body = await sent("responses", effort)

    # With `store` off, the encrypted reasoning is all a tool round can send back of it;
    # with thinking off there is none to ask for.
    include = {} if effort == "none" else {"include": ["reasoning.encrypted_content"]}
    assert written("responses", body) == UNSET["responses"] | {
        "reasoning": {"effort": effort}
    } | include


async def test_anthropic_turns_thinking_off_for_none():
    body = await sent("anthropic", "none")

    assert written("anthropic", body) == UNSET["anthropic"] | {"thinking": {"type": "disabled"}}


@pytest.mark.parametrize("effort", [e for e in EFFORTS if e != "minimal"])
async def test_anthropic_thinks_adaptively_at_the_effort_without_showing_it(
    effort: ReasoningEffort,
):
    body = await sent("anthropic", effort)

    assert written("anthropic", body) == UNSET["anthropic"] | {
        "thinking": {"type": "adaptive", "display": "omitted"},
        "output_config": {"effort": effort},
    }


async def test_the_extra_body_is_merged_in_deep_overriding_what_the_adapter_wrote():
    extra = {
        "thinking": {"type": "enabled", "budget_tokens": 2048},
        "output_config": {"format": "text"},
        "top_k": 5,
    }

    body = await sent("anthropic", "high", extra, tools=[PING])

    assert body["thinking"] == {"type": "enabled", "budget_tokens": 2048, "display": "omitted"}
    assert body["output_config"] == {"effort": "high", "format": "text"}
    assert body["top_k"] == 5
    assert [t["name"] for t in body["tools"]] == ["ping"]


@pytest.mark.parametrize("protocol", UNSET)
async def test_a_value_that_is_not_an_object_replaces_the_adapters(protocol: LLMProtocol):
    extra = {"reasoning_effort": None, "reasoning": "off", "thinking": None, "enable_thinking": False}

    body = await sent(protocol, "low", extra)

    for key, value in extra.items():
        assert body[key] == value


async def test_the_extra_body_is_not_changed_by_the_requests_it_goes_into():
    extra = {"reasoning": {"summary": "auto"}}

    await sent("responses", "high", extra)
    await sent("responses", "low", extra)

    assert extra == {"reasoning": {"summary": "auto"}}


# The extra body, checked the same wherever it comes from.

@pytest.mark.parametrize(
    "extra",
    [
        {"enable_thinking": False},
        {"thinking": {"type": "disabled"}},
        {"reasoning_effort": "high", "reasoning": {"effort": "low"}},
        {"output_config": {"effort": "max"}, "include": []},
        {},
    ],
)
def test_an_extra_body_of_the_thinking_keys_and_others_is_taken(extra: dict):
    assert checked_extra_body(extra) == extra


@pytest.mark.parametrize("extra", [[1, 2], "enable_thinking", 3, None])
def test_an_extra_body_that_is_not_an_object_is_refused(extra: object):
    with pytest.raises(ValueError, match="JSON 对象"):
        checked_extra_body(extra)


@pytest.mark.parametrize(
    "key",
    ["model", "stream", "stream_options", "messages", "input", "instructions", "system",
     "tools", "tool_choice"],
)
def test_an_extra_body_that_would_break_the_request_is_refused_naming_the_key(key: str):
    with pytest.raises(ValueError, match=f"「{key}」"):
        checked_extra_body({"enable_thinking": False, key: "x"})
