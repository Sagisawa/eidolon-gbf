"""Keeping the story corpus in step with the game: `eidolon story sync`.

A sync imports SCTranslationData's translated episodes first, then fills in what they
lack from the ShinyColorsDB mirror (ADR-0004) as untranslated episodes, under the
card's real name and the episode's title as the mirror's API gives them. The import
rules are the usual ones (`story_import`): failure endings are left out, a translated
episode is never replaced by an untranslated one, and a translation that arrives
later replaces the untranslated episode under the same card, since SCTranslationData
names a card's directory the way the game names the card.

Scripts are downloaded into a cache directory that stays out of the repository
(ADR-0003), laid out as the game does (`produce_events/200100401.json`), each with its
ETag beside it. What the API said about each card is kept there too, so a card whose
data has not changed since the last sync is not asked about again, nor are its
scripts; a card that has changed has its scripts asked for conditionally. Scripts
SCTranslationData has translated are never downloaded. A script the mirror does not
have is not an error; its card is asked about again next time.

The mirror being unreachable only costs this sync its untranslated episodes: what was
downloaded before it failed is still imported, and the next sync picks up from there.
"""

import json
import logging
import os
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

from eidolon.characters import Character
from eidolon.corpus import StoryCorpus
from eidolon.mirror import CardEpisode, Mirror, MirrorError
from eidolon.story_import import ImportReport, ScriptFile, import_csv_directory, import_script_files

log = logging.getLogger(__name__)

_CARDS_FILE = "cards.json"
_SCRIPTS_DIR = "scripts"


@dataclass
class SyncReport:
    translated: ImportReport
    """The SCTranslationData import."""
    untranslated: ImportReport = field(default_factory=ImportReport)
    """The import of the mirror's scripts."""
    translations_kept: int = 0
    """Episodes on the cards asked about this sync that SCTranslationData has
    translated, so were not downloaded."""
    downloaded: int = 0
    missing: int = 0
    """Scripts a card lists that the mirror does not have."""
    mirror_error: str | None = None
    """Why the mirror could not be synced from, if it could not."""

    @property
    def embedded_passages(self) -> int:
        return self.translated.embedded_passages + self.untranslated.embedded_passages

    @property
    def skipped_failures(self) -> int:
        return self.translated.skipped_failures + self.untranslated.skipped_failures


@dataclass
class _CardState:
    name: str
    version: str
    episodes: list[CardEpisode]
    complete: bool
    """Every script it lists was either downloaded or already translated."""


class _Cache:
    """The cache directory: scripts, their ETags, and what the API said about each card."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self.cards: dict[str, _CardState] = {}
        path = directory / _CARDS_FILE
        if path.exists():
            for uuid, card in json.loads(path.read_text(encoding="utf-8")).items():
                self.cards[uuid] = _CardState(
                    card["name"],
                    card["version"],
                    [CardEpisode(**episode) for episode in card["episodes"]],
                    card["complete"],
                )

    def script_path(self, script: str) -> Path:
        return self._directory / _SCRIPTS_DIR / f"{script}.json"

    def etag(self, script: str) -> str | None:
        path = self._etag_path(script)
        return path.read_text(encoding="utf-8") if path.exists() else None

    def set_etag(self, script: str, etag: str | None) -> None:
        path = self._etag_path(script)
        if etag:
            path.write_text(etag, encoding="utf-8")
        else:
            path.unlink(missing_ok=True)

    def save(self) -> None:
        cards = {uuid: asdict(card) for uuid, card in self.cards.items()}
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / _CARDS_FILE
        partial = path.with_name(path.name + ".part")
        partial.write_text(json.dumps(cards, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(partial, path)

    def _etag_path(self, script: str) -> Path:
        return self.script_path(script).with_suffix(".etag")


async def sync_stories(
    story_directory: Path,
    cache_directory: Path,
    corpus: StoryCorpus,
    characters: Iterable[Character],
    mirror: Mirror,
    *,
    idols: Sequence[int] | None = None,
) -> SyncReport:
    """Import SCTranslationData's CSVs from `story_directory`, then the mirror's card
    episodes the corpus lacks. `idols` limits the mirror to those idols' cards."""
    characters = list(characters)
    report = SyncReport(await import_csv_directory(story_directory, corpus, characters))
    cache = _Cache(cache_directory)
    try:
        await _fetch_cards(mirror, cache, corpus, report, idols)
    except MirrorError as e:
        report.mirror_error = str(e)
    report.untranslated = await import_script_files(
        _untranslated_scripts(cache, corpus), corpus, characters
    )
    return report


async def _fetch_cards(
    mirror: Mirror,
    cache: _Cache,
    corpus: StoryCorpus,
    report: SyncReport,
    idols: Sequence[int] | None,
) -> None:
    seen: set[str] = set()  # a unit's card is listed under each of its idols
    for idol in idols if idols is not None else await mirror.idols():
        for card in await mirror.cards(idol):
            if card.uuid in seen:
                continue
            seen.add(card.uuid)
            known = cache.cards.get(card.uuid)
            changed = known is None or known.version != card.version
            if known is None or changed:
                episodes = await mirror.episodes(card)
            elif known.complete:
                continue
            else:
                episodes = known.episodes
            # Its episodes are known now, so that what is downloaded is imported even if the
            # mirror fails before the card is done; until it is, it still counts as changed.
            unfinished = known.version if known is not None else ""
            cache.cards[card.uuid] = _CardState(card.name, unfinished, episodes, False)
            complete = True
            for episode in episodes:
                if corpus.imported_from(episode.script) == "csv":
                    report.translations_kept += 1
                    continue
                path = cache.script_path(episode.script)
                if path.exists() and not changed:
                    continue  # downloaded by a sync that stopped before this card was done
                fetched, etag = await mirror.download(
                    episode.script, path, cache.etag(episode.script) if path.exists() else None
                )
                if fetched == "missing":
                    complete = False
                    report.missing += 1
                    log.info("镜像上还没有 %s", episode.script)
                    continue
                cache.set_etag(episode.script, etag)
                if fetched == "downloaded":
                    report.downloaded += 1
            cache.cards[card.uuid] = _CardState(card.name, card.version, episodes, complete)
            if episodes:
                log.info("%s：%d 段剧情", card.name, len(episodes))
            cache.save()  # so an interrupted sync picks up after the last card done


def _untranslated_scripts(cache: _Cache, corpus: StoryCorpus) -> list[ScriptFile]:
    """Every script downloaded so far that SCTranslationData has not translated."""
    files: dict[str, ScriptFile] = {}
    for card in cache.cards.values():
        for episode in card.episodes:
            if episode.script in files or corpus.imported_from(episode.script) == "csv":
                continue
            path = cache.script_path(episode.script)
            if path.exists():
                files[episode.script] = ScriptFile(path, episode.script, card.name, episode.title)
    return sorted(files.values(), key=lambda file: file.source_id)
