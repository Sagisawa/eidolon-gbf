"""Importing releases and songs, for `eidolon world sync` (`world_sync`).

The releases are the CDs on Lantis's Shiny Colors site: its discography lists them apart
from the Blu-rays, and each one's page has its title, release date (発売日), catalog
number (品番) and tracks in order, announced ones not out yet included. Lantis is the
official source, so whatever it says goes. It names a track's singers in one of several
ways, and the import reads them all:

- on the track's line, 「曲名 / 角色 (CV.声优)」, or on a 歌： line under it;
- in the title, for a version one idol or unit sings: 「曲名（櫻木真乃Ver.）」;
- nowhere on the track but at the top of the page, when the whole CD is by one idol,
  one unit or one special unit (アーティスト：Team.Stella, with its idols under it);
- nowhere on this page but on another's track of the same title.

A singer is an idol, matched by her name or by her CV's; one of the eight units, matched
by its name or its reading, which stands for its members; or a special unit or the
whole cast (シャイニーカラーズ) whose idols the page lists, which stands for them and,
for a special unit, is kept as the song's special unit. Off-vocal and game-size versions
and dramas are tracks but no songs.

Where Lantis leaves a track's singers out, or names a special unit without saying who
is in it, ふじわらはじめ (a fan-run song database with an API) fills them in from the
same disc's track list there. The spec had imas-db do this, but imas-db has no Shiny
Colors CDs, only setlists (checked 2026-09-28). On each disc it was asked about, where it
disagrees with Lantis, Lantis is kept and the report lists it. A track whose singers are
still unknown, or which names anyone who is none of the idols, gets no song, and the
report lists it for the deployer to look into.

A song is a title (the first way a release spells it) and its singers: the same title
sung by others is another song. Neither lyrics nor credits are kept. Every release and
song keeps the pages it came from.
"""

import asyncio
import html
import json
import re
import unicodedata
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date

from eidolon.world import Idol, Release, Song, Track, Unit, WorldSyncError

LANTIS_URL = "https://shinycolors.lantis.jp/discography/"
FUJI_API = "https://api.fujiwarahaji.me/v4/"
FUJI_SONGS_URL = FUJI_API + "list?type=music&music_type=sc&limit=1000"
FUJI_NAME = "ふじわらはじめ"
ALL_IDOLS = "シャイニーカラーズ"
"""How Lantis names the whole cast: not a special unit."""

Fetch = Callable[[str], Awaitable[str]]
"""Gets a page's text, or raises WorldSyncError."""

_RELEASE_LINK = re.compile(r'href="(https://shinycolors\.lantis\.jp/releaseinfo/[\w-]+/)"')
_TRACK = re.compile(r"^M?\d+\s*[.．]\s*(.+)$")
"""A numbered track: 1．, 01., or M1. on a drama's or a musical's CD."""
_NO_SONG = re.compile(r"off\s*vocal|game\s*size|instrumental|karaoke|ドラマ|カラオケ|トーク", re.I)
_VERSION = re.compile(r"(?:[（(]\s*(.+?)\s*Ver\.?\s*[)）]|\s(.+?)\s*Ver\.?)\s*$")
_BASE = [
    re.compile(r"\s*-\s*\d+\s*colors\s*-\s*$", re.I),
    re.compile(r"\s*[（(]\s*\d{4}\s*Ver\.?\s*[)）]\s*$", re.I),
]
"""How a release names a later version of a song ふじわらはじめ keeps under its first name."""
_META = (
    "歌：", "作詞", "作曲", "編曲", "リミックス", "アンサンブル", "以上", "DISC", "BONUS", "[", "＜", "<",
)


@dataclass
class ReleaseImport:
    releases: tuple[Release, ...]
    songs: tuple[Song, ...]
    filled: list[str] = field(default_factory=list)
    """Tracks whose singers ふじわらはじめ filled in."""
    conflicts: list[str] = field(default_factory=list)
    """Where ふじわらはじめ disagrees with Lantis, which was kept."""
    unmatched: list[str] = field(default_factory=list)
    """Tracks naming a singer who is none of the idols: no song written."""
    unknown: list[str] = field(default_factory=list)
    """Tracks whose singers no source says: no song written."""
    notes: list[str] = field(default_factory=list)


