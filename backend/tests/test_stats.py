"""Stats (GLOSSARY.md「统计」), the part that does not change with the range: how many days
since the user signed up, the days in a row they have come (now and at the longest), the
hours they come at, and each day of the past 52 weeks. A turn or a gift counts; a day they
gave a gift and said nothing was a day they came. Dates and hours are the producer
profile's time zone's, else the browser's (`X-Timezone`). Only what is still in their
conversations counts: a past conversation deleted, it no longer does, though the days since
they signed up stay. Driven through the backend's external API, the clock moved by hand and
when things were recorded put in the database as if they had happened then."""

import sqlite3
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from eidolon.config import Settings
from eidolon.gift_catalog import GIFTS_FILE
from tests.conftest import CharacterConfig, ClientFactory
from tests.fakes import FAKE_JUDGE, START, FakeClock, FakeLLM, FakeRandom
from tests.test_gift_backpack import COMMON, FIRST
from tests.test_gift_catalog import ONE_OF_EACH_RARITY
from tests.test_text_turn import send_turn, start_conversation

REPLY = ["<ja>はい</ja><zh>好的</zh>"]

TODAY = date(2026, 9, 25)
"""START's day in Tokyo (21:00 there), a Friday; the week the heatmap ends in began on
Monday the 21st."""

HEATMAP_FROM = date(2025, 9, 22)
"""The Monday 52 weeks before this week's."""

TOKYO = {"X-Timezone": "Asia/Tokyo"}


async def stats(client: httpx.AsyncClient, headers: dict[str, str] = TOKYO) -> dict:
    res = await client.get("/api/stats", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def tokyo(day: date, hour: int, minute: int = 0) -> datetime:
    """That time of day in Tokyo, in UTC as the store writes."""
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=UTC) - timedelta(hours=9)


def registered_at(database: Path, when: datetime, name: str = "producer") -> None:
    with sqlite3.connect(database) as db:
        db.execute("UPDATE users SET created_at = ? WHERE name = ?", (when.isoformat(), name))


def said_at(database: Path, text: str, when: datetime) -> None:
    """Have the user's message `text` said at `when`."""
    with sqlite3.connect(database) as db:
        moved = db.execute(
            "UPDATE messages SET created_at = ? WHERE role = 'user' AND text = ?",
            (when.isoformat(), text),
        ).rowcount
    assert moved == 1


def given_at(database: Path, when: datetime) -> None:
    """Have the gift given last given at `when`."""
    with sqlite3.connect(database) as db:
        db.execute(
            "UPDATE conversation_events SET created_at = ? WHERE id ="
            " (SELECT MAX(id) FROM conversation_events WHERE kind = 'gift')",
            (when.isoformat(),),
        )


async def say(client: httpx.AsyncClient, database: Path, conversation: str, text: str,
              when: datetime) -> None:
    """Take a turn in the conversation, said at `when`."""
    assert (await send_turn(client, conversation, text))[-1]["type"] == "done"
    said_at(database, text, when)


def day(stats: dict, which: date) -> int:
    """The heatmap's count on the day."""
    return stats["heatmap"]["counts"][(which - date.fromisoformat(stats["heatmap"]["from"])).days]


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(START)


@pytest.fixture
def gifting(settings: Settings, characters: CharacterConfig) -> Settings:
    """Affinity and gifts on, with cake, which every test character likes, to give."""
    characters.write(GIFTS_FILE, ONE_OF_EACH_RARITY)
    return replace(settings, judge=FAKE_JUDGE, affinity_and_gifts=True)


