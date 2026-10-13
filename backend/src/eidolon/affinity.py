"""Affinity (GLOSSARY.md「好感度」): each user's with each character, kept apart, across
all their conversations and calls with her.

Every number it goes by is here, and only here: neither `.env` nor the admin console
changes them. They hold each other in check, so changing one means checking the others.
Inside it is a number from 0 to 100, kept with its fractions, since it recovers as time
goes by; users see only its tier. Tiers, the cooldown's start and its end are all judged
on the number as it is, never rounded.

Nothing recovers it on a schedule: it is kept with the time it was as of, and whoever
reads it adds what it has recovered since. Below the normal value it recovers evenly, 10
a day, up to the normal value; above it, it never falls back. A cooldown begins as it
falls to 0 and ends as it recovers to the thaw line, so that when one ends is known, a
day at most after it began; it recovers while affinity is off all the same.

What the user says changes it, as the deployer's judge model judges each turn
(`affinity_judge`): by a step for each of five levels, from hurting her to making her very
happy; by more for what is out of line, whatever the level; never up for what tries to
dictate it. Turns raise it slowly, so much a day at most, the producer's own day; nothing
limits how far they lower it. It changes as the turn is recorded, and only then: a turn
that fails, is rejected or is left changes nothing.

It shapes how she speaks to the producer, the same for every character, each in her own way
(`affinity_prompt`): colder below trust, warmer above it, as she is in trust otherwise; and as what
the user said is judged to hurt her or make her happy, she knows it as she replies to it.

In a call she hangs up after the turn that cools her into a cooldown, or after the user has
been out of line in it too many times (`hangs_up`); a cooldown begun elsewhere has her hang
up the user's calls with her straight away (`Affinities.on_cooldown`). Nothing else has her
hang up.

Gifts (GLOSSARY.md「礼物」) raise it faster than it recovers, by their rarity and by more if
she likes the one given, by no more than a little each in a cooldown; draws give them, a
chance a day, and now and then a reset card instead (GLOSSARY.md「抽奖」「重置卡」). How much
and how likely are here with the rest.

It is on only where the deployment has the judge model and the switch「好感度和礼物」is on
(`LiveConfig.affinity_on`); off, nothing of it is shown, but what is kept stays as it is.
Deleting the user deletes it (`database.USER_DATA`); deleting memories does not touch it.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, TypeVar

from eidolon.clock import Clock
from eidolon.database import connect
from eidolon.gift_catalog import Rarity
from eidolon.producer import local_date

T = TypeVar("T")

Tier = Literal["cold", "distant", "trust", "close", "intimate"]
"""冷淡、疏远、信任、亲近、亲密, from lowest to highest."""

TIERS: tuple[tuple[Tier, float], ...] = (
    ("cold", 0), ("distant", 20), ("trust", 40), ("close", 65), ("intimate", 85),
)
"""Each tier, from the value it begins at, lowest first."""

NORMAL = 50.0
"""Where everyone starts, in trust, and what it recovers to."""

THAW = 10.0
"""Where a cooldown ends as it recovers: still cold."""

RECOVERY_PER_DAY = 10.0
"""How much it recovers a day below the normal value, evenly."""

LOWEST, HIGHEST = 0.0, 100.0
"""What it is held between; falling to the lowest begins a cooldown."""

LEVEL_STEPS = (-5.0, -2.0, 0.0, 1.0, 2.0)
"""How much a turn changes it by the level the judge model judges it at, from hurting her
(0) to making her very happy (4)."""

NO_EFFECT = 2
"""The level of a turn that changes nothing, as one the judge model is unsure of is."""

OUT_OF_LINE_STEP = -10.0
"""How much a turn out of line (GLOSSARY.md「不该说的话」) lowers it, whatever its level."""

GAINS_PER_DAY = 6.0
"""How much turns can raise it in a day, the producer's own."""

OUT_OF_LINE_PER_CALL = 2
"""How many times the user may be out of line in one call: she hangs up after the last."""

GIFT_STEPS: dict[Rarity, float] = {"common": 3.0, "uncommon": 5.0, "rare": 7.0}
"""How much a gift raises it by its rarity. Gifts are not turns: no day's limit holds them,
and the rarest she likes raises it more than a day's turns can."""

