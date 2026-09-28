"""Test doubles for external services."""

import asyncio
import html
import hashlib
import json
import secrets
from collections.abc import AsyncGenerator, AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from pipecat.frames.frames import (
    Frame,
    ProposedUserStartedSpeakingFrame,
    ProposedUserStoppedSpeakingFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
)
from pipecat.services.settings import STTSettings, TTSSettings
from pipecat.services.stt_service import STTService
from pipecat.services.tts_service import TTSService
from pipecat.utils.time import time_now_iso8601

from eidolon.characters import Character
from eidolon.config import LLMSettings
from eidolon.embedding import Document, EmbeddingError
from eidolon.identity import Identity, IdentityError, ProviderName
from eidolon.llm import ChatLLM, ChatMessage, LLMError, Tool, ToolCall
from eidolon.mirror import Mirror
from eidolon.own_keys import OwnKeyRejected
from eidolon.retrieval import JudgeError, Need
from eidolon.store import Message

START = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


class FakeClock:
    """A clock the tests move forward themselves."""

    def __init__(self, now: datetime = START) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


DEPLOYER_KEY = "test-key"
"""The deployer's chat model key in the tests' settings."""


HANG = object()
"""A chunk in a FakeLLM reply where the model stops sending but never finishes."""


class FakeLLM:
    """Records every prompt it receives, the tools offered with it and the API key it came
    with (`keys`), and replies from a script.

    Each scripted reply is a list of text chunks and tool calls, streamed in order, so
    tests can split the structured reply at awkward boundaries or have the model call a
    tool; a reply that is an LLMError is raised instead, as a failing service would. With
    a `delay`, it waits that many seconds before each chunk after the first, as a slow
    model would; at `HANG` it waits forever. Unless reached through a FakeLLMService, it
    is the deployer's model.
    """

    def __init__(
        self, *replies: Sequence[str | ToolCall | object] | LLMError, delay: float = 0
    ) -> None:
        self._replies = [r if isinstance(r, LLMError) else list(r) for r in replies]
        self._delay = delay
        self.prompts: list[list[ChatMessage]] = []
        self.tools: list[list[Tool]] = []
        self.keys: list[str] = []

    def stream(
        self, messages: Sequence[ChatMessage], tools: Sequence[Tool] = ()
    ) -> AsyncIterator[str | ToolCall]:
        return self.stream_with(DEPLOYER_KEY, messages, tools)

    async def stream_with(
        self, key: str, messages: Sequence[ChatMessage], tools: Sequence[Tool] = ()
    ) -> AsyncIterator[str | ToolCall]:
        self.prompts.append(list(messages))
        self.tools.append(list(tools))
        self.keys.append(key)
        if not self._replies:
            raise AssertionError("FakeLLM ran out of scripted replies")
        reply = self._replies.pop(0)
        if isinstance(reply, LLMError):
            raise reply
        for i, chunk in enumerate(reply):
            if i and self._delay:
                await asyncio.sleep(self._delay)
            if chunk is HANG:
                await asyncio.Event().wait()
            assert isinstance(chunk, str | ToolCall)
            yield chunk

    async def aclose(self) -> None:
        pass


class FakeLLMService:
    """Stands in for the LLM services users bring their own keys to: every model opened on
    it replies from `llm`'s script, recording the key it came with there. Records what
    was tried before saving (`checked`); a key in `rejects` fails the try with that
    message."""

    def __init__(self, llm: FakeLLM | None = None) -> None:
        self.llm = llm or FakeLLM()
        self.checked: list[LLMSettings] = []
        self.opened: list[LLMSettings] = []
        self.rejects: dict[str, str] = {}

    def open(self, settings: LLMSettings) -> ChatLLM:
        self.opened.append(settings)
        return _KeyedLLM(self.llm, settings.api_key)

    async def check(self, settings: LLMSettings) -> None:
        self.checked.append(settings)
        if settings.api_key in self.rejects:
            raise LLMError(self.rejects[settings.api_key])

    async def aclose(self) -> None:
        pass


