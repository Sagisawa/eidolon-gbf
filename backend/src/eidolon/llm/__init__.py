"""LLM providers: a single streaming chat interface, one implementation per protocol."""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


class ChatLLM(Protocol):
    def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        """Stream the model's reply to `messages` as text chunks."""
        ...
