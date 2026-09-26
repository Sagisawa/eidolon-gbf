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

Event episodes have no listing: their scripts are numbered `4001` + the event's three
digits + the episode's two (`game_event_communications/400109701`), so they are found
by trying numbers. The events known are those the corpus or the cache has; each one
up to the latest is walked once, episode by episode until the mirror has no more,
which fills in the events and episodes SCTranslationData lacks. The latest event is
walked again every sync, in case the mirror has more of it, and a few numbers after
it are tried for new events, so a sync with nothing new costs a handful of 404s. A
number the mirror had nothing under while a later event existed is taken as skipped
for good, and an event no longer the latest is not asked about again: the game
releases an event's episodes together. Episodes already downloaded are not asked
for again, since events carry no version to tell they changed.

An event's name comes from the admin's table of event names (`load_event_names`),
read at every import so that a name filled in later reaches the catalog; an event
not in the table takes the name SCTranslationData files its translated episodes
under, if any, and is otherwise 「活动剧情 NNN」, never a made-up name. Its episodes
are 「第N話」.

The mirror being unreachable only costs this sync its untranslated episodes: what was
downloaded before it failed is still imported, and the next sync picks up from there.
"""

import json
import logging
import os
import re
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

from eidolon.characters import Character
from eidolon.corpus import StoryCorpus
from eidolon.mirror import CardEpisode, Mirror, MirrorError
from eidolon.story_import import ImportReport, ScriptFile, import_csv_directory, import_script_files

log = logging.getLogger(__name__)

_CARDS_FILE = "cards.json"
_EVENTS_FILE = "events.json"
_SCRIPTS_DIR = "scripts"

_EVENT_SCRIPTS = "game_event_communications"
_EVENT_SCRIPT = re.compile(_EVENT_SCRIPTS + r"/4001(?P<event>\d{3})(?P<episode>\d{2})")
PROBE_AHEAD = 3
"""How many event numbers after the latest known are tried, in case some are skipped."""
_EPISODES_AT_MOST = 99
"""Two digits of episode; events have about eight."""


class EventNamesError(RuntimeError):
    """The table of event names could not be read."""


def load_event_names(path: Path, *, required: bool = False) -> dict[int, str]:
    """The admin's table of event names: `[events]` with one `NNN = "name"` per event.

    A table that does not exist is empty, unless it is `required`."""
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if required:
            raise EventNamesError(f"找不到活动名对照表 {path}") from None
        return {}
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        raise EventNamesError(f"活动名对照表 {path} 格式有误：{e}") from None
    events = config.get("events", {})
    if not isinstance(events, dict):
        raise EventNamesError(f"活动名对照表 {path} 里的 events 需要是一张表")
    names: dict[int, str] = {}
    for key, name in events.items():
        if not (key.isascii() and key.isdigit() and len(key) <= 3 and int(key) > 0):
            raise EventNamesError(f"活动名对照表 {path}：{key} 不是 001–999 的活动编号")
        if not isinstance(name, str) or not name.strip():
            raise EventNamesError(f"活动名对照表 {path}：活动 {key} 的名称需要是非空字符串")
        names[int(key)] = name.strip()
    return names


def event_script(event: int, episode: int) -> str:
    """The script of an event's episode, e.g. `game_event_communications/400109701`."""
    return f"{_EVENT_SCRIPTS}/4001{event:03d}{episode:02d}"


