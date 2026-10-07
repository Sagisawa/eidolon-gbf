"""How a text turn turns out: whether it counts towards the user's limit, and what its
activity record says of it, both from one judgment (GLOSSARY.md「回合」「限额」「运行记录」).

`TurnOutcome` is all the rule is. The turn takes a use of the user's limit as it begins,
on whoever's keys `OwnKeys.for_turn` says, and opens its activity record. Then it is told
each event of the turn as the browser is: the character beginning to speak, the turn done
(success), or failed (given back, and failed, or rejected for its input). A turn that is
over without either was left by the user: it is kept. A turn refused before it begins,
over the limit or on an own key that can no longer be decrypted, is recorded so and
refused all the same.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from eidolon.activity import ActivityLog, Result, turn_llms
from eidolon.config import LLMSettings
from eidolon.engine import BLANK, TOO_LONG, TurnDone, TurnEvent, TurnFailed
from eidolon.llm import TurnLLMs
from eidolon.own_keys import OwnKeyFailed, OwnKeys
from eidolon.reply_format import SegmentDelta
from eidolon.usage import OverLimit, UsageLimiter


class TurnOutcome:
    """One text turn of the user's with `character_id`, from taking its use of the limit
    to being over."""

    def __init__(
        self,
        usage: UsageLimiter,
        activity: ActivityLog,
        own_keys: OwnKeys,
        user_id: str,
        character_id: str,
        deployer: tuple[LLMSettings, LLMSettings],
    ) -> None:
        """Take the turn on the user's keys, or the deployer's `deployer` chat and memory
        models, held until `end`. Raises OverLimit when the user has no turns left this hour, OwnKeyFailed
        when their own key can no longer be decrypted."""
        try:
            keys = own_keys.for_turn(user_id)
        except OwnKeyFailed:
            activity.begin("turn", user_id, character_id, own_keys=True).finish("failed")
            raise
        self._release = keys.release
        try:
            self._recording = activity.begin("turn", user_id, character_id, keys.exempt)
            try:
                self._use = usage.take(user_id, "turn", exempt=keys.exempt)
            except OverLimit:
                self._recording.finish("rejected")
                raise
            own = own_keys.describe(user_id).get("llm") if keys.exempt else None
            self.llms: TurnLLMs = turn_llms(activity, keys.llms, own, *deployer)
            """The models the turn runs on, each request recorded as a service call."""
        except BaseException:
            keys.release()
            raise
        self._result: Result | None = None
        self._ended = False

    @contextmanager
    def running(self) -> Iterator[None]:
        """While the turn runs: its service calls are recorded under it, and once it is
        over, however it ended, it is settled."""
        try:
            with self._recording.current():
                yield
        finally:
            self.end()

    def end(self) -> None:
        """Settle the turn, once: its record finished and the deployer's keys let go. Also
        for a turn the user left before its response began, which never ran."""
        if self._ended:
            return
        self._ended = True
        try:
            self._recording.finish(self._result or "left")
        finally:
            self._release()

    def see(self, event: TurnEvent) -> None:
        """An event of the turn, as the browser is told it."""
        if isinstance(event, SegmentDelta):
            self._recording.spoke()  # the reply's first words have appeared
        elif (result := turn_result(event)) is not None:
            self._result = result
            if result != "success":
                self._use.give_back()


def turn_result(event: TurnEvent) -> Result | None:
    """How a turn turned out, if `event` ends it: done, or failed, which is rejected when
    for its input (GLOSSARY.md「回合」). A turn over without either was left. Text turns
    and the turns of calls alike."""
    if isinstance(event, TurnDone):
        return "success"
    if isinstance(event, TurnFailed):
        return "rejected" if event.message in (BLANK, TOO_LONG) else "failed"
    return None
