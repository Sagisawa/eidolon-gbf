"""The conversation engine: one conversation turn in, the character's reply out.

It knows nothing about voice. Given a conversation and the user's input text it
assembles the prompt, streams the chat model's structured reply as per-segment
deltas, and records both sides of the turn once the reply is complete. A turn
that fails part-way leaves no record.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass

from eidolon.characters import Character
from eidolon.llm import ChatLLM, ChatMessage
from eidolon.reply_format import FORMAT_INSTRUCTIONS, ReplyParser, SegmentDelta, format_reply
from eidolon.store import Conversation, Message, Store

MAX_INPUT_LENGTH = 2000
"""The longest thing a user can say in one turn, typed or spoken, in characters."""


@dataclass(frozen=True)
class TurnDone:
    message: Message


TurnEvent = SegmentDelta | TurnDone


class EmptyReply(RuntimeError):
    pass


class ConversationEngine:
    def __init__(
        self, store: Store, chat_llm: ChatLLM, characters: dict[str, Character]
    ) -> None:
        self._store = store
        self._characters = characters
        self._llm = chat_llm

    async def turn(self, conversation: Conversation, text: str) -> AsyncIterator[TurnEvent]:
        history = self._store.list_messages(conversation.id)
        prompt = self._prompt(conversation, history, text)

        parser = ReplyParser()
        async for chunk in self._llm.stream(prompt):
            for delta in parser.feed(chunk):
                yield delta
        for delta in parser.finish():
            yield delta

        if not parser.segments:
            raise EmptyReply("对话模型没有返回任何内容")
        reply = self._store.add_turn(conversation.id, text, parser.segments)
        yield TurnDone(reply)

    def _prompt(
        self, conversation: Conversation, history: list[Message], text: str
    ) -> list[ChatMessage]:
        character = self._characters[conversation.character_id]
        prompt = [ChatMessage("system", f"{character.sheet}\n\n{FORMAT_INSTRUCTIONS}")]
        for message in history:
            if message.role == "user":
                prompt.append(ChatMessage("user", message.text or ""))
            else:
                prompt.append(ChatMessage("assistant", format_reply(message.segments)))
        prompt.append(ChatMessage("user", text))
        return prompt
