"""LLM providers: a single streaming chat interface with tool calling, one implementation
per protocol."""

from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class Tool:
    """A tool the model may call; `parameters` is a JSON Schema for its arguments."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] | None
    """None when the model's arguments were not a JSON object."""


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    """The calls an assistant message made."""
    tool_call_id: str | None = None
    """The call a tool message answers."""


class ChatLLM(Protocol):
    def stream(
        self, messages: Sequence[ChatMessage], tools: Sequence[Tool] = ()
    ) -> AsyncIterator[str | ToolCall]:
        """Stream the model's reply to `messages` as text chunks, then any tool calls it
        makes, each once complete."""
        ...

    async def aclose(self) -> None: ...


class LLMError(RuntimeError):
    """The model's service failed, refused the request, or replied in a way the adapter
    cannot read."""


def _no_hold() -> Callable[[], None]:
    return _let_go


def _let_go() -> None:
    pass


@dataclass(frozen=True)
class TurnLLMs:
    """The models one turn runs on: `chat` plays the character, `memory` writes down what
    the user revealed in it."""

    chat: ChatLLM
    memory: ChatLLM
    hold_memory: Callable[[], Callable[[], None]] = field(default=_no_hold, compare=False)
    """Holds on to `memory` past the end of the turn, for writing down after it, until
    the function it returns is called: the deployer's model may be replaced meanwhile
    (see `service_clients.Swappable`)."""
