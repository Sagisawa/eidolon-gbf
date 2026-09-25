"""Test doubles for external services."""

from collections.abc import AsyncIterator, Sequence

from eidolon.llm import ChatMessage


class FakeLLM:
    """Records every prompt it receives and replies from a script.

    Each scripted reply is a list of text chunks, streamed in order, so tests can
    split the structured reply at awkward boundaries.
    """

    def __init__(self, *replies: Sequence[str]) -> None:
        self._replies = [list(r) for r in replies]
        self.prompts: list[list[ChatMessage]] = []

    async def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        self.prompts.append(list(messages))
        if not self._replies:
            raise AssertionError("FakeLLM ran out of scripted replies")
        for chunk in self._replies.pop(0):
            yield chunk
