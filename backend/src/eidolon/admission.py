"""Letting a turn or call begin, and settling it once it is over (GLOSSARY.md「限额」
「运行记录」): whose keys it runs on, its activity record, its use of the limit and the
deployer's keys it holds, all in one place.

`Admissions` lets each begin, in order: it takes the keys (`OwnKeys`), from those a turn
brings or the user kept for calls, whose models record each request as a service call to
the model they are, opens the activity record, and only then takes a use of the limit, so
that nothing failing before it is counted. Whatever fails on the way is recorded so (`_FAILED`), and
what was taken let go, before it is raised. Before a call is placed, it is only asked
whether the call would count.

The `Admission` it hands out settles it, once: given back unless its result counts
(`_COUNTED`), the record written, the deployer's keys let go.
"""

from collections.abc import Callable
from typing import Generic, TypeVar

from eidolon.activity import ActivityLog, CallEndReason, Recording, Result
from eidolon.llm import TurnLLMs
from eidolon.own_keys import BroughtKeys, CallKeys, OwnKeyFailed, OwnKeys, TurnKeys
from eidolon.usage import OverLimit, UsageKind, UsageLimiter, Use

_COUNTED: dict[UsageKind, frozenset[Result]] = {
    "turn": frozenset({"success", "left"}),
    "call": frozenset({"success", "failed"}),
}
"""The results that count towards the user's limit, by kind; any other is given back. A
turn counts once it was taken, done or left; a call once it connected."""

_FAILED: dict[UsageKind, Result] = {"turn": "failed", "call": "not_connected"}
"""How a turn or call is recorded that failed before it began: a call never connected."""

K = TypeVar("K", TurnKeys, CallKeys)


class Admission(Generic[K]):
    """One turn or call let begin, held until it is settled."""

    def __init__(self, kind: UsageKind, keys: K, recording: Recording, use: Use) -> None:
        self._counted = _COUNTED[kind]
        self.keys = keys
        """Whose keys it runs on."""
        self.recording = recording
        """Its activity record, which the service calls made in it are recorded under."""
        self._use = use
        self._settled = False

    @property
    def llms(self) -> TurnLLMs:
        """The models it runs on, each request recorded as a service call."""
        return self.keys.llms

    @property
    def own_llm(self) -> bool:
        """Whether those are the user's own LLM."""
        return self.keys.own_llm

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
    """Lets the users' turns and calls begin, on the limits and keys of the moment."""

    def __init__(self, usage: UsageLimiter, activity: ActivityLog, own_keys: OwnKeys) -> None:
        self._usage = usage
        self._activity = activity
        self._own_keys = own_keys

    def turn(
        self, user_id: str, character_id: str, brought: BroughtKeys
    ) -> Admission[TurnKeys]:
        """Let the user's next text turn with `character_id`, bringing `brought`, begin.
        Raises OverLimit when they have no turns left this hour; then, and whatever else
        fails before it begins, it is recorded and takes no use of the limit."""
        return self._admit(
            "turn", user_id, character_id, lambda _: self._own_keys.for_turn(brought)
        )

    def call(self, user_id: str, character_id: str) -> Admission[CallKeys]:
        """Let the user's next call with `character_id` begin. Raises OverLimit when they
        have no calls left this hour, OwnKeyFailed when their own key can no longer be
        decrypted; either way, and whatever else fails before it begins, it is recorded
        and takes no use of the limit. Raises CallsUnavailable, recording nothing, when
        the deployment has no keys for calls and neither has the user."""
        return self._admit("call", user_id, character_id, self._call_keys)

    def call_setup(self, user_id: str) -> bool:
        """Whether the user's next call would be on their own keys alone, and so count
        towards nothing; only asked, taking and recording nothing. Raises CallsUnavailable
        as `call` does, and OwnKeyFailed, recording a call that never connected, as the
        call would have been (with no character yet)."""
        keys = self._keys("call", user_id, "", self._call_keys)
        keys.release()
        return keys.exempt

    def _call_keys(self, user_id: str) -> CallKeys:
        return self._own_keys.for_call(self._own_keys.kept(user_id))

    def _keys(
        self, kind: UsageKind, user_id: str, character_id: str, keys_for: Callable[[str], K]
    ) -> K:
        try:
            return keys_for(user_id)
        except OwnKeyFailed:
            self._activity.begin(kind, user_id, character_id, own_keys=True).finish(
                _FAILED[kind]
            )
            raise

    def _admit(
        self, kind: UsageKind, user_id: str, character_id: str, keys_for: Callable[[str], K]
    ) -> Admission[K]:
        keys = self._keys(kind, user_id, character_id, keys_for)
        try:
            recording = self._activity.begin(kind, user_id, character_id, keys.exempt)
            try:
                use = self._usage.take(user_id, kind, exempt=keys.exempt)
            except OverLimit:
                recording.finish("rejected")
                raise
            except BaseException:
                recording.finish(_FAILED[kind])
                raise
        except BaseException:
            keys.release()
            raise
        return Admission(kind, keys, recording, use)
