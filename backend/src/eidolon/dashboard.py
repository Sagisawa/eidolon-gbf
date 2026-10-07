"""The dashboard (GLOSSARY.md「看板」): the activity records of a recent range of time,
summed up for the admin, under `/api/admin/dashboard`.

Everything is summed up here; the browser only shows it. For each service, on the
deployer's keys and on users' own apart: how many calls, how many failed and how, how
long they took, and what they were billed for. For text turns: how many, by how they
turned out, how many on users' own keys, how many users, how soon the character began to
speak, how many with each character, and how many in each stretch of the range (`trend`),
in stretches beginning where the admin's clock (`X-Timezone`) has a round hour or day.
Nothing anyone said is in it, nor whose any of it was.
"""

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import FastAPI, Header, Query

from eidolon.activity import RESULTS, SERVICES, CallRow, RecordRow
from eidolon.admin_api import Admin
from eidolon.assembly import Backend

Range = Literal["24h", "7d", "30d", "90d"]


@dataclass(frozen=True)
class Span:
    """A range of the dashboard: how far back it goes, and how long each stretch of its
    trend is."""

    length: timedelta
    stretch: timedelta
    bucket: Literal["hour", "6h", "day"]


SPANS: dict[Range, Span] = {
    "24h": Span(timedelta(hours=24), timedelta(hours=1), "hour"),
    "7d": Span(timedelta(days=7), timedelta(hours=6), "6h"),
    "30d": Span(timedelta(days=30), timedelta(days=1), "day"),
    "90d": Span(timedelta(days=90), timedelta(days=1), "day"),
}


def add_dashboard_routes(app: FastAPI, backend: Backend) -> None:
    @app.get("/api/admin/dashboard")
    def dashboard(
        _: Admin,
        range: Annotated[Range, Query()] = "24h",
        timezone: Annotated[str | None, Header(alias="X-Timezone")] = None,
    ) -> dict:
        """The activity of the last `range`, summed up."""
        span = SPANS[range]
        now = backend.clock()
        records, calls = backend.activity.since(now - span.length)
        names = {id: c.name for id, c in backend.characters.items()}
        return {
            "range": range,
            "from": (now - span.length).isoformat(),
            "to": now.isoformat(),
            "bucket": span.bucket,
            "health": health(calls),
            "turns": turns([r for r in records if r.kind == "turn"]),
            "trend": trend(
                [r for r in records if r.kind == "turn"], stretches(now, span, _zone(timezone))
            ),
            "characters": characters([r for r in records if r.kind == "turn"], names),
        }


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def percentile(values: Sequence[float], p: float) -> float | None:
    """The nearest-rank `p`th percentile of `values`, None of none."""
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)], 1)


def health(calls: Iterable[CallRow]) -> list[dict]:
    """Each service's calls, on the deployer's keys and on users' own apart, in the order
    of `SERVICES`."""
    groups: dict[tuple[str, bool], list[CallRow]] = defaultdict(list)
    for call in calls:
        groups[(call.service, call.own_key)].append(call)
    rows = []
    for (service, own_key), group in sorted(
        groups.items(), key=lambda g: (_order(g[0][0]), g[0][1])
    ):
        failed = [c for c in group if c.error is not None]
        latencies = [c.latency_ms for c in group]
        rows.append({
            "service": service,
            "own_key": own_key,
            "calls": len(group),
            "errors": len(failed),
            "error_rate": len(failed) / len(group),
            "errors_by_kind": dict(Counter(c.error for c in failed if c.error)),
            "latency_ms": {"p50": percentile(latencies, 50), "p95": percentile(latencies, 95)},
            "usage": _usage(group),
            "usage_unknown": sum(c.usage_unit is None for c in group),
        })
    return rows


def _order(service: str) -> int:
    return SERVICES.index(service) if service in SERVICES else len(SERVICES)  # pyright: ignore[reportArgumentType]


def _usage(calls: Sequence[CallRow]) -> list[dict]:
    """What the calls were billed for, in each unit they were billed in."""
    units: dict[str, list[CallRow]] = defaultdict(list)
    for call in calls:
        if call.usage_unit is not None:
            units[call.usage_unit].append(call)
    return [
        {
            "unit": unit,
            "input": _sum(c.usage_input for c in billed),
            "output": _sum(c.usage_output for c in billed),
        }
        for unit, billed in sorted(units.items())
    ]


def _sum(values: Iterable[float | None]) -> float | None:
    told = [v for v in values if v is not None]
    return sum(told) if told else None


def turns(records: Sequence[RecordRow]) -> dict:
    by_result = Counter(r.result for r in records)
    return {
        "total": len(records),
        "by_result": {result: by_result[result] for result in RESULTS if result != "not_connected"},
        "own_keys": sum(r.own_keys for r in records),
        "active_users": len({r.who for r in records if r.who is not None}),
        "time_to_speak_ms": _speaking(records),
    }


def _speaking(records: Sequence[RecordRow]) -> dict:
    """How soon the character began to speak, in the turns where she did."""
    times = [r.time_to_speak_ms for r in records if r.time_to_speak_ms is not None]
    return {"count": len(times), "p50": percentile(times, 50), "p90": percentile(times, 90)}


def stretches(now: datetime, span: Span, zone: ZoneInfo) -> list[datetime]:
    """Where each stretch of the range's trend begins, oldest first: the last one where
    the admin's clock last had a round hour, six hours or day, and as many before it as the
    range holds."""
    local = now.astimezone(zone)
    if span.stretch >= timedelta(days=1):
        last = local.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        hours = int(span.stretch / timedelta(hours=1))
        last = local.replace(hour=local.hour - local.hour % hours, minute=0, second=0,
                             microsecond=0)
    count = int(span.length / span.stretch)
    last = last.astimezone(UTC)
    return [last - span.stretch * (count - 1 - i) for i in range(count)]


def trend(records: Sequence[RecordRow], starts: Sequence[datetime]) -> list[dict]:
    """How many turns, and by how many users, in each stretch beginning at `starts`; the
    first takes in whatever of the range comes before it."""
    stretch = starts[1] - starts[0] if len(starts) > 1 else timedelta(days=1)
    counts = [0] * len(starts)
    users: list[set[str]] = [set() for _ in starts]
    for record in records:
        i = max(0, min(len(starts) - 1, int((record.started_at - starts[0]) / stretch)))
        counts[i] += 1
        if record.who is not None:
            users[i].add(record.who)
    return [
        {"start": start.isoformat(), "turns": n, "active_users": len(who)}
        for start, n, who in zip(starts, counts, users, strict=True)
    ]


def characters(records: Sequence[RecordRow], names: dict[str, str]) -> list[dict]:
    """How many turns with each character, most first; a character since removed from the
    configuration has no name."""
    counted = Counter(r.character_id for r in records)
    return [
        {"character_id": id, "name": names.get(id), "turns": n}
        for id, n in sorted(counted.items(), key=lambda c: (-c[1], c[0]))
    ]
