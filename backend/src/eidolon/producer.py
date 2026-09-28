"""The producer profile and what it tells the character about the user.

A profile field left unset keeps its default: the character sheet decides how
the character addresses the producer, the producer is the man of the original
story, and the time zone is the one the user's device reports (Asia/Shanghai
when it reports none). The profile only shapes how the character treats the
user now; the stories she recalls stay as they happened.
"""

from dataclasses import dataclass
from datetime import date, datetime
from functools import cache
from typing import Literal
from zoneinfo import ZoneInfo, available_timezones

Gender = Literal["male", "female"]

DEFAULT_TIMEZONE = "Asia/Shanghai"
MAX_FORM_OF_ADDRESS_LENGTH = 20

_GENDER_NAMES: dict[Gender, str] = {"male": "男性", "female": "女性"}
_WEEKDAYS = "一二三四五六日"


@dataclass(frozen=True)
class ProducerProfile:
    form_of_address: str | None = None
    gender: Gender | None = None
    timezone: str | None = None


@cache
def _known_timezones() -> frozenset[str]:
    # The server's own local time is no place a user lives in.
    return frozenset(available_timezones() - {"localtime", "Factory"})


def is_timezone(name: str) -> bool:
    """Whether `name` is an IANA time zone, such as Asia/Tokyo."""
    return name in _known_timezones()


def effective_timezone(profile: ProducerProfile, device_timezone: str | None) -> str:
    """The profile's time zone if set, else the device's, else Asia/Shanghai.

    Either may name a zone this server does not know (tzdata drops or renames
    zones now and then); such a zone is passed over rather than failing the turn.
    """
    for timezone in (profile.timezone, device_timezone):
        if timezone and is_timezone(timezone):
            return timezone
    return DEFAULT_TIMEZONE


def local_date(now: datetime, timezone: str) -> date:
    """The day it is at `now` where the producer is: the day `producer_prompt` tells."""
    return now.astimezone(ZoneInfo(timezone)).date()


def producer_prompt(profile: ProducerProfile, now: datetime, timezone: str) -> str:
    """The prompt section about the user: who they are, and the time where they are."""
    lines = ["# 制作人", "和你对话的是你的制作人，也就是 283 事务所的制作人。"]
    if profile.form_of_address:
        lines.append(
            f"制作人希望你称呼对方为「{profile.form_of_address}」。这只是叫法，"
            "对方仍然是你的制作人；请按你自己的性格和习惯，在合适的时候这样称呼。"
        )
    if profile.gender:
        lines.append(
            f"制作人是{_GENDER_NAMES[profile.gender]}。这只影响你现在怎么对待对方；"
            "回忆原作剧情时，剧情中发生过的事保持原样，不要改写。"
        )
    else:
        lines.append("制作人是男性，和原作一致。")
    local = now.astimezone(ZoneInfo(timezone))
    lines.append(
        f"现在是 {local.year}年{local.month}月{local.day}日"
        f"（星期{_WEEKDAYS[local.weekday()]}）{local:%H:%M}（制作人所在时区 {timezone}）。"
    )
    return "\n".join(lines)
