"""Importing the story corpus from SCTranslationData CSV files.

Each CSV (`id,name,text,trans`, ending in an `info` row naming the game script it
was translated from) becomes one episode keyed by that script. The source
(card or event) is the file's directory and the title its file name, as
SCTranslationData lays them out. Only canon is kept: failure endings are
recognised by their script and left out (and removed, if an earlier import had
them), and the producer's choices (`select` rows) are dropped so the corpus never
says which one was picked. The cast is every configured character whose speaker
name appears; the producer and other people are not cast.
"""

import csv
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from eidolon.characters import Character
from eidolon.corpus import Episode, Line, StoryCorpus

log = logging.getLogger(__name__)

_BATCH = 32
"""Episodes saved (and embedded) together."""

_JOINT_SPEAKERS = re.compile(r"[＆&]")

# Script identifiers look like `produce_events/TIIISSSEE`: type T, idol III, scenario
# SSS (001 W.I.N.G., 002 fan appreciation, 003 G.R.A.D., 004 Landing Point, 005
# S.T.E.P.), episode EE. These are the scripts only reached by losing.
_FAILURE_ENDINGS = [
    re.compile(p)
    for p in (
        r"produce_events/7\d{3}001(02|04|06|08)",  # W.I.N.G. season not cleared
        r"produce_events/6\d{3}001(02|07)",  # W.I.N.G. knocked out, lost the final
        r"produce_events/6\d{3}003(03|06|09|10)",  # G.R.A.D. lost a round
        r"produce_events/1\d{3}003(071|072|08)",  # G.R.A.D. elimination route
        r"produce_communication_auditions/\d+2",  # lost an audition
        r"produce_communication_promise_results/\d+2",  # broke a promise
    )
]

_CATEGORIES = [
    (re.compile(r"produce_events/2"), "P卡剧情"),
    (re.compile(r"produce_events/3"), "S卡剧情"),
    (re.compile(r"produce_"), "培育剧情"),
    (re.compile(r"game_event_communications/"), "活动剧情"),
    (re.compile(r"special_communications/"), "特别剧情"),
    (re.compile(r"mypage_communications/"), "主页剧情"),
    (re.compile(r"business_unit_communication/"), "营业剧情"),
]


def is_failure_ending(source_id: str) -> bool:
    return any(p.fullmatch(source_id) for p in _FAILURE_ENDINGS)


def category_of(source_id: str) -> str:
    return next((name for p, name in _CATEGORIES if p.match(source_id)), "其他剧情")


@dataclass
class ImportReport:
    imported: int = 0
    skipped_failures: int = 0
    removed: int = 0
    """Episodes an earlier import had that are now recognised as failure endings."""
    embedded_passages: int = 0
    warnings: list[str] = field(default_factory=list)


async def import_csv_directory(
    directory: Path, corpus: StoryCorpus, characters: Iterable[Character]
) -> ImportReport:
    """Import every `*.csv` under `directory` as an episode.

    Of several files translated from the same script, the first in path order wins.
    """
    speakers = _speaker_index(characters)
    report = ImportReport()
    episodes: dict[str, Episode] = {}
    seen: dict[str, Path] = {}
    for path in sorted(directory.rglob("*.csv")):
        relative = path.relative_to(directory)
        try:
            source_id, lines = _read_csv(path)
        except (csv.Error, UnicodeDecodeError) as e:
            report.warnings.append(f"{relative}：无法读取（{e}），已跳过")
            continue
        if source_id is None:
            source_id = f"csv/{relative.with_suffix('').as_posix()}"
            report.warnings.append(f"{relative}：没有 info 行，以文件路径作为来源标识")
        if source_id in seen:
            report.warnings.append(
                f"{relative}：与 {seen[source_id]} 来源相同（{source_id}），以前者为准"
            )
            continue
        seen[source_id] = relative

        if is_failure_ending(source_id):
            report.skipped_failures += 1
            if corpus.remove(source_id):
                report.removed += 1
            continue
        episodes[source_id] = Episode(
            id=source_id,
            category=category_of(source_id),
            source=relative.parent.name or relative.stem,
            title=relative.stem,
            cast=_cast(lines, speakers),
            lines=tuple(lines),
        )

    batch = list(episodes.values())
    for start in range(0, len(batch), _BATCH):
        report.embedded_passages += await corpus.save(batch[start : start + _BATCH])
        report.imported += len(batch[start : start + _BATCH])
        log.info("imported %d of %d episodes", report.imported, len(batch))
    return report


def _read_csv(path: Path) -> tuple[str | None, list[Line]]:
    """The script the file was translated from, and its lines."""
    source_id = None
    lines: list[Line] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            row = [cell.strip() for cell in row] + [""] * (4 - len(row))
            line_id, name, text, trans = row[:4]
            if line_id == "info":
                source_id = name.removesuffix(".json") or None
            elif line_id in ("id", "select", "译者") or not text:
                continue  # header, the producer's choices, translator credit
            else:
                lines.append(Line(name or None, _unescape(text), _unescape(trans) or None))
    return source_id, lines


def _unescape(text: str) -> str:
    return text.replace("\\n", "\n")


def _speaker_index(characters: Iterable[Character]) -> dict[str, str]:
    index = {}
    for character in characters:
        if not character.speakers:
            log.warning("character %s has no speakers configured; she is never cast", character.id)
        for name in character.speakers:
            index[name] = character.id
    return index


def _cast(lines: Iterable[Line], speakers: dict[str, str]) -> frozenset[str]:
    cast = set()
    for line in lines:
        for name in _JOINT_SPEAKERS.split(line.speaker or ""):
            if (character := speakers.get(name.strip())) is not None:
                cast.add(character)
    return frozenset(cast)