class _KeyedLLM:
    def __init__(self, llm: FakeLLM, key: str) -> None:
        self._llm = llm
        self._key = key

    def stream(
        self, messages: Sequence[ChatMessage], tools: Sequence[Tool] = ()
    ) -> AsyncIterator[str | ToolCall]:
        return self._llm.stream_with(self._key, messages, tools)

    async def aclose(self) -> None:
        pass


class FakeBackgroundLLM:
    """Stands in for the background model: answers each request with the next scripted
    reply, and with no memories once the script runs out; a reply that is an exception
    is raised instead. Records every prompt it receives. With a `gate`, it answers only
    once the gate is open, like a slow model."""

    NOTHING = '{"memories": []}'

    def __init__(self, *replies: str | Exception, gate: asyncio.Event | None = None) -> None:
        self._replies = list(replies)
        self._gate = gate
        self.prompts: list[list[ChatMessage]] = []

    async def stream(
        self, messages: Sequence[ChatMessage], tools: Sequence[Tool] = ()
    ) -> AsyncIterator[str | ToolCall]:
        self.prompts.append(list(messages))
        reply = self._replies.pop(0) if self._replies else self.NOTHING
        if self._gate is not None:
            await self._gate.wait()
        if isinstance(reply, Exception):
            raise reply
        for i in range(0, len(reply), 7):  # in chunks, as a streaming model would
            yield reply[i : i + 7]

    async def aclose(self) -> None:
        pass


DEPLOYER_SONIOX_KEY = "deployer-soniox-key"
DEPLOYER_FISH_KEY = "deployer-fish-key"
"""The deployer's speech keys in the tests' settings."""


class FakeSTT(STTService):
    """Stands in for Soniox in one call, on `api_key`: ignores the microphone and hears
    what the test says the user said, the way Soniox reports an utterance."""

    def __init__(self, api_key: str) -> None:
        super().__init__(ttfs_p99_latency=0.1, settings=STTSettings(model=None, language=None))
        self.api_key = api_key

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None, None]:
        yield None

    async def hear(self, text: str) -> None:
        """The user said `text`: an utterance starts, is transcribed, and ends."""
        await self.broadcast_frame(ProposedUserStartedSpeakingFrame)
        await self.push_frame(TranscriptionFrame(text, "user", time_now_iso8601(), finalized=True))
        await self.broadcast_frame(ProposedUserStoppedSpeakingFrame)

    async def break_down(self) -> None:
        """Fail as a rejected API key would: for good."""
        await self.push_error("fake speech recognition is down", force_treat_as_permanent=True)


class FakeTTS(TTSService):
    """Stands in for Fish Audio in one call, on `api_key`: records what it is asked to
    voice, and in which voice, and says a moment of silence for each."""

    def __init__(self, api_key: str, voice_id: str, sample_rate: int) -> None:
        super().__init__(
            sample_rate=sample_rate, settings=TTSSettings(model=None, voice=None, language=None)
        )
        self.api_key = api_key
        self.voice_id = voice_id
        self.voiced: list[str] = []

    async def break_down(self) -> None:
        """Fail as a rejected API key would: for good."""
        await self.push_error("fake speech synthesis is down", force_treat_as_permanent=True)

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        self.voiced.append(text)
        samples = self.sample_rate // 10
        yield TTSAudioRawFrame(b"\0\0" * samples, self.sample_rate, 1, context_id=context_id)


class FakeSpeech:
    """Stands in for Soniox and Fish Audio: the speech services of each call started, in
    order, each with the key it was made with. Set `down` to have the services fail to be
    made at all. Records the keys tried before saving (`checked`); a key in `rejects`
    fails its try with that message."""

    def __init__(self) -> None:
        self.stts: list[FakeSTT] = []
        self.ttss: list[FakeTTS] = []
        self.down = False
        self.checked: list[tuple[str, str]] = []
        self.rejects: dict[str, str] = {}

    def stt(self, api_key: str) -> FakeSTT:
        if self.down:
            raise RuntimeError("fake speech services are down")
        self.stts.append(FakeSTT(api_key))
        return self.stts[-1]

    def tts(self, api_key: str, voice_id: str, sample_rate: int) -> FakeTTS:
        self.ttss.append(FakeTTS(api_key, voice_id, sample_rate))
        return self.ttss[-1]

    async def check(self, service: str, api_key: str) -> None:
        self.checked.append((service, api_key))
        if api_key in self.rejects:
            raise OwnKeyRejected(self.rejects[api_key])


