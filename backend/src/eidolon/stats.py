"""Stats (GLOSSARY.md「统计」): the user's own dealings with the characters, summed up for
them alone under `/api/stats`.

Only what is still in their conversations counts: a turn (the user's message, at the time
of it) or a gift (a `gift` conversation event); a past conversation deleted, what was in
it no longer counts. Dates and hours are where the producer is: the profile's time zone,
else the browser's (`X-Timezone`), else the default, as a turn tells her now
(`effective_timezone`).

What does not change with the range: the days since the user signed up, counting that day
as the first; the days in a row they came, a day they took a turn or gave a gift, the
current run counted back from today, or from yesterday while they have not come yet
today, and the longest; how many of either at each hour of the day, all told; and how many
on each day of the past 52 weeks, from a Monday, and this week up to today.

What does (`range`): the past 30 days or 365, today the last, or all of it. How many turns
and how many of either at each hour of the day; each character's turns, she among those
anything is left with, in the idols' order, and the days since the first thing left with
her, a message or an event, counting that day as the first; and the gifts given, how many
she liked as they were given, and whom the most went to, the first in the idols' order of
those tied. Only numbers: what is shown of them, and how, is the page's to decide.
"""

from collections import Counter
from collections.abc import Collection
from datetime import date, datetime, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, Query

from eidolon.assembly import Backend
from eidolon.characters import in_idol_order
from eidolon.producer import effective_timezone
from eidolon.sessions import UserId
from eidolon.store import Contact

HEATMAP_WEEKS = 52
"""The whole weeks before this one the heatmap goes back."""

Range = Literal["30d", "1y", "all"]

RANGE_DAYS: dict[Range, int | None] = {"30d": 30, "1y": 365, "all": None}
"""The days each range takes in, today the last; all of them for `all`."""


def add_stats_routes(app: FastAPI, backend: Backend) -> None:
    store = backend.store

    @app.get("/api/stats")
    def stats(
        user_id: UserId,
        span: Annotated[Range, Query(alias="range")] = "all",
        device_timezone: Annotated[str | None, Header(alias="X-Timezone")] = None,
    ) -> dict:
        zone = ZoneInfo(effective_timezone(store.get_profile(user_id), device_timezone))
        today = backend.clock().astimezone(zone).date()
        contacts = [(c, c.at.astimezone(zone)) for c in store.contacts(user_id)]
        per_day = Counter(at.date() for _, at in contacts)
        per_hour = Counter(at.hour for _, at in contacts)
        signed_up = datetime.fromisoformat(store.get_user(user_id).created_at)
        start = today - timedelta(days=today.weekday() + 7 * HEATMAP_WEEKS)

        def days_since(at: datetime) -> int:
            """The days since `at`, counting its day as the first."""
            return max(1, (today - at.astimezone(zone).date()).days + 1)

        days = RANGE_DAYS[span]
        since = None if days is None else today - timedelta(days=days - 1)
        first = store.first_records(user_id)
        return {
            "days_known": days_since(signed_up),
            "visits": visits(per_day.keys(), today),
            "all_hours": [per_hour[hour] for hour in range(24)],
            "heatmap": {
                "from": start.isoformat(),
                "counts": [
                    per_day[start + timedelta(days=i)] for i in range((today - start).days + 1)
                ],
            },
            "range": in_range(
                span,
                [(c, at) for c, at in contacts if since is None or at.date() >= since],
                {
                    c.id: days_since(first[c.id])
                    for c in in_idol_order(backend.characters.values())
                    if c.id in first
                },
            ),
        }


def in_range(span: Range, within: list[tuple[Contact, datetime]], known: dict[str, int]) -> dict:
    """What changes with the range `span`, of the turns and gifts `within` it, each at its
    time where the user is, and the characters anything is left with, in the idols' order,
    and the days each has been `known`."""
    turns = Counter(c.character_id for c, _ in within if c.kind == "turn")
    per_hour = Counter(at.hour for _, at in within)
    gifts = [c for c, _ in within if c.kind == "gift"]
    given = Counter(c.character_id for c in gifts)
    most = max(given.values(), default=0)
    return {
        "span": span,
        "turns": turns.total(),
        "by_hour": [per_hour[hour] for hour in range(24)],
        "characters": [
            {"character_id": character, "turns": turns[character], "days_known": days}
            for character, days in known.items()
        ],
        "gifts": {
            "given": len(gifts),
            "liked": sum(c.liked for c in gifts),
            "most": next(
                (
                    {"character_id": character, "given": most}
                    for character in known
                    if most and given[character] == most
                ),
                None,
            ),
        },
    }


def visits(days: Collection[date], today: date) -> dict:
    """The days in a row the user came, of `days`, the days they came: the run up to today,
    or up to yesterday while today is not one of them yet, and the longest."""
    longest = run = 0
    previous: date | None = None
    for day in sorted(d for d in days if d <= today):
        run = run + 1 if previous == day - timedelta(days=1) else 1
        longest = max(longest, run)
        previous = day
    current = 0
    day = today if today in days else today - timedelta(days=1)
    while day in days:
        current += 1
        day -= timedelta(days=1)
    return {"current": current, "longest": longest}