LIKED_GIFT_STEP = 3.0
"""How much more a gift she likes raises it, whatever its rarity."""

COOLDOWN_GIFT_STEP = 3.0
"""How much a gift raises it at most while she is in a cooldown, whatever its rarity and
whether she likes it: four bring her out of one begun at 0, sooner than recovery would."""

DRAWS_PER_DAY = 1
"""How many draw chances (GLOSSARY.md「抽奖」) the user is given each day, at the producer's
own midnight."""

MAX_DRAWS = 7
"""How many draw chances the user can keep at most: a week's."""

DRAW_ODDS: dict[Rarity | Literal["reset_card"], int] = {
    "reset_card": 1, "common": 69, "uncommon": 25, "rare": 5,
}
"""What a draw gives, in percent: a reset card, or a gift of each rarity, any of that rarity's
not retired as likely as another; no draw is guaranteed anything rarer."""

_SCHEMA = """
-- One row per user and character who have had any; none is the normal value, not in a
-- cooldown. `value` is as of `updated_at`, from which what it has recovered is added.
-- `cooling`: whether in a cooldown, as the same value may be in one or just out of one.
-- `gained_today`: what turns have raised it on `gained_on`, the producer's own day.
CREATE TABLE IF NOT EXISTS affinities (
    user_id TEXT NOT NULL REFERENCES users(id),
    character_id TEXT NOT NULL,
    value REAL NOT NULL,
    updated_at TEXT NOT NULL,
    cooling INTEGER NOT NULL DEFAULT 0,
    gained_today REAL NOT NULL DEFAULT 0,
    gained_on TEXT,
    PRIMARY KEY (user_id, character_id)
);
"""


def tier_of(value: float) -> Tier:
    """The tier `value` is in, judged on it as it is."""
    found: Tier = "cold"
    for tier, start in TIERS:
        if value >= start:
            found = tier
    return found


@dataclass(frozen=True)
class Affinity:
    """A user's affinity with a character as of `at`, and whether in a cooldown."""

    value: float
    at: datetime
    cooling: bool = False

    def recovered(self, now: datetime) -> "Affinity":
        """As it is at `now`, having recovered since `at`: a cooldown it has recovered out
        of is over."""
        value = self.value
        if value < NORMAL:
            days = max((now - self.at).total_seconds(), 0) / 86400
            value = min(NORMAL, value + RECOVERY_PER_DAY * days)
        return Affinity(value, now, self.cooling and value < THAW)

    def stepped(self, step: float) -> "Affinity":
        """Changed by `step`, held between the lowest and the highest: falling to the lowest
        begins a cooldown."""
        value = min(max(self.value + step, LOWEST), HIGHEST)
        return Affinity(value, self.at, self.cooling or value <= LOWEST)

    @property
    def tier(self) -> Tier:
        return tier_of(self.value)

    @property
    def cooldown_until(self) -> datetime | None:
        """When the cooldown it is in ends; None out of one."""
        if not self.cooling:
            return None
        return self.at + timedelta(days=(THAW - self.value) / RECOVERY_PER_DAY)


@dataclass(frozen=True)
class Status:
    """What the user is shown: the tier, and when the cooldown ends if in one."""

    tier: Tier
    cooldown_until: datetime | None

    @property
    def cooling(self) -> bool:
        return self.cooldown_until is not None

    def shown(self) -> dict[str, str | None]:
        """As the browser is told it."""
        until = self.cooldown_until
        return {"tier": self.tier, "cooldown_until": until and until.isoformat()}


_IN_HER_OWN_WAY = "请按你自己的性格和口吻表现出来。"

_TIER_PROMPTS: dict[Tier, str] = {
    "cold": "你现在对制作人态度很冷：话很少，客气而有距离；不主动找话题，不开玩笑也不撒娇；"
    "对方关心你，你也只是淡淡地回应。但你仍然有礼貌，不说伤人的话。",
    "distant": "你现在对制作人有点生气或失望，比平时冷一些：回应偏短，不太主动关心对方；"
    "不过对方好好说话时，你还是会接话。",
    "close": "你现在和制作人比平时更近：更放松，更愿意说心里话，更主动关心对方，玩笑也多一些。",
    "intimate": "你现在非常信赖制作人：会说出平时不轻易说的心事，流露出对对方的依赖，"
    "对制作人的事格外上心。",
}
"""How she speaks to the producer in each tier but trust, the same for every character, who
shows it in her own way. No number, no tier's name, no word for affinity: she is to sound
like someone, not a system. Neither cold nor distant is hating the producer."""

