"""The conversation engine: one conversation turn in, the character's reply out.

It knows nothing about voice. Given a conversation and the user's input text it
retrieves what the turn calls for, assembles the prompt, streams the chat model's structured reply as per-segment
deltas, and records both sides of the turn once the reply is complete. A turn
that fails part-way leaves no record.

When retrieval is available the chat model is offered the recall-story tool, unless
the turn already recalled an episode. Its calls are answered and the model asked
again, once at most since every round costs the model's time to first token; whatever
it says along the way is part of the reply, and only the reply is recorded.

With memory, the user's memories that retrieval finds go into the prompt, and once a
turn is recorded the background model writes down what the user revealed in it.
"""

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from eidolon.characters import Character
from eidolon.llm import ChatLLM, ChatMessage, Tool, ToolCall
from eidolon.memory import MemoryWriter, memories_prompt
from eidolon.producer import effective_timezone, producer_prompt
from eidolon.reply_format import FORMAT_INSTRUCTIONS, ReplyParser, SegmentDelta, format_reply
from eidolon.retrieval import RECALL_STORY_TOOL, Retrieval, Retrieved
from eidolon.store import Conversation, Message, Store

MAX_INPUT_LENGTH = 2000
"""The longest thing a user can say in one turn, typed or spoken, in characters."""
MAX_TOOL_ROUNDS = 1
"""How many rounds of tool calls the chat model gets in one turn; after that it has to answer."""


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
        memory: MemoryWriter | None = None,
    ) -> None:
        """Without `retrieval`, turns carry no story, character facts or memories; without
        `memory`, nothing is written down."""
        self._store = store
        self._characters = characters
        self._llm = chat_llm
        self._clock = clock or _utc_now
        self._retrieval = retrieval
        self._memory = memory
        self._names = {c.id: c.name for c in characters.values()}

    async def turn(
        self, conversation: Conversation, text: str, device_timezone: str | None = None
    ) -> AsyncIterator[TurnEvent]:
        """Take one turn. `device_timezone` is the time zone the user's device reports,
        used unless the producer profile sets one."""
        character = self._characters[conversation.character_id]
        history = self._store.list_messages(conversation.id)
        profile = self._store.get_profile(conversation.user_id)
        timezone = effective_timezone(profile, device_timezone)
        mark = self._memory.mark(conversation.user_id) if self._memory else 0
        if self._memory:
            await self._memory.settle(conversation.user_id)
        retrieved = (
            await self._retrieval.retrieve(character, conversation.user_id, history, text)
            if self._retrieval
            else Retrieved(None)
        )
        about_producer = producer_prompt(profile, self._clock(), timezone)
        prompt = self._prompt(character, about_producer, history, retrieved, text, timezone)

        tools: list[Tool] = (
            [RECALL_STORY_TOOL] if self._retrieval and not retrieved.recalled else []
        )
        parser = ReplyParser()
        for step in range(MAX_TOOL_ROUNDS + 1):
            offered = tools if step < MAX_TOOL_ROUNDS else []
            said = ""
            calls: list[ToolCall] = []
            async for item in self._llm.stream(prompt, offered):
                if isinstance(item, ToolCall):
                    calls.append(item)
                    continue
                said += item
                for delta in parser.feed(item):
                    yield delta
            for delta in parser.finish():
                yield delta
            if not calls or not offered:  # a call to a tool not offered goes unanswered
                break
            prompt = [*prompt, ChatMessage("assistant", said, tool_calls=tuple(calls))]
            for call in calls:
                result = await self._call_tool(character, call)
                prompt.append(ChatMessage("tool", result, tool_call_id=call.id))

        if not parser.segments:
            raise EmptyReply("对话模型没有返回任何内容")
        reply = self._store.add_turn(conversation.id, text, parser.segments)
        if self._memory:
            now = self._clock().astimezone(ZoneInfo(timezone))
            self._memory.remember(conversation, character, history, text, reply, now, mark)
        yield TurnDone(reply)

    async def _call_tool(self, character: Character, call: ToolCall) -> str:
        """The tool's result, or what went wrong, for the model to read."""
        if call.name != RECALL_STORY_TOOL.name or self._retrieval is None:
            return f"没有 {call.name} 这个工具。"
        query = (call.arguments or {}).get("query")
        if not isinstance(query, str) or not query.strip():
            return "调用参数有误：需要 query（要回顾的事，一句概括）。"
        return await self._retrieval.recall_story(character, query.strip())

    def _prompt(
        self,
        character: Character,
        about_producer: str,
        history: list[Message],
        retrieved: Retrieved,
        text: str,
        timezone: str,
    ) -> list[ChatMessage]:
        sections = [character.sheet, about_producer]
        if retrieved.memories:
            sections.append(memories_prompt(retrieved.memories, character, self._names, timezone))
        if retrieved.prompt:
            sections.append(retrieved.prompt)
        system = "\n\n".join([*sections, FORMAT_INSTRUCTIONS])
        prompt = [ChatMessage("system", system)]
        for message in history:
            if message.role == "user":
                prompt.append(ChatMessage("user", message.text or ""))
            else:
                prompt.append(ChatMessage("assistant", format_reply(message.segments)))
        prompt.append(ChatMessage("user", text))
        return prompt