async def give_cakes(
    make_client: ClientFactory, gifting: Settings, clock: FakeClock, database: Path,
    *when: datetime, character: str = "mano",
) -> None:
    """Have the user give her a cake at each of `when`, drawing them first."""
    client = make_client(
        FakeLLM(), settings=gifting, clock=clock, random=FakeRandom(*[COMMON, FIRST] * len(when))
    )
    now = clock.now
    assert (await client.get("/api/gifts")).status_code == 200
    clock.advance(days=len(when) - 1)  # the chances to draw them
    assert (await client.post("/api/gifts/draws", json={"all": True})).status_code == 200
    clock.now = now
    for at in when:
        res = await client.post(f"/api/characters/{character}/gifts", json={"gift_id": "cake"})
        assert res.status_code == 200, res.text
        given_at(database, at)


async def test_stats_need_a_session(make_client: ClientFactory):
    client = make_client(FakeLLM(), user=None)

    assert (await client.get("/api/stats")).status_code == 401


async def test_a_new_user_has_known_them_a_day_and_come_on_none(
    make_client: ClientFactory, settings: Settings, clock: FakeClock
):
    client = make_client(FakeLLM(), clock=clock)
    registered_at(settings.database_path, clock.now - timedelta(hours=1))

    got = await stats(client)

    assert got["days_known"] == 1
    assert got["visits"] == {"current": 0, "longest": 0}
    assert got["hours"] == [0] * 24
    assert got["heatmap"]["from"] == HEATMAP_FROM.isoformat()
    # 52 whole weeks, and this one up to today, a Friday.
    assert got["heatmap"]["counts"] == [0] * (52 * 7 + 5)


async def test_the_days_since_signing_up_count_from_that_day_in_their_time_zone(
    make_client: ClientFactory, settings: Settings, clock: FakeClock
):
    client = make_client(FakeLLM(), clock=clock)
    # The 16th at 1:00 in Tokyo, still the 15th in UTC.
    registered_at(settings.database_path, tokyo(date(2026, 9, 16), 1))

    assert (await stats(client))["days_known"] == 10
    assert (await stats(client, {"X-Timezone": "UTC"}))["days_known"] == 11


async def test_a_turn_counts_on_the_day_and_at_the_hour_it_was_where_the_user_is(
    make_client: ClientFactory, settings: Settings, clock: FakeClock
):
    client = make_client(FakeLLM(REPLY), clock=clock)
    conversation = await start_conversation(client)
    # Just past midnight on the 25th in Tokyo: 15:30 on the 24th in UTC.
    await say(client, settings.database_path, conversation, "晚安", tokyo(TODAY, 0, 30))

    in_tokyo = await stats(client)
    in_utc = await stats(client, {"X-Timezone": "UTC"})

    assert in_tokyo["hours"][0] == 1 and sum(in_tokyo["hours"]) == 1
    assert day(in_tokyo, TODAY) == 1 and sum(in_tokyo["heatmap"]["counts"]) == 1
    assert in_utc["hours"][15] == 1
    assert day(in_utc, TODAY - timedelta(days=1)) == 1


async def test_the_profiles_time_zone_comes_before_the_browsers(
    make_client: ClientFactory, settings: Settings, clock: FakeClock
):
    client = make_client(FakeLLM(REPLY), clock=clock)
    conversation = await start_conversation(client)
    await say(client, settings.database_path, conversation, "晚安", tokyo(TODAY, 0, 30))
    res = await client.put("/api/profile", json={"timezone": "UTC"})
    assert res.status_code == 200

    got = await stats(client)  # the browser says Tokyo

    assert got["hours"][15] == 1
    assert day(got, TODAY - timedelta(days=1)) == 1


async def test_turns_and_gifts_both_count_each_day_and_hour(
    make_client: ClientFactory, settings: Settings, gifting: Settings, clock: FakeClock
):
    database = settings.database_path
    client = make_client(FakeLLM(REPLY, REPLY), clock=clock)
    conversation = await start_conversation(client)
    await say(client, database, conversation, "早上好", tokyo(TODAY, 8))
    await say(client, database, conversation, "在吗", tokyo(TODAY - timedelta(days=3), 8))
    await give_cakes(make_client, gifting, clock, database, tokyo(TODAY, 8, 30))

    got = await stats(client)

    assert day(got, TODAY) == 2
    assert day(got, TODAY - timedelta(days=3)) == 1
    assert got["hours"][8] == 3