class FakeIdentityProvider:
    """Stands in for Google or GitHub: the test says which identity the next sign-in there
    is (`will_identify`). Records the callback URL of every sign-in; set `down` to have it
    fail as an unreachable provider would."""

    AUTHORIZE_URL = "https://provider.invalid/authorize"

    def __init__(self, name: ProviderName) -> None:
        self.name: ProviderName = name
        self.callbacks: list[str] = []
        self.down = False
        self._identities: dict[str, Identity] = {}

    def will_identify(self, identity: Identity) -> str:
        """The code the provider will send back for this identity."""
        code = secrets.token_hex(4)
        self._identities[code] = identity
        return code

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        query = urlencode({"provider": self.name, "state": state, "redirect_uri": redirect_uri})
        return f"{self.AUTHORIZE_URL}?{query}"

    async def identify(self, code: str, redirect_uri: str) -> Identity:
        self.callbacks.append(redirect_uri)
        if self.down:
            raise IdentityError(f"fake {self.name} is down")
        if code not in self._identities:
            raise IdentityError(f"fake {self.name} does not know the code {code}")
        return self._identities.pop(code)

    async def aclose(self) -> None:
        pass


class FakeEmbedder:
    """Embeds text as counts of a few keywords, so the nearest passages are the ones
    sharing the query's keywords. Records every document (its text, and its title in
    `titles`) and query it embeds; set `down` to have it fail as an unreachable service
    would."""

    KEYWORDS = ("鳩", "公園", "優勝", "長崎", "ちゃんぽん", "写真", "負け", "猫", "北海道")

    def __init__(self, model: str = "fake-embedding") -> None:
        self.model = model
        self.documents: list[str] = []
        self.titles: list[str | None] = []
        self.queries: list[str] = []
        self.down = False

    async def embed_documents(self, documents: Sequence[Document]) -> list[list[float]]:
        if self.down:
            raise EmbeddingError("fake embedding service is down")
        self.documents.extend(d.text for d in documents)
        self.titles.extend(d.title for d in documents)
        return [self._vector(d.text) for d in documents]

    async def embed_query(self, text: str) -> list[float]:
        if self.down:
            raise EmbeddingError("fake embedding service is down")
        self.queries.append(text)
        return self._vector(text)

    def _vector(self, text: str) -> list[float]:
        return [0.01] + [float(text.count(k)) for k in self.KEYWORDS]


class FakeJudge:
    """Stands in for Jev: answers every turn the same way, or fails if `answer` is None.
    Records what it was asked."""

    def __init__(self, answer: Need | None = "references") -> None:
        self.answer: Need | None = answer
        self.asked: list[tuple[str, str]] = []  # (character id, text)

    async def judge(self, character: Character, history: Sequence[Message], text: str) -> Need:
        self.asked.append((character.id, text))
        if self.answer is None:
            raise JudgeError("fake Jev is down")
        return self.answer


class FakeReranker:
    """Ranks documents containing `prefer` first (scoring them 0.9), otherwise keeping the
    order it was given (scoring the rest `others`). Records every call."""

    def __init__(self, prefer: str = "", others: float = 0.5) -> None:
        self.prefer = prefer
        self.others = others
        self.calls: list[tuple[str, list[str]]] = []

    async def rerank(
        self, query: str, documents: Sequence[str], top_n: int
    ) -> list[tuple[int, float]]:
        self.calls.append((query, list(documents)))
        order = sorted(range(len(documents)), key=lambda i: self.prefer not in documents[i])
        return [(i, 0.9 if self.prefer in documents[i] else self.others) for i in order[:top_n]]


