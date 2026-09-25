"""The conversation engine: one conversation turn in, the character's reply out.

It knows nothing about voice. Given a conversation and the user's input text it
assembles the prompt, streams the chat model's structured reply as per-segment
deltas, and records both sides of the turn.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass

from eidolon.characters import CHARACTERS
from eidolon.llm import ChatLLM, ChatMessage
from eidolon.reply_format import FORMAT_INSTRUCTIONS, ReplyParser, SegmentDelta
from eidolon.store import Conversation, Message, Store


@dataclass(frozen=True)
class TurnDone:
    message: Message


TurnEvent = SegmentDelta | TurnDone


class ConversationEngine:
    def __init__(self, store: Store, chat_llm: ChatLLM) -> None:
        self._store = store
        self._llm = chat_llm

    async def turn(self, conversation: Conversation, text: str) -> AsyncIterator[TurnEvent]:
        history = self._store.list_messages(conversation.id)
        self._store.add_user_message(conversation.id, text)
        prompt = self._prompt(conversation, history, text)

        parser = ReplyParser()
        async for chunk in self._llm.stream(prompt):
            for delta in parser.feed(chunk):
                yield delta
        for delta in parser.finish():
            yield delta

        reply = self._store.add_character_message(conversation.id, parser.segments)
        yield TurnDone(reply)

    def _prompt(
        self, conversation: Conversation, history: list[Message], text: str
    ) -> list[ChatMessage]:
        character = CHARACTERS[conversation.character_id]
        prompt = [ChatMessage("system", f"{character.sheet}\n\n{FORMAT_INSTRUCTIONS}")]
        for message in history:
            if message.role == "user":
                prompt.append(ChatMessage("user", message.text or ""))
            else:
                reply = "".join(f"<ja>{s.ja}</ja><zh>{s.zh}</zh>" for s in message.segments)
                prompt.append(ChatMessage("assistant", reply))
        prompt.append(ChatMessage("user", text))
        return prompt
