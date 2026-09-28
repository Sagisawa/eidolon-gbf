"""How a call turns out: whether it counts towards the user's limit, and what the browser
is told when the backend ends it (CONTEXT.md「限额」「接通」).

`CallOutcome` is all the rule is: the call takes a use of the user's limit when it is
offered, and the call's pipeline reports what happens to it (set up or not, connected, a
turn recorded, a service failing, a limit reached, over). Each event hands back the
`ended` message to send the browser, if it is the one that ends the call, and once the
call is over the use is kept or given back as that message said.
"""

from typing import Literal

from eidolon.own_keys import OwnKeyFailed, Service
from eidolon.usage import UsageLimiter

EndReason = Literal["not_connected", "dropped", "duration_limit", "turn_limit", "own_key"]
"""Why the backend ended a call, as the `ended` message tells the browser: it never really
connected (a voice service failed before any turn), a voice service failed later, the call
reached its time or its turn limit, or one of the user's own keys failed."""


def ended(reason: EndReason, message: str, counts: bool) -> dict:
    """The `ended` message: why the call is over, and whether it counted towards the
    user's limit (CONTEXT.md「限额」「接通」)."""
    return {"type": "ended", "reason": reason, "message": message, "counts": counts}


class CallOutcome:
    """Whether one call counts towards the user's limit, from being offered to being over.

    The call is taken when it is offered. It is given back unless it connects, and a call
    that connects but ends on a failing voice service before any turn is recorded never
    really connected either. A call that connected and is hung up, by the user or not,
    or that reaches its limits, is kept; it counts unless it is `exempt`, on the user's
    own keys alone. The browser is told why the backend ended a call only once, by the
    first event to end it, and the call is settled as it was told: nothing that happens
    after that changes whether it counts.
    """

    def __init__(self, usage: UsageLimiter, user_id: str, exempt: bool) -> None:
        """Take the call. Raises OverLimit when the user has no calls left this hour,
        unless the call is exempt."""
        self._use = usage.take(user_id, "call", exempt=exempt)
        self._exempt = exempt
        self._connected = False
        self._recorded = 0
        self._kept: bool | None = None  # decided when the browser is told why the call ended
        self._settled = False

    def set_up_failed(self) -> dict | None:
        """The call could not be set up. It is given back; the browser learns of it from
        the answer to its offer, so there is nothing to tell it here."""
        self._settle()
        return None

    def connected(self) -> dict | None:
        """The call has connected (CONTEXT.md「接通」)."""
        self._connected = True
        return None

    def turn_recorded(self) -> dict | None:
        """A turn of the call was recorded."""
        self._recorded += 1
        return None

    def service_failed(self, own_service: Service | None) -> dict | None:
        """A voice service failed, ending the call; `own_service` is the one failing on
        the user's own key, if it is theirs. Before any turn is recorded the call never
        really connected and is given back. A failing own key is theirs to fix, so they are
        told which. Before the call connects there is no one to tell: the browser learns
        the call is over as its connection closes."""
        if not self._connected:
            return None
        kept = self._recorded > 0
        if own_service is not None:
            message = OwnKeyFailed(own_service, "通话已结束").message
            return self._end("own_key", message, kept)
        if not kept:
            return self._end("not_connected", "语音服务出了故障，通话没能接通", kept)
        return self._end("dropped", "语音服务出了故障，通话中断了", kept)

    def limit_reached(self, reason: EndReason, why: str) -> dict | None:
        """The call reached its time or its turn limit (`reason`), as `why` says; it was
        connected, so it is kept."""
        return self._end(reason, f"{why}，先挂断啦。想接着聊可以重新拨打。", True)

    def settle(self) -> dict | None:
        """The call is over, however it ended: keep it or give it back, once."""
        self._settle()
        return None

    def _end(self, reason: EndReason, message: str, kept: bool) -> dict | None:
        """The `ended` message, unless the browser was already told why the call ended."""
        if self._kept is not None:
            return None
        self._kept = kept
        return ended(reason, message, kept and not self._exempt)

    def _settle(self) -> None:
        if self._settled:
            return
        self._settled = True
        if not self._connected or self._kept is False:
            self._use.give_back()
