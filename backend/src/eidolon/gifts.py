"""Gifts (GLOSSARY.md「礼物」「抽奖」「重置卡」): each user's draw chances, what they have drawn
and their reset cards, the one way into them for the gifts page and the admin console.

Draw chances are given one a day (`affinity.DRAWS_PER_DAY`) at the producer's own midnight,
kept up to `affinity.MAX_DRAWS`. Nothing gives them on a schedule: whoever reads them first
gives what the days since they were last given have brought, counted in the producer's own
time zone (`producer.effective_timezone`). A user without any yet is given one that day,
new or not. A day that is not later than the one they were last given on, as when the time
zone is turned back, gives none.

Gifts are open where affinity is (`LiveConfig.affinity_on`): the deployment has the judge
model and the switch「好感度和礼物」is on. Closed, what each user has is kept and read all
the same, but no chances are given; and the days it was closed give none once it opens
again, which gives one that day. So when it last opened is kept (`notice`), as the backend
starts and as the switch changes. That is no one's; what each user has is theirs, deleted
with them (`database.USER_DATA`).

Each draw uses a chance and gives a reset card or a gift, as likely as `affinity.DRAW_ODDS`
says, any of the rarity's gifts not retired as likely as another: nothing is guaranteed,
and whom a gift is liked by plays no part. Drawn gifts stack in the backpack, which keeps
them retired since or not. The numbers come from the random source the backend is built
with (`randomness.Random`). Drawing calls no model and leaves no activity record.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from itertools import accumulate
from pathlib import Path

from eidolon.affinity import DRAW_ODDS, DRAWS_PER_DAY, MAX_DRAWS, Affinities
from eidolon.characters import Character
from eidolon.clock import Clock
from eidolon.database import connect
from eidolon.gift_catalog import Gift
from eidolon.producer import local_date
from eidolon.randomness import Random

_SCHEMA = """
-- One row per user given any draw chances: how many they have, the producer's own day they
-- were last given on, and how many reset cards they have.
CREATE TABLE IF NOT EXISTS gift_balances (
    user_id TEXT PRIMARY KEY REFERENCES users(id),
    draws INTEGER NOT NULL,
    given_on TEXT NOT NULL,
    reset_cards INTEGER NOT NULL DEFAULT 0
);
-- One row: whether gifts were open when last noticed, and when they last opened (none if
-- never noticed opening).
CREATE TABLE IF NOT EXISTS gifts_opened (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    open INTEGER NOT NULL,
    opened_at TEXT
);
-- How many of each gift each user has; a row of none is as good as no row.
CREATE TABLE IF NOT EXISTS gift_backpacks (
    user_id TEXT NOT NULL REFERENCES users(id),
    gift_id TEXT NOT NULL,
    count INTEGER NOT NULL,
    PRIMARY KEY (user_id, gift_id)
);
"""

RESET_CARD = "reset_card"
"""What a draw gives that is not a gift."""


class GiftsClosed(Exception):
    """Gifts are not open: what the user has can be read, but nothing done with it."""

    def __init__(self) -> None:
        super().__init__("礼物暂时没有开放")


class NoDraws(Exception):
    """The user has no draw chances left."""

    def __init__(self) -> None:
        super().__init__("没有抽奖次数了，明天 0:00 再发 1 次")


@dataclass(frozen=True)
class Drawn:
    """What drawing gave, in the order drawn (a gift's identifier each, or `RESET_CARD`),
    and how many chances are left."""

    drawn: list[str]
    draws: int

    def shown(self) -> dict:
        """As the browser is told it."""
        return {
            "drawn": [
                {"kind": "reset_card"} if d == RESET_CARD else {"kind": "gift", "gift_id": d}
                for d in self.drawn
            ],
            "draws": self.draws,
        }


@dataclass(frozen=True)
class GiftState:
    """What the user has, as the gifts page shows it, and whether gifts are open."""

    open: bool
    draws: int
    backpack: list[tuple[str, int]]
    """Each gift the user has, in catalog order, and how many."""
    reset_cards: int
    characters: list[dict]
    """Each character's affinity with the user, for choosing whom to give to: none while
    closed, as affinity shows nothing then."""

    def shown(self) -> dict:
        """As the browser is told it."""
        return {
            "open": self.open,
            "draws": self.draws,
            "max_draws": MAX_DRAWS,
            "backpack": [{"gift_id": g, "count": n} for g, n in self.backpack],
            "reset_cards": self.reset_cards,
            "characters": self.characters,
        }


class Gifts:
    """Every user's draw chances, backpack and reset cards, kept in the database at `path`,
    next to the users they belong to."""

    def __init__(
        self,
        path: Path,
        clock: Clock,
        is_open: Callable[[], bool],
        affinities: Affinities,
        characters: dict[str, Character],
        catalog: dict[str, Gift],
        random: Random,
    ) -> None:
        """`is_open` tells whether gifts are open now (the live configuration's affinity
        switch); draws take their numbers from `random`. Notices whether they have opened
        since last noticed."""
        self._db = connect(path)
        self._lock = threading.Lock()
        self._clock = clock
        self._is_open = is_open
        self._affinities = affinities
        self._characters = characters
        self._catalog = catalog
        self._random = random
        with self._lock, self._db:
            self._db.executescript(_SCHEMA)
        self.notice()

    def notice(self) -> None:
        """Keep when gifts opened, if they were closed when last noticed and are open now:
        as the backend starts and whenever the configuration changes."""
        is_open = self._is_open()
        with self._lock, self._db:
            row = self._db.execute("SELECT open FROM gifts_opened WHERE id = 1").fetchone()
            if row is not None and bool(row[0]) == is_open:
                return
            if is_open:
                self._db.execute(
                    "INSERT OR REPLACE INTO gifts_opened (id, open, opened_at) VALUES (1, 1, ?)",
                    (self._clock().isoformat(),),
                )
            else:
                self._db.execute(
                    "INSERT INTO gifts_opened (id, open) VALUES (1, 0)"
                    " ON CONFLICT (id) DO UPDATE SET open = 0"
                )

    def state(self, user_id: str, timezone: str) -> GiftState:
        """What the user has now, having been given the draw chances due by the producer's
        own day in `timezone`, if gifts are open. Notices first whether they have opened,
        as the switch may have just been turned on and not yet noticed."""
        self.notice()
        is_open = self._is_open()
        with self._lock, self._db:
            if is_open:
                self._give(user_id, local_date(self._clock(), timezone), timezone)
            row = self._db.execute(
                "SELECT draws, reset_cards FROM gift_balances WHERE user_id = ?", (user_id,)
            ).fetchone()
            held = dict(
                self._db.execute(
                    "SELECT gift_id, count FROM gift_backpacks WHERE user_id = ? AND count > 0",
                    (user_id,),
                ).fetchall()
            )
        draws, reset_cards = row or (0, 0)
        backpack = [(g, held[g]) for g in self._catalog if g in held]
        statuses = (
            (character_id, self._affinities.status(user_id, character_id))
            for character_id in (self._characters if is_open else ())
        )
        characters = [
            {"id": character_id, "cooling": status.cooling} | status.shown()
            for character_id, status in statuses
            if status is not None
        ]
        return GiftState(is_open, draws, backpack, reset_cards, characters)

    def draw(self, user_id: str, timezone: str, *, all: bool = False) -> Drawn:
        """Draw once, or as many times as the user has chances if `all`, having been given
        the chances due by the producer's own day in `timezone`; in one go, so that two
        drawing at once draw no more than there are chances. Raises GiftsClosed if gifts
        are not open, NoDraws if there are no chances to draw."""
        self.notice()
        if not self._is_open():
            raise GiftsClosed()
        with self._lock, self._db:
            self._give(user_id, local_date(self._clock(), timezone), timezone)
            (draws,) = self._db.execute(
                "SELECT draws FROM gift_balances WHERE user_id = ?", (user_id,)
            ).fetchone()
            if draws == 0:
                raise NoDraws()
            drawn = [self._draw_one() for _ in range(draws if all else 1)]
            for d in drawn:
                if d == RESET_CARD:
                    self._db.execute(
                        "UPDATE gift_balances SET reset_cards = reset_cards + 1"
                        " WHERE user_id = ?",
                        (user_id,),
                    )
                else:
                    self._db.execute(
                        "INSERT INTO gift_backpacks (user_id, gift_id, count) VALUES (?, ?, 1)"
                        " ON CONFLICT (user_id, gift_id) DO UPDATE SET count = count + 1",
                        (user_id, d),
                    )
            left = draws - len(drawn)
            self._db.execute(
                "UPDATE gift_balances SET draws = ? WHERE user_id = ?", (left, user_id)
            )
        return Drawn(drawn, left)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def _give(self, user_id: str, today: date, timezone: str) -> None:
        """Give the user the draw chances due by `today`: one if they have none yet; else
        one for each day since they were last given, counted from the day before gifts
        last opened if they opened since, up to the most kept. Called holding the lock, in
        a transaction."""
        row = self._db.execute(
            "SELECT draws, given_on FROM gift_balances WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            self._db.execute(
                "INSERT INTO gift_balances (user_id, draws, given_on) VALUES (?, ?, ?)",
                (user_id, DRAWS_PER_DAY, today.isoformat()),
            )
            return
        draws, given_on = row[0], date.fromisoformat(row[1])
        if today <= given_on:
            return
        since = given_on
        opened = self._opened_on(timezone)
        if opened is not None and opened > given_on:
            since = opened - timedelta(days=1)
        due = (today - since).days * DRAWS_PER_DAY
        self._db.execute(
            "UPDATE gift_balances SET draws = ?, given_on = ? WHERE user_id = ?",
            (max(draws, min(draws + due, MAX_DRAWS)), today.isoformat(), user_id),
        )

    def _draw_one(self) -> str:
        """What one draw gives: `RESET_CARD`, or the identifier of a gift not retired."""
        number = self._random(100)
        kind = next(
            k for k, upto in zip(DRAW_ODDS, accumulate(DRAW_ODDS.values())) if number < upto
        )
        if kind == RESET_CARD:
            return RESET_CARD
        pool = [g.id for g in self._catalog.values() if g.rarity == kind and not g.retired]
        return pool[self._random(len(pool))]

    def _opened_on(self, timezone: str) -> date | None:
        """The producer's own day gifts last opened on, in `timezone`; None if never
        noticed opening."""
        row = self._db.execute("SELECT opened_at FROM gifts_opened WHERE id = 1").fetchone()
        if row is None or row[0] is None:
            return None
        return local_date(datetime.fromisoformat(row[0]), timezone)