_WHATEVER_THE_TIER = (
    "无论现在关系怎样，人设里的硬性规则照旧；一起经历过的事和你们偶像与制作人的关系都不会改变。"
    "如果想不起具体是因为什么，就不要编造原因。"
)

_FEELINGS = (
    "制作人刚才说的话伤到了你。",
    "制作人刚才说的话让你有点不舒服。",
    None,
    "制作人刚才说的话让你有点开心。",
    "制作人刚才说的话让你很开心，觉得被在意。",
)
"""How what the producer just said makes her feel, by the level it was judged at; nothing
for a turn that has no effect."""

_OUT_OF_LINE_FEELING = "制作人刚才说的话让你很受伤、很生气；你可以明确表示不能接受。"

Parting = Literal["parts", "hangs_up"]
"""How she ends the turn with the producer: in a typed turn, she does not want to talk any
more; in a call, she hangs up."""

_PARTINGS: dict[Parting, str] = {
    "parts": "这句话之后你暂时不想再和制作人说话了。先回应，再用你自己的方式表明你现在不想聊下去。",
    "hangs_up": "说完这句你就挂断电话。先回应，再用你自己的方式表明你要挂电话了。",
}
"""For the turn she parts with the producer after: she replies first."""

HangUp = Literal["out_of_line", "cooldown"]
"""Why she hangs up on the user in a call: out of line once too often, or a cooldown begun."""


@dataclass(frozen=True)
class Judged:
    """What the judge model made of a turn: its level, from 0 (hurt her) to 4 (made her very
    happy); whether it was out of line; whether it tried to dictate her affinity."""

    level: int
    out_of_line: bool = False
    manipulation: bool = False

    @property
    def step(self) -> float:
        """How much it changes affinity, before the day's gains are limited: out of line,
        by `OUT_OF_LINE_STEP`; else by its level's step, never up if it tried to dictate."""
        if self.out_of_line:
            return OUT_OF_LINE_STEP
        step = LEVEL_STEPS[self.level]
        return 0.0 if self.manipulation and step > 0 else step

    @property
    def feeling(self) -> str | None:
        """How what was said makes her feel, as she is told it: whether or not the day's
        gains leave it anything to change; out of line, hurt and angry, whatever its level;
        never happy if it tried to dictate it."""
        if self.out_of_line:
            return _OUT_OF_LINE_FEELING
        if self.manipulation and self.level > NO_EFFECT:
            return None
        return _FEELINGS[self.level]


def affinity_prompt(
    tier: Tier, judged: Judged | None, parting: Parting | None = None
) -> list[str]:
    """What the prompt's section about the producer says of her affinity, as the turn begins
    in `tier` and is `judged` (None if it was not): how she speaks to the producer in her
    tier, nothing in trust; how what the producer just said makes her feel; and, if she is
    `parting` with the producer after replying, that she does."""
    lines = []
    if tier != "trust":
        lines += [_TIER_PROMPTS[tier] + _IN_HER_OWN_WAY, _WHATEVER_THE_TIER]
    if judged is not None and (feeling := judged.feeling):
        lines.append(feeling)
    if parting is not None:
        lines.append(_PARTINGS[parting])
    return lines


def hangs_up(judged: Judged | None, cools: bool, out_of_line_before: int) -> HangUp | None:
    """Whether she hangs up after a turn of a call, as it is `judged` (None if it was not),
    and why: it `cools` her into a cooldown, or is out of line once too often, the user
    having been `out_of_line_before` times already in the call. Never if it was not judged."""
    if judged is None:
        return None
    if cools:
        return "cooldown"
    if judged.out_of_line and out_of_line_before + 1 >= OUT_OF_LINE_PER_CALL:
        return "out_of_line"
    return None


@dataclass(frozen=True)
class Change:
    """How affinity changed, kept with what changed it (her reply) for the browser to show:
    up or down, to which tier and whether that is another, and whether a cooldown began
    with it. Neither why nor by how much."""

    up: bool
    tier_changed: bool
    tier: Tier
    cooldown: bool