async def test_only_the_past_52_weeks_and_this_one_are_in_the_heatmap_but_every_hour_counts(
    make_client: ClientFactory, settings: Settings, clock: FakeClock
):
    database = settings.database_path
    client = make_client(FakeLLM(REPLY, REPLY), clock=clock)
    conversation = await start_conversation(client)
    await say(client, database, conversation, "第一句", tokyo(HEATMAP_FROM, 10))
    await say(client, database, conversation, "更早", tokyo(HEATMAP_FROM - timedelta(days=1), 22))

    got = await stats(client)

    assert got["heatmap"]["counts"][0] == 1
    assert sum(got["heatmap"]["counts"]) == 1
    assert got["hours"][10] == 1 and got["hours"][22] == 1


async def test_a_day_they_only_gave_a_gift_is_a_day_they_came(
    make_client: ClientFactory, settings: Settings, gifting: Settings, clock: FakeClock
):
    database = settings.database_path
    client = make_client(FakeLLM(*[REPLY] * 3), clock=clock)
    conversation = await start_conversation(client)
    for i, ago in enumerate((9, 8, 6)):  # the 7th day ago only a gift
        await say(client, database, conversation, f"第{i}天", tokyo(TODAY - timedelta(days=ago), 20))
    await give_cakes(make_client, gifting, clock, database, tokyo(TODAY - timedelta(days=7), 20))

    assert (await stats(client))["visits"] == {"current": 0, "longest": 4}


async def test_not_having_come_yet_today_does_not_break_the_days_in_a_row(
    make_client: ClientFactory, settings: Settings, clock: FakeClock
):
    database = settings.database_path
    client = make_client(FakeLLM(*[REPLY] * 4), clock=clock)
    conversation = await start_conversation(client)
    for ago in (5, 2, 1):
        await say(client, database, conversation, f"{ago}天前", tokyo(TODAY - timedelta(days=ago), 12))

    assert (await stats(client))["visits"] == {"current": 2, "longest": 2}

    await say(client, database, conversation, "今天", tokyo(TODAY, 12))

    assert (await stats(client))["visits"] == {"current": 3, "longest": 3}


async def test_a_deleted_past_conversation_no_longer_counts_but_the_days_known_stay(
    make_client: ClientFactory, settings: Settings, clock: FakeClock
):
    database = settings.database_path
    client = make_client(FakeLLM(REPLY, REPLY), clock=clock)
    registered_at(database, tokyo(TODAY - timedelta(days=30), 12))
    past = await start_conversation(client)
    await say(client, database, past, "上周", tokyo(TODAY - timedelta(days=1), 23))
    current = await start_conversation(client)
    await say(client, database, current, "今天", tokyo(TODAY, 9))
    before = await stats(client)

    assert (await client.delete(f"/api/conversations/{past}")).status_code == 204
    after = await stats(client)

    assert before["visits"] == {"current": 2, "longest": 2}
    assert after["visits"] == {"current": 1, "longest": 1}
    assert (day(before, TODAY - timedelta(days=1)), day(after, TODAY - timedelta(days=1))) == (1, 0)
    assert (before["hours"][23], after["hours"][23]) == (1, 0)
    assert after["hours"][9] == 1
    assert before["days_known"] == after["days_known"] == 31


async def test_a_user_sees_only_their_own(
    make_client: ClientFactory, settings: Settings, clock: FakeClock
):
    producer = make_client(FakeLLM(REPLY), clock=clock)
    friend = make_client(FakeLLM(), "friend", clock=clock)
    conversation = await start_conversation(producer)
    await say(producer, settings.database_path, conversation, "你好", tokyo(TODAY, 9))

    theirs = await stats(friend)

    assert theirs["hours"] == [0] * 24
    assert theirs["visits"] == {"current": 0, "longest": 0}
    assert (await stats(producer))["hours"][9] == 1