@dataclass
class _Track:
    title: str
    singers_text: str | None = None
    """What the page says sings it, if it says."""
    group_members: str | None = None
    """The idols the page lists under a 歌： line naming a group."""
    singers: list[str] | None = None
    special: str | None = None
    no_song: bool = False
    bad: list[str] = field(default_factory=list)
    """Singers the page names who are none of the idols."""
    sources: list[str] = field(default_factory=list)


@dataclass
class _Release:
    url: str
    title: str
    date: date
    catalog: str
    artist: str
    artist_members: str | None
    tracks: list[_Track]

    @property
    def groups(self) -> dict[str, str]:
        """The groups whose idols the page lists, by name."""
        groups = {}
        if self.artist_members:
            groups[_plain(self.artist)] = self.artist_members
        for track in self.tracks:
            if track.singers_text and track.group_members:
                groups[_plain(track.singers_text)] = track.group_members
        return groups


async def import_releases(
    fetch: Fetch, idols: Sequence[Idol], units: Sequence[Unit]
) -> ReleaseImport:
    """The releases and songs as Lantis and ふじわらはじめ have them now, the singers
    matched to `idols` and `units`. Raises WorldSyncError if either cannot be read."""
    fan_songs = await _fuji_songs(fetch)
    discography = await fetch(LANTIS_URL)
    urls = _cd_links(discography)
    notes: list[str] = []
    limit = asyncio.Semaphore(4)

    async def page(url: str) -> _Release:
        async with limit:
            return _parse_release(url, await fetch(url), notes)

    releases = sorted(await asyncio.gather(*map(page, urls)), key=lambda r: (r.date, r.catalog))
    result = ReleaseImport((), (), notes=notes)
    singers = _Singers(idols, units)
    _resolve_from_lantis(releases, singers)
    fuji = _Fuji(fetch, fan_songs, singers, notes)
    for release in releases:
        if any(_open(track) for track in release.tracks):
            await fuji.fill(release, result)
    for release in releases:
        for number, track in enumerate(release.tracks, 1):
            where = f"{release.catalog}《{release.title}》第 {number} 首「{track.title}」"
            if track.no_song or track.singers is not None:
                continue
            if track.bad:
                result.unmatched.append(f"{where}：{'、'.join(track.bad)}")
            else:
                result.unknown.append(where)
    result.releases, result.songs = _assemble(releases)
    return result


def _open(track: _Track) -> bool:
    return not track.no_song and track.singers is None


# Lantis


def _cd_links(discography: str) -> list[str]:
    start, end = discography.find('class="CD_area"'), discography.find('class="BD_area"')
    if start == -1:
        raise WorldSyncError(f"{LANTIS_URL} 上找不到 CD 一览，页面结构可能变了")
    urls = list(dict.fromkeys(_RELEASE_LINK.findall(discography[start:end if end > start else None])))
    if not urls:
        raise WorldSyncError(f"{LANTIS_URL} 上找不到任何 CD，页面结构可能变了")
    return urls


def _lines(fragment: str) -> list[str]:
    text = re.sub(r"<br\s*/?>", "\n", fragment)
    text = re.sub(r"</?(?:p|h\d|div|li|ul)\b[^>]*>", "\n", text)
    text = re.sub(r'<img[^>]*alt="([^"]*)"[^>]*>', r"[\1]", text)
    text = re.sub(r"<[^>]+>", "", text)
    lines = html.unescape(text).replace("　", " ").splitlines()
    return [line.strip() for line in lines if line.strip()]


def _parse_date(text: str, separator: str) -> date | None:
    match = re.search(rf"(\d{{4}}){re.escape(separator)}(\d{{1,2}}){re.escape(separator)}(\d{{1,2}})", text)
    if not match:
        return None
    try:
        return date(*map(int, match.groups()))
    except ValueError:
        return None


