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
on each day of the past 52 weeks, from a Monday, and this week up to today. Only numbers:
what is shown of them, and how, is the page's to decide.
"""

from collections import Counter
from collections.abc import Collection
from datetime import date, datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header

from eidolon.assembly import Backend
from eidolon.producer import effective_timezone
from eidolon.sessions import UserId

HEATMAP_WEEKS = 52
"""The whole weeks before this one the heatmap goes back."""


def add_stats_routes(app: FastAPI, backend: Backend) -> None:
    store = backend.store

    @app.get("/api/stats")
    def stats(
        user_id: UserId,
        device_timezone: Annotated[str | None, Header(alias="X-Timezone")] = None,
    ) -> dict:
        zone = ZoneInfo(effective_timezone(store.get_profile(user_id), device_timezone))
        today = backend.clock().astimezone(zone).date()
        local = [c.at.astimezone(zone) for c in store.contacts(user_id)]
        per_day = Counter(at.date() for at in local)
        per_hour = Counter(at.hour for at in local)
        signed_up = datetime.fromisoformat(store.get_user(user_id).created_at)
        start = today - timedelta(days=today.weekday() + 7 * HEATMAP_WEEKS)
        return {
            "days_known": max(1, (today - signed_up.astimezone(zone).date()).days + 1),
            "visits": visits(per_day.keys(), today),
            "all_hours": [per_hour[hour] for hour in range(24)],
            "heatmap": {
                "from": start.isoformat(),
                "counts": [
                    per_day[start + timedelta(days=i)] for i in range((today - start).days + 1)
                ],
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
