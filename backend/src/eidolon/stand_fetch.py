"""Fetching the stands from ShinyColorsDB (ADR-0011): `eidolon stand fetch`.

For every character with an `idol_id`, ShinyColorsDB's API is asked for her dresses each
time (new cards come out every week or two), and the files of their everyday clothes
(`stand`) and stage costumes (`stand_costume`) that the source in the build directory
lacks are downloaded from its CDN, as they are: about half the textures are WebP under a
`.png` name, which browsers read all the same. An outfit's files never change, so one
already fetched is not asked for again.

The source's `spine_manifest.json` (laid out as the old Spine mirror's, which can seed
it) lists every outfit fetched and only ever grows: a card the API stops listing, or
leaves out of an answer once, keeps its place in the outfit picker. An outfit the API
lists without a place on the CDN, or whose files the CDN does not have or sends broken,
is left out and reported, and asked for again next time. When ShinyColorsDB cannot be
reached, or answers unlike it used to, what was fetched until then is kept and listed.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from eidolon.characters import Character
from eidolon.mirror import Dress, Mirror, MirrorError
from eidolon.stand_outfits import (
    CATEGORIES,
    MANIFEST,
    OUTFIT_FILES,
    is_webp,
    outfit_directory,
    outfit_path,
    read_manifest,
    source_directory,
    write_atomically,
    write_json,
)

log = logging.getLogger(__name__)


@dataclass
class FetchReport:
    fetched: list[str] = field(default_factory=list)
    """The outfits downloaded this time, e.g. `stand/1030010010`."""
    fetched_bytes: int = 0
    skipped: list[str] = field(default_factory=list)
    """Why outfits ShinyColorsDB lists were left out this time."""
    error: str | None = None
    """Why ShinyColorsDB could not be asked for the rest, if it could not."""


async def fetch_stands(build: Path, characters: Iterable[Character], mirror: Mirror) -> FetchReport:
    source = source_directory(build)
    manifest = read_manifest(source)
    entries = {entry.get("path"): entry for entry in manifest or []}
    report = FetchReport()
    try:
        for character in characters:
            if character.idol_id is None:
                continue
            for dress in await mirror.dresses(character.idol_id):
                for category in CATEGORIES:
                    if category not in dress.stands:
                        continue
                    outfit_id = f"{category}/{dress.enza_id}"
                    if await _fetch_outfit(mirror, source, outfit_id, dress.stands[category], dress, report):
                        entries[outfit_path(outfit_id)] = {
                            "path": outfit_path(outfit_id),
                            "category": category,
                            "idolId": character.idol_id,
                            "idolName": character.name,
                            "enzaId": dress.enza_id,
                            "dressName": dress.name,
                            "dressType": dress.type,
                        }
    except MirrorError as e:
        report.error = str(e)
    finally:
        if manifest is not None or entries:  # having fetched nothing ever is not an empty source
            write_json(source / MANIFEST, [entries[path] for path in sorted(entries, key=str)])
    return report


async def _fetch_outfit(
    mirror: Mirror, source: Path, outfit_id: str, cdn_path: str | None, dress: Dress, report: FetchReport
) -> bool:
    """Whether the outfit's files are all in the source, having fetched those it lacked
    from `cdn_path` on the CDN."""
    if cdn_path is None:
        report.skipped.append(f"ShinyColorsDB 列了 {outfit_id}（{dress.name}）却没有它的文件，下次同步再试")
        return False
    directory = outfit_directory(source, outfit_id)
    downloaded = 0
    for name in OUTFIT_FILES:
        target = directory / name
        if target.is_file() and _looks_valid(name, _start_of(target)):
            continue
        content = await mirror.stand_file(f"{cdn_path}{name}")
        if content is None or not _looks_valid(name, content):
            problem = "没有" if content is None else "发来的不像是"
            report.skipped.append(f"ShinyColorsDB {problem} {outfit_id}（{dress.name}）的 {name}，下次同步再试")
            return False
        write_atomically(target, content)
        downloaded += len(content)
    if downloaded:
        log.info("拉取了 %s（%s）", outfit_id, dress.name)
        report.fetched.append(outfit_id)
        report.fetched_bytes += downloaded
    return True


def _start_of(path: Path) -> bytes:
    with path.open("rb") as file:
        return file.read(64)


def _looks_valid(name: str, content: bytes) -> bool:
    """Whether the start of a file is what its name says, and not an error page."""
    if name.endswith(".json"):
        return content.lstrip()[:1] == b"{"
    if name.endswith(".png"):
        return content[:8] == b"\x89PNG\r\n\x1a\n" or is_webp(content)
    return bool(content.strip()) and not content.lstrip().startswith(b"<")