def _parse_release(url: str, page: str, notes: list[str]) -> _Release:
    title = re.search(r'<div class="titles">.*?<h2>(.*?)</h2>', page, re.S)
    banner = re.search(r'<div class="date">([^<]*)</div>', page)
    contents = re.search(r'<div class="release_contents">(.*?)<!--release_contents-->', page, re.S)
    if not title or not contents:
        raise WorldSyncError(f"{url} 上找不到唱片名或唱片内容，页面结构可能变了")
    lines = _lines(contents.group(1))
    index = next((i for i, line in enumerate(lines) if line.startswith("[インデックス")), len(lines))
    artist, members, day, catalog = "", None, None, None
    for i, line in enumerate(lines[:index]):
        if line.startswith("アーティスト："):
            artist = line.split("：", 1)[1].strip()
            under = []
            for next_line in lines[i + 1:index]:
                if next_line.startswith(("発売日", "品番", "価格", "[")):
                    break
                under.append(next_line)
            members = "、".join(under).strip("、") or None
        elif line.startswith("発売日："):
            day = _parse_date(line, "/")
        elif line.startswith("品番："):
            catalog = line.split("：", 1)[1].strip()
    banner_text = banner.group(1).strip() if banner else ""
    banner_day = _parse_date(banner_text, ".")
    if day and banner_day and day != banner_day:
        notes.append(
            f"{catalog}：Lantis 页面标题上方写 {banner_text}，"
            f"発売日写 {day.year}/{day.month}/{day.day}，按発売日写入"
        )
    day = day or banner_day
    if catalog is None or day is None:
        raise WorldSyncError(f"{url} 上找不到品番或发售日，页面结构可能变了")
    return _Release(
        url, _text(title.group(1)), day, catalog, artist, members, _parse_tracks(lines[index + 1:])
    )


def _parse_tracks(lines: list[str]) -> list[_Track]:
    end = next((i for i, line in enumerate(lines) if line.startswith("[インフォメーション")), len(lines))
    lines = lines[:end]
    numbered = any(_TRACK.match(line) for line in lines)  # a digital single's is not
    tracks: list[_Track] = []
    for line in lines:
        number = _TRACK.match(line)
        if number or (not numbered and not line.startswith(_META)):
            track = _Track((number.group(1) if number else line).strip())
            if " / " in track.title:  # 「曲名 / 角色 (CV.声优)」
                title, singers = track.title.rsplit(" / ", 1)
                track.title, track.singers_text = title.strip(), singers.strip()
            tracks.append(track)
        elif not tracks:
            continue
        elif line.startswith("歌："):
            tracks[-1].singers_text = line.removeprefix("歌：").strip()
        elif (singers := tracks[-1].singers_text) and _unclosed(singers):  # broken mid-name
            tracks[-1].singers_text = singers + line
        elif singers and tracks[-1].group_members is None and "CV" in line and not line.startswith(_META):
            tracks[-1].group_members = line  # who the group on the 歌： line is
    for track in tracks:
        track.no_song = bool(_NO_SONG.search(track.title))
    return tracks


def _unclosed(text: str) -> bool:
    """Whether a list of singers goes on to the next line: broken off in a name, or after a
    comma."""
    opened = text.count("(") + text.count("（") > text.count(")") + text.count("）")
    return opened or text.rstrip().endswith(("、", ",", "，", "/", "／"))


def _text(raw: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", raw)).strip()


def _plain(name: str) -> str:
    return re.sub(r"\s", "", name)


def _key(text: str) -> str:
    """A title or name for matching: `（2023 Ver.）` is `(2023Ver.)`, case aside."""
    return re.sub(r"[\W_]", "", unicodedata.normalize("NFKC", text)).casefold()


def _hiragana(text: str) -> str:
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in text)


