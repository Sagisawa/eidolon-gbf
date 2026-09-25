"""The conversation engine: one conversation turn in, the character's reply out.

It knows nothing about voice. Given a conversation and the user's input text it
retrieves what the turn calls for, assembles the prompt, streams the chat model's structured reply as per-segment
deltas, and records both sides of the turn once the reply is complete. A turn
that fails part-way leaves no record.
"""

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from eidolon.characters import Character
from eidolon.llm import ChatLLM, ChatMessage
from eidolon.producer import effective_timezone, producer_prompt
from eidolon.reply_format import FORMAT_INSTRUCTIONS, ReplyParser, SegmentDelta, format_reply
from eidolon.retrieval import Reference, Retrieval, references_prompt
from eidolon.store import Conversation, Message, Store

MAX_INPUT_LENGTH = 2000
"""The longest thing a user can say in one turn, typed or spoken, in characters."""


@dataclass(frozen=True)
class TurnDone:
    message: Message


TurnEvent = SegmentDelta | TurnDone

Clock = Callable[[], datetime]
"""The current time, timezone-aware."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


class EmptyReply(RuntimeError):
    pass


class ConversationEngine:
    def __init__(
        self,
        store: Store,
        chat_llm: ChatLLM,
        characters: dict[str, Character],
        clock: Clock | None = None,
        retrieval: Retrieval | None = None,
    ) -> None:
        """Without `retrieval`, turns carry no story or character facts."""
        self._store = store
        self._characters = characters
        self._llm = chat_llm
        self._clock = clock or _utc_now
        self._retrieval = retrieval

    async def turn(
        self, conversation: Conversation, text: str, device_timezone: str | None = None
    ) -> AsyncIterator[TurnEvent]:
        """Take one turn. `device_timezone` is the time zone the user's device reports,
        used unless the producer profile sets one."""
        character = self._characters[conversation.character_id]
        history = self._store.list_messages(conversation.id)
        references = (
            await self._retrieval.references(character, history, text) if self._retrieval else []
        )
        prompt = self._prompt(conversation, character, history, references, text, device_timezone)

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
        self,
        conversation: Conversation,
        character: Character,
        history: list[Message],
        references: list[Reference],
        text: str,
        device_timezone: str | None,
    ) -> list[ChatMessage]:
        profile = self._store.get_profile(conversation.user_id)
        about_producer = producer_prompt(
            profile, self._clock(), effective_timezone(profile, device_timezone)
        )
        sections = [character.sheet, about_producer]
        if references:
            sections.append(references_prompt(references))
        system = "\n\n".join([*sections, FORMAT_INSTRUCTIONS])
        prompt = [ChatMessage("system", system)]
        for message in history:
            if message.role == "user":
                prompt.append(ChatMessage("user", message.text or ""))
            else:
                prompt.append(ChatMessage("assistant", format_reply(message.segments)))
        prompt.append(ChatMessage("user", text))
        return prompt