class FakeShinyColorsDB:
    """Stands in for the ShinyColorsDB API, the viewer that mirrors the game's scripts and
    the idols' albums, answering as they do: idols and their cards, each card's episodes,
    albums, and scripts; scripts and albums with an ETag, 304 to a request for a copy that
    is still current and 404 for one it does not have. Records every request, and which
    scripts (and albums, as `album/NN`) it sent in full. Set `down`
    to have it unreachable, or `down_after` to have it go down after that many requests."""

    def __init__(self) -> None:
        self.idols: dict[int, list[dict]] = {}
        self.events: dict[str, list[dict]] = {}
        self.scripts: dict[str, bytes] = {}
        self.albums: dict[int, dict] = {}
        self.requests: list[httpx.Request] = []
        self.sent: list[str] = []
        self.down = False
        self.down_after: int | None = None

    def add_card(
        self, idol: int, uuid: str, name: str, type: str, episodes: Sequence[tuple[int, str]] = ()
    ) -> None:
        self.idols.setdefault(idol, []).append(
            {"cardUuid": uuid, "cardName": name, "cardType": type, "cardHash": "v1", "lastModified": "2026-09-01"}
        )
        title = "eventTitle" if type.startswith("P_") else "eventName"
        self.events[uuid] = [{"eventId": event_id, title: t} for event_id, t in episodes]

    def update_card(self, uuid: str) -> None:
        """The card's data changes, as when the game revises it."""
        for card in (c for cards in self.idols.values() for c in cards if c["cardUuid"] == uuid):
            card["cardHash"] += "+"

    def add_album(
        self, idol: int, sections: dict[str, str], entries: Sequence[tuple[str, str, str, str]]
    ) -> None:
        """The idol's album: its sections (album type → title), and its entries, each
        `(category, communication id, title, album type)`."""
        self.albums[idol] = {
            "id": str(idol),
            "albumCommunicationTitles": [
                {"albumType": album_type, "id": str(1000 + n), "title": title}
                for n, (album_type, title) in enumerate(sections.items(), 1)
            ],
            "communications": [
                {"albumType": album_type, "communicationCategory": category,
                 "communicationId": number, "title": title, "isReleased": True}
                for category, number, title, album_type in entries
            ],
        }

    def add_script(self, script: str, frames: object) -> None:
        self.scripts[script] = json.dumps(frames, ensure_ascii=False).encode()

    def mirror(self) -> Mirror:
        return Mirror(httpx.AsyncClient(transport=httpx.MockTransport(self._handle)), interval=0)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.down or (self.down_after is not None and len(self.requests) > self.down_after):
            raise httpx.ConnectError("connection refused")
        path, params = request.url.path, request.url.params
        if request.url.host == "api.shinycolors.moe":
            if path == "/info/idolList":
                return httpx.Response(200, json=[{"idolId": i} for i in self.idols])
            if path == "/info/idolInfo":
                return httpx.Response(200, json={"cardLists": self.idols.get(int(params["idolId"]), [])})
            if path in ("/info/pCardInfo", "/info/sCardInfo"):
                key = "cardIdolEvents" if path == "/info/pCardInfo" else "cardSupportEvents"
                return httpx.Response(200, json={key: self.events[params["cardId"]]})
            return httpx.Response(404)
        if request.url.host == "cf-static.shinycolors.moe":
            idol = int(path.removeprefix("/albums/album/").removesuffix(".json"))
            album = self.albums.get(idol)
            body = None if album is None else json.dumps(album, ensure_ascii=False).encode()
            return self._send(request, f"album/{idol:02d}", body)
        script = path.removeprefix("/json/").removesuffix(".json")
        return self._send(request, script, self.scripts.get(script))

    def _send(self, request: httpx.Request, name: str, body: bytes | None) -> httpx.Response:
        if body is None:
            return httpx.Response(404, text="<html>Not Found</html>")
        etag = f'"{hashlib.md5(body).hexdigest()}"'
        if request.headers.get("If-None-Match") == etag:
            return httpx.Response(304)
        self.sent.append(name)
        return httpx.Response(200, content=body, headers={"ETag": etag})