def _split(text: str, separators: str = "、/／×,，") -> list[str]:
    """`text`'s parts, split where no parenthesis is open."""
    parts, depth, current = [], 0, ""
    for char in text:
        depth += (char in "(（") - (char in ")）")
        if depth == 0 and char in separators:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    return [part.strip() for part in parts if part.strip()]


class _Singers:
    """Tells which idols a singer the sources name stands for."""

    def __init__(self, idols: Sequence[Idol], units: Sequence[Unit]) -> None:
        self._idols = {idol.name for idol in idols}
        self._by_cv = {_plain(idol.cv): idol.name for idol in idols if idol.cv}
        self._units: dict[str, tuple[str, ...]] = {}
        for unit in units:
            self._units[_key(unit.name)] = unit.members
            if unit.reading:
                self._units[_key(unit.reading)] = unit.members

    def idol(self, name: str) -> str | None:
        """The idol a person named so is: by her name, or by her CV's in brackets."""
        match = re.match(r"^(.*?)\s*[（(]\s*CV\s*[.．:：]?\s*(.*?)\s*[)）]$", name)
        person, cv = (match.group(1), match.group(2)) if match else (name, None)
        person = re.sub(r"[（(][^（()）]*[)）]$", "", _plain(person))  # 三峰結華（初代）
        if person in self._idols:
            return person
        return self._by_cv.get(_plain(cv)) if cv else None

    def one(self, name: str, groups: dict[str, str]) -> tuple[list[str], str | None] | None:
        """The idols `name` stands for, and the special unit it is, if it is one."""
        if idol := self.idol(name):
            return [idol], None
        members = self._units.get(_key(_hiragana(name))) or self._units.get(_key(name))
        if members:
            return list(members), None
        if (listed := groups.get(_plain(name))) is not None:
            resolved = self.all(listed, {})
            if resolved and not resolved[2]:
                return resolved[0], None if _plain(name) == ALL_IDOLS else name.strip()
        return None

    def all(self, text: str, groups: dict[str, str]) -> tuple[list[str], str | None, list[str]]:
        """The idols everyone `text` names stands for, the special unit among them, and
        those who stand for none."""
        names: list[str] = []
        special, bad = None, []
        for part in _split(text):
            found = self.one(part, groups)
            if found is None:
                bad.append(part)
                continue
            names += [name for name in found[0] if name not in names]
            special = special or found[1]
        return names, special, bad


def _version_singer(title: str, singers: _Singers) -> list[str] | None:
    """The idols of the version the title names (「曲名（櫻木真乃Ver.）」)."""
    match = _VERSION.search(title)
    if not match:
        return None
    who = (match.group(1) or match.group(2)).strip()
    for start in range(len(who)):  # the singer is the end of what comes before Ver.
        found = singers.one(who[start:].strip(), {})
        if found:
            return found[0]
    return None


def _resolve_from_lantis(releases: list[_Release], singers: _Singers) -> None:
    """Tells each track's singers as far as Lantis's pages do."""
    said: dict[str, set[tuple[str, ...]]] = {}  # title → singers, where a track says

    def same_title(track: _Track, told: dict[str, set[tuple[str, ...]]]) -> bool:
        found = told.get(_key(track.title), set())
        if len(found) == 1:
            track.singers = list(next(iter(found)))
            return True
        return False

    for release in releases:
        groups = release.groups
        for track in release.tracks:
            if track.no_song:
                continue
            if track.singers_text:
                names, special, bad = singers.all(track.singers_text, groups)
                if bad:
                    track.bad = bad
                else:
                    track.singers, track.special = names, special
            elif (version := _version_singer(track.title, singers)) is not None:
                track.singers = version
            if track.singers is not None:
                track.sources.append(release.url)
                said.setdefault(_key(track.title), set()).add(tuple(track.singers))
    for release in releases:
        for track in release.tracks:
            if _open(track) and not track.bad and same_title(track, said):
                track.sources.append(release.url)
    told = {key: set(value) for key, value in said.items()}
    for release in releases:
        artists = _split(release.artist, "、/／")
        open_tracks = [t for t in release.tracks if _open(t) and not t.bad]
        by_page = not any(t.singers_text for t in release.tracks)
        # A CD by several names each singing their own songs does not say who sings which,
        # but one whose other tracks are each one's version has a single song they share.
        if not open_tracks or not by_page or not (len(artists) == 1 or len(open_tracks) == 1):
            continue
        names, special, bad = singers.all(release.artist, release.groups)
        if bad:
            continue
        for track in open_tracks:
            track.singers, track.special = names, special
            track.sources.append(release.url)
            told.setdefault(_key(track.title), set()).add(tuple(names))
    for release in releases:
        for track in release.tracks:
            if _open(track) and not track.bad and same_title(track, told):
                track.sources.append(release.url)


