"""The conversation engine: one conversation turn in, the character's reply out.

It knows nothing about voice. Given a conversation and the user's input text it
retrieves what the turn calls for, assembles the prompt, streams the chat model's structured reply as per-segment
deltas, and records both sides of the turn once the reply is complete.

Every turn, typed or spoken, speaks the same protocol: `user` (the input as taken up),
then any `delta`s, then `done` or `error`. Among the deltas, `SegmentComplete` says
when a segment is complete; it stays on the server. Input that is blank or too long is rejected
before the model is asked; a turn that is rejected or fails part-way leaves no record,
and what went wrong stays in the server log.

When retrieval is available the chat model is offered the recall-story tool, unless
the turn already recalled an episode. Its calls are answered and the model asked
again, once at most since every round costs the model's time to first token; whatever
it says along the way is part of the reply, and only the reply is recorded.

Every turn carries the world setting, when there is one, after the character sheet: the
office and its units, and the character's own songs and lives, each release and live
told as past or still to come by the day it is where the user is, the day the prompt about the producer tells.

The user's memories that retrieval finds go into the prompt, and once a turn is
recorded memory writes down what the user revealed in it, when memory is on.

A turn can be told to stop part-way (a call's user interrupting the character): the
model and any tool it is waiting on are abandoned at once, and the turn is recorded as
ever, with only the segments complete by then.

Each turn runs on the models it is given (see `OwnKeys.for_turn`): one plays the
character, the other writes down memories. When the user's own fails, the turn fails
saying so. Retrieval is always the deployer's.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal, ParamSpec, TypeVar

from eidolon.characters import Character
from eidolon.clock import Clock
from eidolon.llm import ChatMessage, Tool, ToolCall, TurnLLMs
from eidolon.memory import Memories
from eidolon.own_keys import OwnKeyFailed
from eidolon.producer import effective_timezone, local_date, producer_prompt
from eidolon.reply_format import (
    FORMAT_INSTRUCTIONS,
    ReplyParser,
    SegmentComplete,
    SegmentDelta,
    SpeechDelta,
    format_reply,
)
from eidolon.retrieval import RECALL_STORY_TOOL, Retrieval, Retrieved
from eidolon.store import Conversation, Message, Store
from eidolon.world import World

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


TurnEvent = UserSaid | SegmentDelta | SpeechDelta | SegmentComplete | TurnDone | TurnFailed
"""A turn's events: `user`, then any `delta`s, then `done` or `error`. `asdict(event)` is
the event as it goes out to the browser, except `SpeechDelta` and `SegmentComplete`, which
do not."""

FAILED = "角色暂时无法回复，请稍后再试。"
"""What the user reads when a turn fails; the details stay in the server log."""
TOO_LONG = f"这句话太长了，最多 {MAX_INPUT_LENGTH} 字。"
"""What the user reads when a turn is rejected for input over `MAX_INPUT_LENGTH`."""
BLANK = "没有收到要说的话。"
"""What the user reads when a turn is rejected for blank input."""

log = logging.getLogger(__name__)

class EmptyReply(RuntimeError):
    pass


class _Stopped(Exception):
    """The turn was told to stop."""


P = ParamSpec("P")
T = TypeVar("T")


async def _unless_stopped(
    stop: asyncio.Event | None, work: Callable[P, Awaitable[T]], *args: P.args, **kwargs: P.kwargs
) -> T:
    """What `work` comes to, unless `stop` is set first: then it is abandoned and this
    raises _Stopped."""
    if stop is None:
        return await work(*args, **kwargs)
    if stop.is_set():
        raise _Stopped
    working = asyncio.ensure_future(work(*args, **kwargs))
    stopped = asyncio.ensure_future(stop.wait())
    try:
        await asyncio.wait({working, stopped}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        stopped.cancel()
        if not working.done():
            working.cancel()
            await asyncio.wait({working})
    if working.cancelled():
        raise _Stopped
    return working.result()


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
        characters: dict[str, Character],
        memory: Memories,
        clock: Clock,
        retrieval: Retrieval | None = None,
        history_turns: int | None = None,
        world: World | None = None,
    ) -> None:
        """Without `retrieval`, turns carry no story or character facts and find no
        memories. Each turn reads only the conversation's latest `history_turns` turns, or
        all of them if None. Without `world`, turns carry no world setting."""
        self._store = store
        self._characters = characters
        self._clock = clock
        self._retrieval = retrieval
        self._memory = memory
        self._history_turns = history_turns
        self._world = world

    async def turn(
        self,
        conversation: Conversation,
        text: str,
        llms: TurnLLMs,
        device_timezone: str | None = None,
        stop: asyncio.Event | None = None,
    ) -> AsyncIterator[TurnEvent]:
        """Take one turn on `llms`. `device_timezone` is the time zone the user's device
        reports, used unless the producer profile sets one. Once `stop` is set, the turn
        goes no further and is recorded with the segments complete by then."""
        text = text.strip()
        yield UserSaid(text)
        if not text or len(text) > MAX_INPUT_LENGTH:
            yield TurnFailed(TOO_LONG if text else BLANK)
            return
        try:
            async for event in self._reply(conversation, text, llms, device_timezone, stop):
                yield event
        except OwnKeyFailed as e:  # theirs to fix, so they are told what went wrong
            log.warning("turn failed on the user's own key in conversation %s: %s",
                        conversation.id, e.service)
            yield TurnFailed(e.message)
        except Exception:  # the turn has started; report instead of dropping it
            log.exception("turn failed in conversation %s", conversation.id)
            yield TurnFailed(FAILED)

    async def _reply(
        self,
        conversation: Conversation,
        text: str,
        llms: TurnLLMs,
        device_timezone: str | None,
        stop: asyncio.Event | None,
    ) -> AsyncIterator[TurnEvent]:
        character = self._characters[conversation.character_id]
        history = latest_turns(self._store.list_messages(conversation.id), self._history_turns)
        profile = self._store.get_profile(conversation.user_id)
        timezone = effective_timezone(profile, device_timezone)
        memory = await self._memory.begin(conversation, timezone, llms.memory)
        retrieved = (
            await self._retrieval.retrieve(character, history, text, memory)
            if self._retrieval
            else Retrieved(None)
        )
        now = self._clock()
        about_producer = producer_prompt(profile, now, timezone)
        world_prompt = (
            self._world.prompt(character.name, local_date(now, timezone)) if self._world else None
        )
        prompt = self._prompt(character, world_prompt, about_producer, history, retrieved, text)

        tools: list[Tool] = (
            [RECALL_STORY_TOOL] if self._retrieval and not retrieved.recalled else []
        )
        parser = ReplyParser()
        try:
            for step in range(MAX_TOOL_ROUNDS + 1):
                offered = tools if step < MAX_TOOL_ROUNDS else []
                said = ""
                calls: list[ToolCall] = []
                stream = llms.chat.stream(prompt, offered)
                try:
                    while (item := await _unless_stopped(stop, anext, stream, None)) is not None:
                        if isinstance(item, ToolCall):
                            calls.append(item)
                            continue
                        said += item
                        for event in parser.feed(item):
                            yield event
                finally:
                    if (close := getattr(stream, "aclose", None)) is not None:
                        await close()  # a stream left part-way lets go of its connection
                for event in parser.finish():
                    yield event
                if not calls or not offered:  # a call to a tool not offered goes unanswered
                    break
                prompt = [*prompt, ChatMessage("assistant", said, tool_calls=tuple(calls))]
                last_round = step + 1 == MAX_TOOL_ROUNDS
                for call in calls:
                    result = await _unless_stopped(stop, self._call_tool, character, call)
                    if last_round:
                        result = f"{result}\n\n{LAST_ROUND_NOTE}"
                    prompt.append(ChatMessage("tool", result, tool_call_id=call.id))
        except _Stopped:
            pass

        if not parser.complete:
            raise EmptyReply("对话模型没有返回任何内容")
        reply = self._store.add_turn(conversation.id, text, parser.complete)
        memory.write_down(history, text, reply)
        yield TurnDone(reply.without_cues())

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
        world_prompt: str | None,
        about_producer: str,
        history: list[Message],
        retrieved: Retrieved,
        text: str,
    ) -> list[ChatMessage]:
        sections = [character.sheet]
        if world_prompt:
            sections.append(world_prompt)
        sections.append(about_producer)
        if retrieved.memories_prompt:
            sections.append(retrieved.memories_prompt)
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
