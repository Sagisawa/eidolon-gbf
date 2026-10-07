"""Letting a turn or call begin, and settling it once it is over (GLOSSARY.md「限额」
「运行记录」): whose keys it runs on, its activity record, its use of the limit and the
deployer's keys it holds, all in one place.

`Admissions` lets each begin, in order: it takes the keys (`OwnKeys`), opens the
activity record, prepares the models, each request recorded as a service call, and only
then takes a use of the limit, so that nothing failing before it is counted. Whatever
fails on the way is recorded so, and what was taken let go, before it is raised.

The `Admission` it hands out settles it, once: given back unless its result counts
(`_COUNTED`), the record written, the deployer's keys let go.
"""

from collections.abc import Callable
from typing import Generic, TypeVar

from eidolon.activity import ActivityLog, CallEndReason, Recording, Result, turn_llms
from eidolon.config import LLMSettings
from eidolon.llm import TurnLLMs
from eidolon.own_keys import CallKeys, OwnKeyFailed, OwnKeys, TurnKeys
from eidolon.usage import OverLimit, UsageKind, UsageLimiter, Use

_COUNTED: dict[UsageKind, frozenset[Result]] = {
    "turn": frozenset({"success", "left"}),
    "call": frozenset({"success", "failed"}),
}
"""The results that count towards the user's limit, by kind; any other is given back. A
turn counts once it was taken, done or left; a call once it connected."""

K = TypeVar("K", TurnKeys, CallKeys)


class Admission(Generic[K]):
    """One turn or call let begin, held until it is settled."""

    def __init__(
        self,
        kind: UsageKind,
        keys: K,
        recording: Recording,
        llms: TurnLLMs,
        use: Use,
    ) -> None:
        self._counted = _COUNTED[kind]
        self.keys = keys
        """Whose keys it runs on."""
        self.recording = recording
        """Its activity record, which the service calls made in it are recorded under."""
        self.llms = llms
        """The models it runs on, each request recorded as a service call."""
        self._use = use
        self._settled = False

    @property
    def exempt(self) -> bool:
        """Whether it is on the user's own keys alone, and counts towards nothing."""
        return self.keys.exempt

    def counts(self, result: Result) -> bool:
        """Whether it counts towards the user's limit, turning out as `result`."""
        return not self.exempt and result in self._counted

    def settle(
        self,
        result: Result,
        duration: float | None = None,
        end_reason: CallEndReason | None = None,
    ) -> None:
        """It is over as `result` (a call's with how long it lasted and why it ended):
        its use given back unless that counts, its record written, the deployer's keys
        let go, each whatever became of the one before. Only the first time."""
        if self._settled:
            return
        self._settled = True
        try:
            if result not in self._counted:
                self._use.give_back()  # an exempt use is kept for the admin to see
        finally:
            try:
                self.recording.finish(result, duration, end_reason)
            finally:
                self.keys.release()


class Admissions:
    """Lets the users' turns and calls begin, on the limits, keys and deployer's models
    of the moment."""

    def __init__(
        self,
        usage: UsageLimiter,
        activity: ActivityLog,
        own_keys: OwnKeys,
        deployer_llms: Callable[[], tuple[LLMSettings, LLMSettings]],
    ) -> None:
        """Turns and calls on the deployer's keys run on the chat and memory models
        `deployer_llms` says, as each begins (their service calls are recorded as
        such)."""
        self._usage = usage
        self._activity = activity
        self._own_keys = own_keys
        self._deployer_llms = deployer_llms

    def turn(self, user_id: str, character_id: str) -> Admission[TurnKeys]:
        """Let the user's next text turn with `character_id` begin. Raises OverLimit when
        they have no turns left this hour, OwnKeyFailed when their own key can no longer
        be decrypted; either way, and whatever else fails before it begins, it is
        recorded and takes no use of the limit."""
        try:
            keys = self._own_keys.for_turn(user_id)
        except OwnKeyFailed:
            self._activity.begin("turn", user_id, character_id, own_keys=True).finish("failed")
            raise
        try:
            recording = self._activity.begin("turn", user_id, character_id, keys.exempt)
            try:
                own = self._own_keys.describe(user_id).get("llm") if keys.exempt else None
                llms = turn_llms(self._activity, keys.llms, own, *self._deployer_llms())
                use = self._usage.take(user_id, "turn", exempt=keys.exempt)
            except OverLimit:
                recording.finish("rejected")
                raise
            except BaseException:
                recording.finish("failed")
                raise
        except BaseException:
            keys.release()
            raise
        return Admission("turn", keys, recording, llms, use)