# ふじわらはじめ


async def _fuji_songs(fetch: Fetch) -> dict[str, list[str]]:
    """ふじわらはじめ's Shiny Colors songs: the API URLs of each, by title."""

    try:
        rows = json.loads(await fetch(FUJI_SONGS_URL))
        songs: dict[str, list[str]] = {}
        for row in rows:
            songs.setdefault(_key(row["name"]), []).append(row["api"])
    except (ValueError, KeyError, TypeError) as e:
        raise WorldSyncError(f"{FUJI_SONGS_URL} 的回答不是预期的格式：{e!r}") from None
    if not songs:
        raise WorldSyncError(f"{FUJI_SONGS_URL} 没有返回任何歌曲")
    return songs


def _edition(title: str) -> str:
    """A release's title for matching across sources, without its edition (【初回限定盤】)."""
    return _key(re.sub(r"[【\[［][^】\]］]*[】\]］]", "", title))


def _bases(title: str) -> list[str]:
    keys = [_key(title)]
    for pattern in _BASE:
        base = pattern.sub("", title)
        if base != title:
            keys.append(_key(base))
    return keys


@dataclass
class _FanTrack:
    singers: list[str]
    unmatched: list[str]
    special: str | None


class _Fuji:
    def __init__(
        self, fetch: Fetch, songs: dict[str, list[str]], singers: _Singers, notes: list[str]
    ) -> None:
        self._fetch = fetch
        self._songs = songs
        self._singers = singers
        self._notes = notes
        self._json: dict[str, dict] = {}

    async def _get(self, url: str) -> dict:
        """The song or disc at `url`; empty if ふじわらはじめ answers with nothing, as it
        does for some discs whatever you ask (noted for the report)."""
        if url not in self._json:
            text = await self._fetch(url)
            if not text.strip():
                self._notes.append(f"{FUJI_NAME}的 {url} 返回了空内容，当作那里没有资料")
                self._json[url] = {}
                return self._json[url]
            try:
                data = json.loads(text)
            except ValueError as e:
                raise WorldSyncError(f"{url} 的回答不是预期的格式：{e!r}") from None
            if not isinstance(data, dict):
                raise WorldSyncError(f"{url} 的回答不是预期的格式")
            self._json[url] = data
        return self._json[url]

    async def _discs(self, release: _Release) -> list[dict]:
        """ふじわらはじめ's discs that are this release, found through its tracks' songs."""
        found: dict[str, dict] = {}
        for track in release.tracks:
            if not _open(track):
                continue
            for key in _bases(track.title):
                for api in self._songs.get(key, []):
                    song = await self._get(api)
                    for disc in song.get("disc") or []:
                        name, url = disc.get("name", ""), disc.get("api")
                        mine, theirs = _edition(release.title), _edition(name)
                        if url and (mine == theirs or mine.startswith(theirs) or theirs.startswith(mine)):
                            found[url] = await self._get(url)
        return list(found.values())

    def _tracks(self, disc: dict) -> dict[str, list[_FanTrack]]:
        """The disc's sung tracks by title, versions for a game or without vocals aside."""
        tracks: dict[str, list[_FanTrack]] = {}
        for song in disc.get("song") or []:
            if {"offvocal", "gamever"} & set(song.get("flag") or []):
                continue
            names, unmatched, specials = [], [], []
            for unit in song.get("unit") or []:
                if not self._singers.one(unit.get("name", ""), {}) and unit.get("name"):
                    specials.append(unit["name"])
                for member in unit.get("member") or []:
                    names.append(member.get("name", ""))
            names += [member.get("name", "") for member in song.get("member") or []]
            idols: list[str] = []
            for name in names:
                idol = self._singers.idol(name)
                if idol is None:
                    unmatched.append(name)
                elif idol not in idols:
                    idols.append(idol)
            if idols or unmatched:
                special = "、".join(specials) or None
                tracks.setdefault(_key(song.get("name", "")), []).append(_FanTrack(idols, unmatched, special))
        return tracks

    async def fill(self, release: _Release, result: ReleaseImport) -> None:
        for disc in await self._discs(release):
            link = disc.get("link") or disc.get("api", "")
            tracks = self._tracks(disc)
            for track in release.tracks:
                if track.no_song:
                    continue
                if track.singers is not None:
                    self._compare(release, track, tracks.get(_key(track.title), []), result)
                    continue
                candidates = next((tracks[k] for k in _bases(track.title) if k in tracks), [])
                distinct = {tuple(c.singers): c for c in candidates}
                if len(distinct) != 1:
                    continue
                fan = next(iter(distinct.values()))
                if fan.unmatched:
                    track.bad = track.bad or fan.unmatched
                    continue
                special = fan.special or next(
                    (b for b in track.bad if "CV" not in b), None
                ) or (release.artist if _single_group(release, self._singers) else None)
                track.singers, track.special = fan.singers, special
                track.bad = []
                track.sources += [release.url, link]
                result.filled.append(
                    f"{release.catalog}「{track.title}」：{'、'.join(fan.singers)}（{link}）"
                )

    @staticmethod
    def _compare(release: _Release, track: _Track, fan: list[_FanTrack], result: ReleaseImport) -> None:
        distinct = {tuple(f.singers) for f in fan if not f.unmatched}
        if len(distinct) == 1 and set(next(iter(distinct))) != set(track.singers or []):
            result.conflicts.append(
                f"{release.catalog}「{track.title}」：Lantis 是 {'、'.join(track.singers or [])}，"
                f"{FUJI_NAME}是 {'、'.join(next(iter(distinct)))}"
            )


