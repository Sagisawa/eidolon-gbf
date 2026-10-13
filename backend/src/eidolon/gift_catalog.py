"""The gift catalog (GLOSSARY.md「礼物」), loaded from the configuration beside the
characters'.

It is configuration, not data: the maintainer keeps it in the repository as they keep the
characters, and neither `.env` nor the admin console changes it. Each gift has its
identifier (also its illustration's file name in the frontend's static files, and what
backpacks and gift records keep), its name, its category and its rarity. A gift is never
deleted once out, only retired: no draw gives it any more, but whoever has one still sees
it and can give it. Every rarity needs a gift not retired, or draws of it would come up
empty. What each rarity raises affinity by and how likely a draw is to give it are with
affinity's other numbers (`affinity`).

Anything wrong in it keeps the backend from starting (`GiftCatalogError`).
"""

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, get_args

Category = Literal["food", "drink", "flower", "trinket"]
"""吃的、饮品、花草、小物件."""

Rarity = Literal["common", "uncommon", "rare"]
"""普通、少见、稀有, from the commonest."""

GIFTS_FILE = "gifts.toml"

_VALID_ID = re.compile(r"[a-z0-9_-]+")


class GiftCatalogError(RuntimeError):
    pass


@dataclass(frozen=True)
class Gift:
    id: str
    name: str
    category: Category
    rarity: Rarity
    retired: bool = False

    def listed(self) -> dict:
        """As the gifts page reads it."""
        return {
            "id": self.id, "name": self.name, "category": self.category,
            "rarity": self.rarity, "retired": self.retired,
        }


def gifts_path(characters_path: Path) -> Path:
    """Where the gift catalog is: beside the character configuration."""
    return characters_path.parent / GIFTS_FILE


def load_gift_catalog(path: Path) -> dict[str, Gift]:
    """The gifts in the catalog at `path`, keyed by identifier in file order. Raises
    GiftCatalogError if it is missing or broken."""
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise GiftCatalogError(f"找不到礼物目录 {path}") from None
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        raise GiftCatalogError(f"礼物目录 {path} 格式有误：{e}") from None
    entries = config.get("gifts", [])
    if not isinstance(entries, list):
        raise GiftCatalogError(f"礼物目录 {path} 里的 gifts 应当是 [[gifts]] 段")

    catalog: dict[str, Gift] = {}
    for entry in entries:
        gift = _parse_gift(entry)
        if gift.id in catalog:
            raise GiftCatalogError(f"礼物标识 {gift.id} 重复")
        catalog[gift.id] = gift
    for rarity in get_args(Rarity):
        if not any(g.rarity == rarity and not g.retired for g in catalog.values()):
            raise GiftCatalogError(f"礼物目录里稀有度 {rarity} 没有一件没下架的礼物，这一档抽不出东西")
    return catalog


def _parse_gift(entry: dict) -> Gift:
    label = entry.get("id", "（没有标识）")
    missing = [f for f in ("id", "name", "category", "rarity") if f not in entry]
    if missing:
        raise GiftCatalogError(f"礼物 {label} 缺少 {'、'.join(missing)}")
    id, name, category, rarity = entry["id"], entry["name"], entry["category"], entry["rarity"]
    if not isinstance(id, str) or not _VALID_ID.fullmatch(id):
        raise GiftCatalogError(f"礼物标识 {id} 只能用小写字母、数字、- 和 _")
    if not isinstance(name, str) or not name.strip():
        raise GiftCatalogError(f"礼物 {id} 的 name 应当是一段文字")
    if category not in get_args(Category):
        raise GiftCatalogError(
            f"礼物 {id} 的类别 {category} 不在 {'、'.join(get_args(Category))} 之中"
        )
    if rarity not in get_args(Rarity):
        raise GiftCatalogError(
            f"礼物 {id} 的稀有度 {rarity} 不在 {'、'.join(get_args(Rarity))} 之中"
        )
    retired = entry.get("retired", False)
    if not isinstance(retired, bool):
        raise GiftCatalogError(f"礼物 {id} 的 retired 应当是 true 或 false")
    return Gift(id, name, category, rarity, retired)
