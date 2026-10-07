"""How a text turn turns out (GLOSSARY.md「回合」), from the events it is told: whether it
counts towards the user's limit, and what its activity record says, are its `Admission`'s
to settle once it is over (`admission`).

`TurnOutcome` is told each event of the turn as the browser is: the character beginning
to speak, the turn done (success), or failed (failed, or rejected for its input). A turn
that is over without either was left by the user.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from eidolon.activity import Result
from eidolon.admission import Admission
from eidolon.engine import BLANK, TOO_LONG, TurnDone, TurnEvent, TurnFailed
from eidolon.own_keys import TurnKeys
from eidolon.reply_format import SegmentDelta


class TurnOutcome:
    """One text turn let begin by `admission`, until it is over."""

    def __init__(self, admission: Admission[TurnKeys]) -> None:
        self._admission = admission
        self._result: Result | None = None

    @contextmanager
    def running(self) -> Iterator[None]:
        """While the turn runs: its service calls are recorded under it, and once it is
        over, however it ended, it is settled."""
        try:
            with self._admission.recording.current():
                yield
        finally:
            self.end()

    def end(self) -> None:
        """Settle the turn as it turned out, once. Also for a turn the user left before
        its response began, which never ran."""
        self._admission.settle(self._result or "left")

    def see(self, event: TurnEvent) -> None:
        """An event of the turn, as the browser is told it."""
        if isinstance(event, SegmentDelta):
            self._admission.recording.spoke()  # the reply's first words have appeared
        elif (result := turn_result(event)) is not None:
            self._result = result


def turn_result(event: TurnEvent) -> Result | None:
    """How a turn turned out, if `event` ends it: done, or failed, which is rejected when
    for its input (GLOSSARY.md「回合」). A turn over without either was left. Text turns
    and the turns of calls alike."""
    if isinstance(event, TurnDone):
        return "success"
    if isinstance(event, TurnFailed):
        return "rejected" if event.message in (BLANK, TOO_LONG) else "failed"
    return None