def _single_group(release: _Release, singers: _Singers) -> bool:
    """Whether the release is by one group Lantis does not say the idols of."""
    artists = _split(release.artist, "、/／")
    return len(artists) == 1 and "CV" not in artists[0] and singers.one(artists[0], release.groups) is None


# Songs


def _assemble(releases: Iterable[_Release]) -> tuple[tuple[Release, ...], tuple[Song, ...]]:
    songs: dict[tuple[str, frozenset[str]], dict] = {}
    ids: set[str] = set()
    out: list[Release] = []
    for release in releases:
        tracks = []
        for track in release.tracks:
            if track.no_song or track.singers is None:
                tracks.append(Track(track.title, None))
                continue
            key = (_key(track.title), frozenset(track.singers))
            song = songs.get(key)
            if song is None:
                id, n = track.title, 1
                while id in ids:
                    n += 1
                    id = f"{track.title} #{n}"
                ids.add(id)
                song = songs[key] = {
                    "id": id, "title": track.title, "singers": tuple(track.singers),
                    "special_unit": track.special, "releases": [], "sources": [],
                }
            song["special_unit"] = song["special_unit"] or track.special
            if release.catalog not in song["releases"]:
                song["releases"].append(release.catalog)
            song["sources"] += [s for s in dict.fromkeys(track.sources) if s not in song["sources"]]
            tracks.append(Track(track.title, song["id"]))
        out.append(Release(release.catalog, release.title, release.date, tuple(tracks), (release.url,)))
    return tuple(out), tuple(
        Song(s["id"], s["title"], s["singers"], s["special_unit"], tuple(s["releases"]), tuple(s["sources"]))
        for s in songs.values()
    )