def _event_of(script: str) -> tuple[int, int] | None:
    """The event and episode of an event script, if it is one."""
    match = _EVENT_SCRIPT.fullmatch(script)
    return (int(match["event"]), int(match["episode"])) if match else None


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
    unnamed_events: list[int] = field(default_factory=list)
    """Events with untranslated episodes that neither the table of event names nor
    SCTranslationData names."""
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
        self.events: dict[int, int] = {}
        """Each event walked to its end, and how many episodes it has."""
        path = directory / _EVENTS_FILE
        if path.exists():
            self.events = {
                int(event): episodes
                for event, episodes in json.loads(path.read_text(encoding="utf-8")).items()
            }

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

    def event_scripts(self) -> list[Path]:
        return sorted((self._directory / _SCRIPTS_DIR / _EVENT_SCRIPTS).glob("*.json"))

    def save(self) -> None:
        self._write(_CARDS_FILE, {uuid: asdict(card) for uuid, card in self.cards.items()})

    def save_events(self) -> None:
        self._write(_EVENTS_FILE, {f"{event:03d}": n for event, n in sorted(self.events.items())})

    def _write(self, name: str, data: object) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / name
        partial = path.with_name(path.name + ".part")
        partial.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
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
    event_names: Mapping[int, str] | None = None,
    idols: Sequence[int] | None = None,
) -> SyncReport:
    """Import SCTranslationData's CSVs from `story_directory`, then the mirror's card
    and event episodes the corpus lacks, events named from `event_names`. `idols`
    limits the mirror to those idols' cards, and leaves events out."""
    characters = list(characters)
    report = SyncReport(await import_csv_directory(story_directory, corpus, characters))
    cache = _Cache(cache_directory)
    errors = []
    try:
        await _fetch_cards(mirror, cache, corpus, report, idols)
    except MirrorError as e:
        errors.append(str(e))
    if idols is None:
        try:  # the viewer may well be up when the API is not
            await _fetch_events(mirror, cache, corpus, report)
        except MirrorError as e:
            errors.append(str(e))
    report.mirror_error = "；".join(errors) or None
    names = event_names or {}
    event_files, report.unnamed_events = _untranslated_event_scripts(cache, corpus, names)
    report.untranslated = await import_script_files(
        _untranslated_scripts(cache, corpus) + event_files, corpus, characters
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


async def _fetch_events(
    mirror: Mirror,
    cache: _Cache,
    corpus: StoryCorpus,
    report: SyncReport,
) -> None:
    known = {
        found[0]
        for episode_id in corpus.episode_ids(f"{_EVENT_SCRIPTS}/")
        if (found := _event_of(episode_id))
    }
    known.update(event for event, episodes in cache.events.items() if episodes)
    latest = max(known, default=0)
    for event in range(1, latest + 1):
        if event in cache.events and event < latest:
            continue
        cache.events[event] = await _walk_event(mirror, cache, corpus, report, event)
        cache.save_events()
    # Events after the latest: numbers are sometimes skipped, so a few are tried.
    tried: list[int] = []
    event = latest + 1
    while len(tried) < PROBE_AHEAD:
        episodes = await _walk_event(mirror, cache, corpus, report, event)
        if episodes:
            log.info("镜像上有新活动 %03d：%d 话", event, episodes)
            cache.events.update({skipped: 0 for skipped in tried})
            cache.events[event] = episodes
            cache.save_events()
            tried = []
        else:
            tried.append(event)
        event += 1


async def _walk_event(
    mirror: Mirror, cache: _Cache, corpus: StoryCorpus, report: SyncReport, event: int
) -> int:
    """Fetch the event's episodes from the first until the mirror has no more; returns
    how many it has. Episodes translated or already downloaded are not asked for."""
    episode = 1
    while episode <= _EPISODES_AT_MOST:
        script = event_script(event, episode)
        path = cache.script_path(script)
        if corpus.imported_from(script) != "csv" and not path.exists():
            fetched, etag = await mirror.download(script, path, None)
            if fetched == "missing":
                break
            cache.set_etag(script, etag)
            report.downloaded += 1
        episode += 1
    return episode - 1


def _untranslated_event_scripts(
    cache: _Cache, corpus: StoryCorpus, names: Mapping[int, str]
) -> tuple[list[ScriptFile], list[int]]:
    """Every event script downloaded so far that SCTranslationData has not translated,
    and the events of those that go unnamed.

    An event is named from the table as it is now; one the table lacks takes the name
    SCTranslationData files its translated episodes under, if it has any, so that the
    event stays together in the catalog."""
    files = []
    unnamed: set[int] = set()
    for path in cache.event_scripts():
        script = f"{_EVENT_SCRIPTS}/{path.stem}"
        if (found := _event_of(script)) is None or corpus.imported_from(script) == "csv":
            continue
        event, episode = found
        name = names.get(event) or _translated_event_name(corpus, event)
        if name is None:
            unnamed.add(event)
        source = name or f"活动剧情 {event:03d}"
        files.append(ScriptFile(path, script, source, f"第{episode}話"))
    return files, sorted(unnamed)


def _translated_event_name(corpus: StoryCorpus, event: int) -> str | None:
    for episode_id in corpus.episode_ids(f"{_EVENT_SCRIPTS}/4001{event:03d}"):
        if corpus.imported_from(episode_id) == "csv" and (episode := corpus.get(episode_id)):
            return episode.source
    return None


def _untranslated_scripts(cache: _Cache, corpus: StoryCorpus) -> list[ScriptFile]:
    """Every card script downloaded so far that SCTranslationData has not translated."""
    files: dict[str, ScriptFile] = {}
    for card in cache.cards.values():
        for episode in card.episodes:
            if episode.script in files or corpus.imported_from(episode.script) == "csv":
                continue
            path = cache.script_path(episode.script)
            if path.exists():
                files[episode.script] = ScriptFile(path, episode.script, card.name, episode.title)
    return sorted(files.values(), key=lambda file: file.source_id)