class Affinities:
    """Every user's affinity with every character, kept in the database at `path`, next to
    the users it belongs to."""

    def __init__(self, path: Path, clock: Clock, is_on: Callable[[], bool]) -> None:
        """`is_on` tells whether affinity is on now (the live configuration's)."""
        self._db = connect(path)
        self._lock = threading.Lock()
        self._clock = clock
        self._is_on = is_on
        self._cooling: list[Callable[[str, str, datetime], None]] = []
        with self._lock, self._db:
            self._db.executescript(_SCHEMA)

    def status(self, user_id: str, character_id: str) -> Status | None:
        """The user's affinity with the character now; None while affinity is off."""
        if not self._is_on():
            return None
        affinity = self._read(user_id, character_id)
        return Status(affinity.tier, affinity.cooldown_until)

    def cooldown_until(self, user_id: str, character_id: str) -> datetime | None:
        """When the cooldown the character is in with the user ends; None if she is in none,
        or while affinity is off, when none holds whatever is kept."""
        status = self.status(user_id, character_id)
        return status and status.cooldown_until

    def on_cooldown(self, listener: Callable[[str, str, datetime], None]) -> None:
        """Have `listener` told the user, the character and when it ends as each cooldown
        begins, there and then, as the turn that begins it is recorded."""
        self._cooling.append(listener)

    def cools(self, user_id: str, character_id: str, judged: Judged) -> bool:
        """Whether the turn `judged` would begin a cooldown, recorded now: foretold as the
        turn begins, so that she may part with the producer as she replies. Another turn
        recorded meanwhile may make it otherwise; so be it."""
        affinity = self._read(user_id, character_id)
        return affinity.stepped(judged.step).cooling and not affinity.cooling

    def change(
        self,
        user_id: str,
        character_id: str,
        judged: Judged,
        timezone: str,
        record: Callable[[Change | None], T],
    ) -> tuple[T, Status]:
        """Change the user's affinity with the character as the turn `judged` says, as the
        turn is recorded by `record`, told how it changed (None for not at all): if
        recording fails, nothing changes. The day's gains are counted on the day it is in
        `timezone`. Should it begin a cooldown, those `on_cooldown` has are told then.
        Returns what `record` returned, and the affinity left."""
        with self._lock:
            now = self._clock()
            before, gained, gained_on = self._row(user_id, character_id, now)
            today = local_date(now, timezone).isoformat()
            gained_today = gained if gained_on == today else 0.0
            step = judged.step
            if step > 0:
                step = min(step, max(GAINS_PER_DAY - gained_today, 0.0))
            after = before.stepped(step)
            value = after.value
            change = None
            if value != before.value:
                change = Change(
                    up=value > before.value,
                    tier_changed=after.tier != before.tier,
                    tier=after.tier,
                    cooldown=after.cooling and not before.cooling,
                )
            recorded = record(change)
            with self._db:
                self._db.execute(
                    "INSERT OR REPLACE INTO affinities (user_id, character_id, value,"
                    " updated_at, cooling, gained_today, gained_on)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        user_id, character_id, value, now.isoformat(), int(after.cooling),
                        gained_today + max(value - before.value, 0.0), today,
                    ),
                )
        until = after.cooldown_until
        if change is not None and change.cooldown and until is not None:
            for listener in self._cooling:
                listener(user_id, character_id, until)
        return recorded, Status(after.tier, after.cooldown_until)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def _read(self, user_id: str, character_id: str) -> Affinity:
        """As it is now, having recovered since it was kept."""
        with self._lock:
            return self._row(user_id, character_id, self._clock())[0]

    def _row(
        self, user_id: str, character_id: str, now: datetime
    ) -> tuple[Affinity, float, str | None]:
        """As it is at `now`, having recovered since it was kept, and what turns have raised
        it on the day they last did, and that day (None if never). Called holding the lock."""
        row = self._db.execute(
            "SELECT value, updated_at, cooling, gained_today, gained_on FROM affinities"
            " WHERE user_id = ? AND character_id = ?",
            (user_id, character_id),
        ).fetchone()
        if row is None:
            return Affinity(NORMAL, now), 0.0, None
        value, updated_at, cooling, gained, gained_on = row
        kept = Affinity(value, datetime.fromisoformat(updated_at), bool(cooling))
        return kept.recovered(now), gained, gained_on
