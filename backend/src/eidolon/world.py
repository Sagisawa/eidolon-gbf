"""The world setting: the facts of the original that belong to no one character, from the
data file `eidolon world sync` writes (`world_sync`) beside the character configuration.

The file holds the date the data runs to, the office's president and clerk, the idols
(with their CV, which is only for telling which lives an idol stood on and for people
checking the data: it never reaches a prompt, ADR-0008) and the eight units, each entry
with the URLs it came from. Every character is one of its idols, matched by display
name; without the file, characters go without the world setting.

Every turn carries the world setting in full, after the character sheet
(`World.prompt`), with the rules for facts of the original that the data does not have.
"""

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from eidolon.characters import Character

WORLD_FILE = "world.json"
"""The data file's name, in the directory of the character configuration."""


class WorldError(RuntimeError):
    """The data file cannot be read, or a character is not one of its idols."""


@dataclass(frozen=True)
class Staff:
    name: str
    reading: str
    position: str
    """社長, 事務員."""
    sources: tuple[str, ...]


@dataclass(frozen=True)
class Idol:
    name: str
    """Her full name in Japanese, without a space, e.g. 櫻木真乃."""
    reading: str
    unit: str | None
    """The name of her unit; None only if the sources could not agree on one."""
    cv: str | None
    """Her CV: never in a prompt."""
    sources: tuple[str, ...]


@dataclass(frozen=True)
class Unit:
    name: str
    reading: str | None
    members: tuple[str, ...]
    sources: tuple[str, ...]


@dataclass(frozen=True)
class World:
    as_of: date
    """The day the data was imported: the characters know nothing after it."""
    office: str
    staff: tuple[Staff, ...]
    units: tuple[Unit, ...]
    idols: tuple[Idol, ...]

    def idol(self, name: str) -> Idol | None:
        return next((idol for idol in self.idols if idol.name == name), None)

    def check_characters(self, characters: dict[str, Character], path: Path) -> None:
        """Raises WorldError naming the first character who is none of the idols."""
        for character in characters.values():
            if self.idol(character.name) is None:
                raise WorldError(
                    f"角色 {character.id} 的显示名「{character.name}」在世界设定资料 {path} 的偶像名单里找不到"
                    "（显示名要和资料里的日文全名一致，例如「櫻木真乃」）"
                )

    def prompt(self) -> str:
        """The world setting as every turn carries it. No CV is in it."""
        as_of = f"{self.as_of.year}年{self.as_of.month}月{self.as_of.day}日"
        lines = [
            "# 世界设定",
            f"以下是你所在的{self.office}的基本情况，资料截止到 {as_of}。",
            "",
        ]
        for staff in self.staff:
            reading = f"（{staff.reading}）" if staff.reading else ""
            lines.append(f"{staff.position}：{staff.name}{reading}")
        lines += ["", "事务所的组合和成员（每位偶像只属于一个组合）："]
        for unit in self.units:
            reading = f"（{unit.reading}）" if unit.reading else ""
            lines.append(f"- {unit.name}{reading}：{'、'.join(unit.members)}")
        lines += [
            "",
            "关于作品里的事实：",
            "- 歌曲、唱片、演出，上面的资料里查不到的，就老实说一时想不起来；"
            "既不说「没有这回事」，也不顺着对方的说法附和、编下去。",
            "- 不引用歌词，也不编造歌词。被要求唱或念歌词时，用你自己的方式岔开，比如说想在舞台上唱给他听。",
            "- 关于演出，你只知道名称、日期、会场、出演者和曲目这类事实，不编造台上发生了什么（MC、现场的情节等）。",
            "- 不谈论声优，也不知道「中の人」这回事；被问到时按你自己的性格应对，不说出任何人的名字。",
            "- 不谈论具体的周边商品（立牌、徽章之类），被问到时按你自己的性格应对，不编造商品。",
            f"- {as_of}以后的事（新的歌曲、唱片、演出、新来的偶像等）你一概不知道，被问到就说还没听说。",
        ]
        return "\n".join(lines)

    def to_json(self) -> dict:
        return {
            "as_of": self.as_of.isoformat(),
            "office": {"name": self.office, "staff": [asdict(s) for s in self.staff]},
            "units": [asdict(u) for u in self.units],
            "idols": [asdict(i) for i in self.idols],
        }

    @classmethod
    def from_json(cls, data: dict) -> "World":
        return cls(
            as_of=date.fromisoformat(data["as_of"]),
            office=data["office"]["name"],
            staff=tuple(
                Staff(s["name"], s["reading"], s["position"], tuple(s["sources"]))
                for s in data["office"]["staff"]
            ),
            units=tuple(
                Unit(u["name"], u["reading"], tuple(u["members"]), tuple(u["sources"]))
                for u in data["units"]
            ),
            idols=tuple(
                Idol(i["name"], i["reading"], i["unit"], i["cv"], tuple(i["sources"]))
                for i in data["idols"]
            ),
        )


def world_path(characters_path: Path) -> Path:
    """Where the data file is: beside the character configuration."""
    return characters_path.parent / WORLD_FILE


def load_world(path: Path) -> World | None:
    """The data file at `path`; None if there is none. Raises WorldError if it is broken."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise WorldError(f"世界设定资料 {path} 格式有误：{e}") from None
    try:
        return World.from_json(data)
    except (KeyError, TypeError, ValueError) as e:
        raise WorldError(f"世界设定资料 {path} 缺少或写错了字段：{e!r}（重新运行 eidolon world sync）") from None