@dataclass
class LantisRelease:
    """A release on Lantis's Shiny Colors site, as its page shows it."""

    slug: str
    """The page's path segment, e.g. laca-25301."""
    title: str
    date: str
    """The 発売日 line as the page writes it: 2026/9/16."""
    catalog: str
    artist: str
    """The アーティスト line."""
    index: list[str]
    """The track list, a paragraph each, its lines as the page writes them, e.g.
    ["1．ヒカリのdestination\n歌：イルミネーションスターズ\n作詞：…"]."""
    artist_members: str | None = None
    """The line of idols under the アーティスト line, if the page has one."""
    banner_date: str | None = None
    """The date over the title (2026.09.16); by default the 発売日's."""


@dataclass
class FujiDisc:
    """A disc in ふじわらはじめ's database: its name, and its tracks, each a name, its
    units (name and members), its idols and its flags (orig, gamever, offvocal)."""

    tax_id: int
    name: str
    tracks: list[tuple[str, list[tuple[str, list[str]]], list[str], list[str]]]


class FakeWorldSites:
    """Stands in for the sites `eidolon world sync` imports from, answering as they do:
    im@sparql's SPARQL endpoint (told apart by what each query asks for), the official
    site's idol index and unit pages, Lantis's Shiny Colors site (the discography and the
    releases' pages) and ふじわらはじめ's API (its song list, songs and discs). Records
    every request. Add a host's name to `down` to have it unreachable, or a page's path
    to `missing` to have it answer 404."""

    SPARQL = "sparql.crssnky.xyz"
    OFFICIAL = "shinycolors.idolmaster-official.jp"
    LANTIS = "shinycolors.lantis.jp"
    FUJI = "api.fujiwarahaji.me"

    def __init__(self) -> None:
        self.idols: list[dict[str, str]] = []
        """im@sparql's idols: `id` (the resource's last path segment), `name`, `kana`, `cv`."""
        self.staff: list[dict[str, str]] = []
        """im@sparql's staff: `id`, `name`, `kana`, `position`."""
        self.sparql_units: dict[str, tuple[str | None, list[str]]] = {}
        """im@sparql's units, by name: reading and members."""
        self.official_units: list[tuple[str, str, str, list[str]]] = []
        """The official site's units, in order: slug, logo text (empty for none), the
        name under the logo, members as the site writes them (family name, space, given)."""
        self.releases: list[LantisRelease] = []
        """Lantis's CDs, in the discography's order."""
        self.blu_rays: list[tuple[str, str]] = []
        """Lantis's Blu-rays: slug and title. The discography lists them apart from the CDs."""
        self.fuji_songs: dict[int, tuple[str, list[int]]] = {}
        """ふじわらはじめ's Shiny Colors songs by id: name and the discs it is on."""
        self.fuji_discs: dict[int, FujiDisc] = {}
        self.requests: list[httpx.Request] = []
        self.down: set[str] = set()
        self.missing: set[str] = set()
        self.empty: set[str] = set()
        """ふじわらはじめ's API calls (path and query: v4/tax?id=4654) that answer with
        an empty body, as it does for some discs."""

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self._handle))

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host = request.url.host
        if host in self.down:
            raise httpx.ConnectError("connection refused")
        if host == self.SPARQL and request.url.path == "/spql/imas/query":
            return httpx.Response(200, json=self._query(request.url.params["query"]))
        if host == self.OFFICIAL and request.url.path.strip("/") not in self.missing:
            path = request.url.path.strip("/")
            if path == "idol":
                return httpx.Response(200, text=self._index())
            for slug, logo, name, members in self.official_units:
                if path == f"idol/{slug}":
                    return httpx.Response(200, text=self._unit_page(slug, logo, name, members))
        path = request.url.path.strip("/")
        if host == self.LANTIS and path not in self.missing:
            if path == "discography":
                return httpx.Response(200, text=self._discography())
            for release in self.releases:
                if path == f"releaseinfo/{release.slug}":
                    return httpx.Response(200, text=self._release_page(release))
        if host == self.FUJI and f"{path}?{request.url.query.decode()}" in self.empty:
            return httpx.Response(200, content=b"", headers={"Content-Type": "application/json"})
        if host == self.FUJI and path not in self.missing:
            params = request.url.params
            if path == "v4/list" and params.get("type") == "music" and params.get("music_type") == "sc":
                return httpx.Response(200, json=[
                    {"name": name, "type": "music", "music_type": "sc", "song_id": song_id,
                     "link": f"https://fujiwarahaji.me/music/sc/{song_id}",
                     "api": f"https://{self.FUJI}/v4/music?id={song_id}"}
                    for song_id, (name, _) in self.fuji_songs.items()
                ])
            if path == "v4/music" and int(params["id"]) in self.fuji_songs:
                return httpx.Response(200, json=self._fuji_song(int(params["id"])))
            if path == "v4/tax" and int(params["id"]) in self.fuji_discs:
                return httpx.Response(200, json=self._fuji_disc(self.fuji_discs[int(params["id"])]))
        return httpx.Response(404, text="<html>Not Found</html>")

    def _discography(self) -> str:
        def links(items: list[tuple[str, str]]) -> str:
            return "".join(
                f'<a href="https://{self.LANTIS}/releaseinfo/{slug}/" title="{html.escape(title)}">'
                f'<img src="x.jpg" class="hv"></a>\n'
                for slug, title in items
            )

        return (
            '<section id="discographys" class="mb96">\n'
            '<div class="CD_area"><div class="cat_cd">'
            '<h3><img src="/images/common/dsc_tit_cd.png" alt="CD" height="19"></h3></div>\n'
            '<div class="list"><div class="dsc_box mb0"><h4><span>■CD</span></h4>\n'
            f"{links([(r.slug, r.title) for r in self.releases])}</div></div>\n</div>\n"
            '<div class="BD_area"><div class="cat_cd">'
            '<h3><img src="/images/common/dsc_tit_bd.png" alt="CD" height="19"></h3></div>\n'
            f'<div class="list"><div class="dsc_box mb0">\n{links(self.blu_rays)}</div></div>\n</div>\n'
            "</section>"
        )

    def _release_page(self, release: LantisRelease) -> str:
        def paragraph(text: str) -> str:
            return "<p>" + "<br />\n".join(html.escape(line) for line in text.split("\n")) + "</p>"

        year, month, day = release.date.split("/")
        banner = release.banner_date or f"{year}.{int(month):02}.{int(day):02}"
        artist = f"アーティスト：{release.artist}"
        if release.artist_members:
            artist += f"\n{release.artist_members}"
        facts = f"発売日：{release.date}\n品番：{release.catalog}\n価格：1,980円（10%税込）"
        index = "\n".join(paragraph(p) for p in release.index)
        return (
            '<html><body><section id="release"><div class="release_box cd">\n'
            f'<div class="titles">\n<div class="date">{banner} RELEASE</div>\n'
            f"<h2>{html.escape(release.title)}</h2>\n</div>\n"
            f'<div class="release_contents">\n{paragraph(artist)}\n{paragraph(facts)}\n'
            '<h3><img src="/images/common/release_index.png" alt="インデックス"></h3>\n'
            f"{index}\n"
            '<h3><img src="/images/common/release_information.png" alt="インフォメーション"></h3>\n'
            "<p>描き下ろしイラストジャケット</p>\n"
            "</div><!--release_contents-->\n</div></section>\n"
            f"{self._discography()}</body></html>"
        )

    def _fuji_disc_ref(self, disc: FujiDisc) -> dict:
        return {
            "name": disc.name, "type": "disc", "tax_id": disc.tax_id,
            "link": f"https://fujiwarahaji.me/disc/{disc.tax_id}",
            "api": f"https://{self.FUJI}/v4/tax?id={disc.tax_id}",
        }

    @staticmethod
    def _fuji_idol(name: str) -> dict:
        return {"name": name, "type": "idol", "production": "sc", "cv": "某声優"}

    def _fuji_song(self, song_id: int) -> dict:
        name, discs = self.fuji_songs[song_id]
        return {
            "name": name, "type": "music", "song_id": song_id,
            "link": f"https://fujiwarahaji.me/music/sc/{song_id}",
            "api": f"https://{self.FUJI}/v4/music?id={song_id}",
            "member": [], "disc": [self._fuji_disc_ref(self.fuji_discs[d]) for d in discs],
        }

    def _fuji_disc(self, disc: FujiDisc) -> dict:
        return {
            **self._fuji_disc_ref(disc), "cat": "", "flag": "", "setlist": True,
            "song": [
                {
                    "name": name, "type": "music", "music_type": "sc", "song_text": "",
                    "unit": [
                        {"name": unit, "type": "unit", "member": [self._fuji_idol(m) for m in members]}
                        for unit, members in units
                    ],
                    "member": [self._fuji_idol(m) for m in idols] or None,
                    "member_text": "", "flag": flags,
                }
                for name, units, idols, flags in disc.tracks
            ],
        }

    def _query(self, query: str) -> dict:
        detail = "https://sparql.crssnky.xyz/imasrdf/RDFs/detail/"

        def uri(value: str) -> dict:
            return {"type": "uri", "value": value}

        def ja(value: str) -> dict:
            return {"type": "literal", "xml:lang": "ja", "value": value}

        rows: list[dict] = []
        if "imas:Unit" in query:
            for name, (kana, members) in self.sparql_units.items():
                for member in members:
                    row = {"unit": uri(detail + name.replace(" ", "")), "name": ja(name), "member": ja(member)}
                    if kana is not None:
                        row["kana"] = ja(kana)
                    rows.append(row)
        elif "imas:Staff" in query:
            for staff in self.staff:
                rows.append({
                    "staff": uri(detail + staff["id"]), "name": ja(staff["name"]),
                    "kana": ja(staff["kana"]), "position": ja(staff["position"]),
                    "officeName": ja("283プロダクション"),
                })
        elif "imas:Idol" in query:
            for idol in self.idols:
                rows.append({
                    "idol": uri(detail + idol["id"]), "name": ja(idol["name"]),
                    "kana": ja(idol["kana"]), "cv": ja(idol["cv"]),
                })
        return {"head": {"vars": []}, "results": {"bindings": rows}}

    def _index(self) -> str:
        items = "".join(
            f'<li class="idol-item js--scroll__trigger">\n'
            f'  <a href="./{slug}" id="{slug}" class="idol-link">\n'
            f'    <div class="idol-logo unit{n}"><img loading="lazy" src="x.png" alt="{slug}"></div>\n'
            f"  </a>\n</li>\n"
            for n, (slug, *_) in enumerate(self.official_units, 1)
        )
        return f'<html><body><main class="idol-unit"><ul class="idol-list">\n{items}</ul></main></body></html>'

    def _unit_page(self, slug: str, logo: str, name: str, members: list[str]) -> str:
        names = "".join(
            f'<li class="idol-group__name" data-id="{n}">\n'
            f'<a href="../../idol/{slug}/m{n}/" class="idol-group__name--text">{member}</a>\n</li>\n'
            for n, member in enumerate(members, 1)
        )
        nav = "".join(
            f'<li class="idol-nav__unit--btn"><a href="../../idol/{other}" class="idol-nav__unit--item">'
            f'<img loading="lazy" src="logo_{other}.png" alt="{other_logo}"></a></li>\n'
            for other, other_logo, *_ in self.official_units
        )
        return (
            f'<html><body><main class="idol common-main" data-id="{slug}">\n'
            f'<ul class="idol-group__list">\n{names}</ul>\n'
            f'<div class="idol-group__logo">\n<picture>\n'
            f'<img loading="lazy" src="../../assets/img/idol/{slug}/logo.png" alt="{logo}">\n'
            f'</picture>\n<p class="idol-group__logo--name">{name}</p>\n</div>\n'
            f'<ul class="idol-nav__unit">\n{nav}</ul>\n</main></body></html>'
        )
