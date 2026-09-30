"""Each configured character's outfit list (CONTEXT.md「衣装」): `eidolon stand outfits`.

The Spine mirror's `spine_manifest.json` lists every stand of every idol; a character
with an `idol_id` gets a list of her cards, in the order of their enzaIds, which is the
order the game released them. A card has her everyday clothes on it (`stand`) and its
stage costume (`stand_costume`), each of which it may lack; when the two textures are
the same byte for byte (most Special cards) they are one outfit, listed as her everyday
clothes (whatever her default outfit is, so that the list does not change with it; a
default outfit left out this way is reported). The chibi stands (`cb`,
`cb_costume`) are left out, and so is an outfit the mirror lists without its files.

A card is named as in the game without the 【】 or her name: 【ほわっとスマイル】櫻木真乃
is ほわっとスマイル. The game left a few cards unnamed (【】櫻木真乃); those go by hers.

The list is written to `outfits/<idol_id>.json` in the build directory, which is laid
out as the bucket is (`stand_upload`):

    {"idol_id": 1, "cards": [{"id": "1030010010", "name": "ナチュラルモード", "type": "P_SR",
      "everyday": {"id": "stand/1030010010", "url": "../spine/idols/stand/1030010010/",
                   "thumbnail": "../thumbnails/stand/1030010010.png"},
      "stage": {...} or null}]}

`url` and `thumbnail` are relative to the list itself.
"""

import json
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from eidolon.characters import Character

CATEGORIES = ("stand", "stand_costume")
"""Her everyday clothes on a card, and its stage costume."""
OUTFIT_FILES = ("data.json", "data.atlas", "data.png")
MANIFEST = "spine_manifest.json"
LISTS_DIR = "outfits"
THUMBNAILS_DIR = "thumbnails"

_BRACKETED = re.compile(r"【(?P<name>[^】]*)】")


class MirrorLayoutError(RuntimeError):
    """The mirror is not where it was said to be, or not as the manifest lays it out."""


def outfit_path(outfit_id: str) -> str:
    """Where an outfit's files are in the mirror's `assets` and in the bucket."""
    return f"spine/idols/{outfit_id}/"


def outfit_directory(mirror: Path, outfit_id: str) -> Path:
    """Where an outfit's files are in the mirror."""
    return mirror / "assets" / outfit_path(outfit_id)


def thumbnail_path(outfit_id: str) -> str:
    """Where an outfit's thumbnail is in the build directory and in the bucket."""
    return f"{THUMBNAILS_DIR}/{outfit_id}.png"


def list_path(idol_id: int) -> str:
    """Where an idol's outfit list is in the build directory and in the bucket."""
    return f"{LISTS_DIR}/{idol_id}.json"


@dataclass(frozen=True)
class Card:
    id: str
    """The card's enzaId."""
    name: str
    type: str
    """Its rarity or kind, as the manifest's `dressType`: P_SSR, Special, Mizugi..."""
    everyday: str | None
    """Her everyday clothes on the card, e.g. `stand/1030010010`."""
    stage: str | None
    """Its stage costume, e.g. `stand_costume/1030010010`."""

    @property
    def outfits(self) -> list[str]:
        return [outfit for outfit in (self.everyday, self.stage) if outfit is not None]


@dataclass(frozen=True)
class OutfitList:
    idol_id: int
    character: str
    """Her name, for the report."""
    cards: list[Card]

    @property
    def outfits(self) -> list[str]:
        return [outfit for card in self.cards for outfit in card.outfits]

    def to_json(self) -> dict:
        return {
            "idol_id": self.idol_id,
            "cards": [
                {
                    "id": card.id,
                    "name": card.name,
                    "type": card.type,
                    "everyday": _outfit_json(card.everyday),
                    "stage": _outfit_json(card.stage),
                }
                for card in self.cards
            ],
        }


def _outfit_json(outfit_id: str | None) -> dict | None:
    if outfit_id is None:
        return None
    return {
        "id": outfit_id,
        "url": f"../{outfit_path(outfit_id)}",
        "thumbnail": f"../{thumbnail_path(outfit_id)}",
    }


@dataclass
class OutfitsReport:
    lists: list[OutfitList] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def make_outfit_lists(mirror: Path, build: Path, characters: Iterable[Character]) -> OutfitsReport:
    """Write the outfit list of every character with an idol to `build`, from the mirror
    at `mirror` (the directory with `spine_manifest.json` and `assets/`)."""
    entries = _read_manifest(mirror)
    report = OutfitsReport()
    for character in characters:
        if character.idol_id is None:
            continue
        outfits = _list_outfits(mirror, entries, character, report.warnings)
        if character.default_outfit is not None and character.default_outfit not in outfits.outfits:
            report.warnings.append(
                f"{character.name} 的 default_outfit {character.default_outfit} 不在她的衣装清单里"
                "（镜像里没有这套，或者它和同一张卡的私服贴图相同、只记了私服），不会上传，"
                "通话层会退回背景图；改成清单里有的一套"
            )
        _write_json(build / list_path(character.idol_id), outfits.to_json())
        report.lists.append(outfits)
    return report


def _read_manifest(mirror: Path) -> list[dict]:
    path = mirror / MANIFEST
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise MirrorLayoutError(f"找不到立绘镜像的 {path}") from None
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise MirrorLayoutError(f"立绘镜像的 {path} 格式有误：{e}") from None
    if not isinstance(entries, list):
        raise MirrorLayoutError(f"立绘镜像的 {path} 应是一个列表")
    return entries


def _list_outfits(
    mirror: Path, entries: list[dict], character: Character, warnings: list[str]
) -> OutfitList:
    assert character.idol_id is not None
    cards: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise MirrorLayoutError(f"立绘镜像的 {MANIFEST} 里有一项不是对象：{entry!r}")
        if entry.get("idolId") != character.idol_id or entry.get("category") not in CATEGORIES:
            continue
        if not entry.get("enzaId"):
            raise MirrorLayoutError(f"立绘镜像的 {MANIFEST} 里有一项没有 enzaId：{entry!r}")
        enza_id = str(entry["enzaId"])
        outfit_id = f"{entry['category']}/{enza_id}"
        if not all((outfit_directory(mirror, outfit_id) / name).is_file() for name in OUTFIT_FILES):
            warnings.append(f"镜像里没有 {outfit_id}（{entry.get('dressName', '')}）的文件，没有列进衣装清单")
            continue
        card = cards.setdefault(enza_id, {"entry": entry, "outfits": {}})
        card["outfits"][entry["category"]] = outfit_id

    listed = []
    for enza_id, card in sorted(cards.items()):
        everyday = card["outfits"].get("stand")
        stage = card["outfits"].get("stand_costume")
        if everyday and stage and _same_texture(mirror, everyday, stage):
            stage = None
        entry = card["entry"]
        listed.append(
            Card(
                id=enza_id,
                name=card_name(str(entry.get("dressName", "")), character.name),
                type=str(entry.get("dressType", "")),
                everyday=everyday,
                stage=stage,
            )
        )
    return OutfitList(character.idol_id, character.name, listed)


def _same_texture(mirror: Path, first: str, second: str) -> bool:
    first_png, second_png = (outfit_directory(mirror, o) / "data.png" for o in (first, second))
    return first_png.read_bytes() == second_png.read_bytes()


def card_name(dress_name: str, character_name: str) -> str:
    """The card's name as in the game, without the 【】 or her name; hers if it has none."""
    match = _BRACKETED.search(dress_name)
    name = match["name"].strip() if match else ""
    return name or character_name


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    partial.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(partial, path)
