"""The conversation engine: one conversation turn in, the character's reply out.

It knows nothing about voice. Given a conversation and the user's input text it
retrieves what the turn calls for, assembles the prompt, streams the chat model's structured reply as per-segment
deltas, and records both sides of the turn once the reply is complete.

Every turn, typed or spoken, speaks the same protocol: `user` (the input as taken up),
then any `delta`s, then `done` or `error`. Input that is blank or too long is rejected
before the model is asked; a turn that is rejected or fails part-way leaves no record,
and what went wrong stays in the server log.

When retrieval is available the chat model is offered the recall-story tool, unless
the turn already recalled an episode. Its calls are answered and the model asked
again, once at most since every round costs the model's time to first token; whatever
it says along the way is part of the reply, and only the reply is recorded.

With memory, the user's memories that retrieval finds go into the prompt, and once a
turn is recorded the background model writes down what the user revealed in it.
"""

import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from eidolon.characters import Character
from eidolon.llm import ChatLLM, ChatMessage, Tool, ToolCall
from eidolon.memory import MemoryWriter, memories_prompt
from eidolon.producer import effective_timezone, producer_prompt
from eidolon.reply_format import FORMAT_INSTRUCTIONS, ReplyParser, SegmentDelta, format_reply
from eidolon.retrieval import RECALL_STORY_TOOL, Retrieval, Retrieved
from eidolon.store import Conversation, Message, Store

MAX_INPUT_LENGTH = 2000
"""The longest thing a user can say in one turn, typed or spoken, in characters; longer
input is rejected, not cut short."""
MAX_TOOL_ROUNDS = 1
"""How many rounds of tool calls the chat model gets in one turn; after that it has to answer."""
LAST_ROUND_NOTE = (
    "（这一轮不能再调用任何工具了，请现在就回答制作人。上面想起来的内容如果答不上他的问题，"
    "就像一时记不清那样自然地说，不要提到查找、工具、记录或剧情库。）"
)
"""Added to each tool result the model reads just before the round that offers no tools.
Without it the model, still wanting to look something up, writes out its own tool-call
markup as the reply. Worded and verified against the real chat model; rewording it needs
that verification again."""


@dataclass(frozen=True)
class UserSaid:
    """What the user said, as the turn takes it up; every turn opens with it."""

    text: str
    type: Literal["user"] = field(default="user", init=False)


@dataclass(frozen=True)
class TurnDone:
    """The recorded reply; the turn succeeded."""

    message: Message
    type: Literal["done"] = field(default="done", init=False)


@dataclass(frozen=True)
class TurnFailed:
    """Why the turn was rejected or failed, for the user to read; it left no record."""

    message: str
    type: Literal["error"] = field(default="error", init=False)


TurnEvent = UserSaid | SegmentDelta | TurnDone | TurnFailed
"""A turn's events: `user`, then any `delta`s, then `done` or `error`. `asdict(event)` is
the event as it goes out to the browser."""

FAILED = "角色暂时无法回复，请稍后再试。"
"""What the user reads when a turn fails; the details stay in the server log."""
TOO_LONG = f"这句话太长了，最多 {MAX_INPUT_LENGTH} 字。"
"""What the user reads when a turn is rejected for input over `MAX_INPUT_LENGTH`."""
BLANK = "没有收到要说的话。"
"""What the user reads when a turn is rejected for blank input."""

log = logging.getLogger(__name__)

Clock = Callable[[], datetime]
"""The current time, timezone-aware."""


def utc_now() -> datetime:
    return datetime.now(UTC)


class EmptyReply(RuntimeError):
    pass


def latest_turns(messages: list[Message], turns: int | None) -> list[Message]:
    """The messages from the `turns`th last user message on (from the first if None), so
    what the chat model reads always opens with the user."""
    starts = [i for i, m in enumerate(messages) if m.role == "user"]
    kept = starts if turns is None else starts[-turns:]
    return messages[kept[0]:] if kept else []


class ConversationEngine:
    def __init__(
        self,
        store: Store,
        chat_llm: ChatLLM,
        characters: dict[str, Character],
        clock: Clock | None = None,
        retrieval: Retrieval | None = None,
        memory: MemoryWriter | None = None,
        history_turns: int | None = None,
    ) -> None:
        """Without `retrieval`, turns carry no story, character facts or memories; without
        `memory`, nothing is written down. Each turn reads only the conversation's latest
        `history_turns` turns, or all of them if None."""
        self._store = store
        self._characters = characters
        self._llm = chat_llm
        self._clock = clock or utc_now
        self._retrieval = retrieval
        self._memory = memory
        self._names = {c.id: c.name for c in characters.values()}
        self._history_turns = history_turns

    async def turn(
        self, conversation: Conversation, text: str, device_timezone: str | None = None
    ) -> AsyncIterator[TurnEvent]:
        """Take one turn. `device_timezone` is the time zone the user's device reports,
        used unless the producer profile sets one."""
        text = text.strip()
        yield UserSaid(text)
        if not text or len(text) > MAX_INPUT_LENGTH:
            yield TurnFailed(TOO_LONG if text else BLANK)
            return
        try:
            async for event in self._reply(conversation, text, device_timezone):
                yield event
        except Exception:  # the turn has started; report instead of dropping it
            log.exception("turn failed in conversation %s", conversation.id)
            yield TurnFailed(FAILED)

    async def _reply(
        self, conversation: Conversation, text: str, device_timezone: str | None
    ) -> AsyncIterator[TurnEvent]:
        character = self._characters[conversation.character_id]
        history = latest_turns(self._store.list_messages(conversation.id), self._history_turns)
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
            last_round = step + 1 == MAX_TOOL_ROUNDS
            for call in calls:
                result = await self._call_tool(character, call)
                if last_round:
                    result = f"{result}\n\n{LAST_ROUND_NOTE}"
                prompt.append(ChatMessage("tool", result, tool_call_id=call.id))

        if not parser.segments:
            raise EmptyReply("对话模型没有返回任何内容")
        now = self._clock().astimezone(ZoneInfo(timezone))
        reply = self._store.add_turn(conversation.id, text, parser.segments)
        if self._memory:
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
