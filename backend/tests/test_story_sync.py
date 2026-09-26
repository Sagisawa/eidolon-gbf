"""Syncing the story corpus with the game (`eidolon story sync`): SCTranslationData's
translations, then the card and event episodes they lack from the ShinyColorsDB mirror
(the spec's cut point B), checked by querying the corpus afterwards."""

import time
from pathlib import Path

import httpx
import pytest

from eidolon.characters import load_characters
from eidolon.corpus import CatalogEntry, Line, StoryCorpus
from eidolon.mirror import Mirror
from eidolon.story_sync import PROBE_AHEAD, SyncReport, sync_stories
from tests.conftest import Admin, CharacterConfig
from tests.fakes import FakeEmbedder, FakeShinyColorsDB
from tests.stories import (
    EVENT_TRANSLATED,
    KOGANE_SCRIPT,
    MANO_CARD,
    MANO_CARD_SCRIPT,
    MANO_CARD_SECOND_SCRIPT,
    MANO_CARD_TRANSLATED,
    MANO_SUPPORT_SCRIPT,
    event_frames,
    write_story,
)

MANO_P_SSR = "8f051e66-mano-p-ssr"
MANO_S_SSR = "0f6e2b14-mano-s-ssr"
MANO_P_R = "42b375e0-mano-p-r"
KOGANE_P_SSR = "9c1d0a2e-kogane-p-ssr"


@pytest.fixture
def mirror_site() -> FakeShinyColorsDB:
    """Mano's cards (one with an episode not yet on the mirror, one with no episodes)
    and a card of Kogane's whose first episode SCTranslationData has translated."""
    site = FakeShinyColorsDB()
    site.add_card(
        1, MANO_P_SSR, MANO_CARD, "P_SSR",
        [(200100401, "ほわほわアイドル"), (200100402, "真乃ならできる"), (200100403, "成長の証")],
    )
    site.add_card(1, MANO_S_SSR, "【トリプルイルミネーション】櫻木真乃", "S_SSR", [(300100401, "始まりのステップ")])
    site.add_card(1, MANO_P_R, "【白いツバサ】櫻木真乃", "P_R")
    site.add_card(
        4, KOGANE_P_SSR, "【ばりうまかブルース】月岡恋鐘", "P_SSR",
        [(201100401, "長崎の味"), (201100402, "ちゃんぽんば作ったけん")],
    )
    site.add_script("produce_events/200100401", MANO_CARD_SCRIPT)
    site.add_script("produce_events/200100402", MANO_CARD_SECOND_SCRIPT)
    site.add_script("produce_events/300100401", MANO_SUPPORT_SCRIPT)
    site.add_script("produce_events/201100401", KOGANE_SCRIPT)
    site.add_script("produce_events/201100402", KOGANE_SCRIPT)
    return site


class Syncer:
    def __init__(
        self, tmp_path: Path, characters: CharacterConfig, story: Path, site: FakeShinyColorsDB
    ) -> None:
        self.embedder = FakeEmbedder()
        self.corpus = StoryCorpus(tmp_path / "eidolon.db", self.embedder)
        self.story = story
        self.cache = tmp_path / "mirror"
        self._characters = characters
        self._site = site

    async def run(
        self, idols: list[int] | None = None, event_names: dict[int, str] | None = None
    ) -> SyncReport:
        characters = load_characters(self._characters.path)
        mirror = self._site.mirror()
        try:
            return await sync_stories(
                self.story, self.cache, self.corpus, characters.values(), mirror,
                event_names=event_names, idols=idols,
            )
        finally:
            await mirror.aclose()


@pytest.fixture
def syncer(tmp_path: Path, characters: CharacterConfig, story: Path, mirror_site: FakeShinyColorsDB):
    syncer = Syncer(tmp_path, characters, story, mirror_site)
    yield syncer
    syncer.corpus.close()


async def test_card_episodes_the_translations_lack_come_in_under_the_cards_name_and_title(
    syncer: Syncer,
):
    report = await syncer.run()

    episode = syncer.corpus.get("produce_events/200100401")
    assert episode is not None
    assert (episode.category, episode.source, episode.title) == ("P卡剧情", MANO_CARD, "ほわほわアイドル")
    assert episode.imported_from == "json" and episode.cast == {"mano"}
    # Lines as the translations have them: LF line breaks, no translation.
    assert episode.lines[:2] == (
        Line("プロデューサー", "真乃、ここにいたのか\n探したぞ"),
        Line("真乃", "ほわ……\n鳩さんたちと公園で遊んでいました"),
    )
    assert all(line.zh is None for line in episode.lines)
    support = syncer.corpus.get("produce_events/300100401")
    assert support is not None
    assert (support.category, support.source, support.title) == (
        "S卡剧情", "【トリプルイルミネーション】櫻木真乃", "始まりのステップ"
    )
    assert report.untranslated.added == 4  # Mano's three, Kogane's second
    assert report.mirror_error is None


async def test_canon_rules_apply_to_the_mirrors_episodes(syncer: Syncer):
    await syncer.run()

    episode = syncer.corpus.get("produce_events/200100401")
    assert episode is not None
    texts = [line.ja for line in episode.lines]
    # Both reactions, but not which option the producer picked.
    assert "はいっ、鳩さんは友達です" in texts and "あっ！　すみません……" in texts
    assert "鳩が好きなんだな" not in texts and "レッスンの時間だぞ" not in texts


async def test_the_catalog_shows_the_mirrors_episodes_by_card(syncer: Syncer):
    await syncer.run()

    catalog = {source.source: source for source in syncer.corpus.catalog("mano")}
    assert catalog[MANO_CARD].category == "P卡剧情"
    assert catalog[MANO_CARD].episodes == (
        CatalogEntry("produce_events/200100401", "ほわほわアイドル"),
        CatalogEntry("produce_events/200100402", "真乃ならできる"),
    )


async def test_a_translated_episode_is_neither_downloaded_nor_replaced(
    syncer: Syncer, mirror_site: FakeShinyColorsDB
):
    report = await syncer.run()

    translated = syncer.corpus.get("produce_events/201100401")
    assert translated is not None
    assert translated.imported_from == "csv"
    assert translated.lines[0].zh == "长崎的什锦面超好吃的！"
    assert "produce_events/201100401" not in mirror_site.sent
    assert report.translations_kept == 1


async def test_a_translation_that_arrives_later_replaces_the_untranslated_episode_under_the_same_card(
    syncer: Syncer,
):
    await syncer.run()
    # SCTranslationData translates it, filing it under the card's name as the game gives it.
    write_story(
        syncer.story, f"櫻木真乃/{MANO_CARD}/ほわほわアイドル.csv", MANO_CARD_TRANSLATED,
        "produce_events/200100401",
    )

    report = await syncer.run()

    episode = syncer.corpus.get("produce_events/200100401")
    assert episode is not None
    assert episode.imported_from == "csv"
    assert episode.lines[0].zh == "呼哇……\n我在公园和鸽子们玩"
    assert len([e for e in syncer.corpus.list_episodes() if e.id == "produce_events/200100401"]) == 1
    catalog = {source.source: source for source in syncer.corpus.catalog("mano")}
    assert [entry.episode_id for entry in catalog[MANO_CARD].episodes] == [
        "produce_events/200100401",
        "produce_events/200100402",
    ]
    assert report.translated.untranslated_replaced == 1
    assert report.untranslated.imported == 0


async def test_failure_endings_are_skipped(syncer: Syncer):
    report = await syncer.run()

    assert report.skipped_failures == 3
    assert syncer.corpus.get("produce_events/600100102") is None


async def test_syncing_again_downloads_and_embeds_nothing(
    syncer: Syncer, mirror_site: FakeShinyColorsDB
):
    await syncer.run()
    mirror_site.sent.clear()
    syncer.embedder.documents.clear()

    report = await syncer.run()

    assert mirror_site.sent == []
    assert syncer.embedder.documents == []
    assert (report.downloaded, report.embedded_passages, report.untranslated.imported) == (0, 0, 0)
    assert report.translations_kept == 0  # no card was asked about again
    assert syncer.corpus.get("produce_events/200100401") is not None


async def test_an_unchanged_card_is_not_asked_about_again(
    syncer: Syncer, mirror_site: FakeShinyColorsDB
):
    await syncer.run()
    mirror_site.requests.clear()

    await syncer.run()

    asked = {str(r.url) for r in mirror_site.requests}
    assert not any("201100402" in url or KOGANE_P_SSR in url for url in asked)
    assert not any("300100401" in url or MANO_S_SSR in url for url in asked)


async def test_a_changed_card_is_checked_but_only_changed_scripts_are_downloaded_again(
    syncer: Syncer, mirror_site: FakeShinyColorsDB
):
    await syncer.run()
    mirror_site.update_card(MANO_P_SSR)
    changed = [*MANO_CARD_SECOND_SCRIPT, {"id": 2001004020030, "speaker": "真乃", "text": "やってみます"}]
    mirror_site.add_script("produce_events/200100402", changed)
    mirror_site.sent.clear()

    report = await syncer.run()

    assert mirror_site.sent == ["produce_events/200100402"]
    episode = syncer.corpus.get("produce_events/200100402")
    assert episode is not None and episode.lines[-1].ja == "やってみます"
    assert (report.untranslated.imported, report.untranslated.added) == (1, 0)


async def test_a_script_the_mirror_lacks_is_no_error_and_comes_in_once_it_is_there(
    syncer: Syncer, mirror_site: FakeShinyColorsDB
):
    report = await syncer.run()

    assert report.mirror_error is None
    assert report.missing == 1
    assert syncer.corpus.get("produce_events/200100403") is None

    mirror_site.add_script("produce_events/200100403", MANO_CARD_SECOND_SCRIPT)
    await syncer.run()

    episode = syncer.corpus.get("produce_events/200100403")
    assert episode is not None and (episode.source, episode.title) == (MANO_CARD, "成長の証")


async def test_when_the_mirror_is_unreachable_the_translations_still_come_in(
    syncer: Syncer, mirror_site: FakeShinyColorsDB
):
    mirror_site.down = True

    report = await syncer.run()

    assert report.mirror_error is not None
    park = syncer.corpus.get("produce_events/100100101")
    assert park is not None and park.imported_from == "csv"
    assert syncer.corpus.get("produce_events/200100401") is None


async def test_an_api_answer_shaped_unlike_before_is_a_mirror_error(
    syncer: Syncer, mirror_site: FakeShinyColorsDB
):
    del mirror_site.idols[4][0]["cardUuid"]

    report = await syncer.run()

    assert report.mirror_error is not None and "idolInfo" in report.mirror_error
    # Mano's cards, listed before Kogane's, still come in.
    assert syncer.corpus.get("produce_events/200100401") is not None


async def test_a_sync_the_mirror_broke_off_picks_up_where_it_stopped(
    syncer: Syncer, mirror_site: FakeShinyColorsDB
):
    # Idols, Mano's cards, her P_SSR and its first two scripts, then the mirror goes away.
    mirror_site.down_after = 5

    report = await syncer.run()

    assert report.mirror_error is not None
    assert mirror_site.sent == ["produce_events/200100401", "produce_events/200100402"]
    # What was downloaded before it failed is imported.
    assert syncer.corpus.get("produce_events/200100401") is not None
    mirror_site.down_after = None
    mirror_site.sent.clear()
    syncer.embedder.documents.clear()

    report = await syncer.run()

    assert report.mirror_error is None
    assert "produce_events/200100401" not in mirror_site.sent
    assert "produce_events/200100402" not in mirror_site.sent
    assert syncer.corpus.get("produce_events/300100401") is not None
    assert not any("ほわほわアイドル" in text for text in syncer.embedder.documents)


async def test_a_sync_the_embedding_service_broke_off_picks_up_without_downloading_again(
    syncer: Syncer, mirror_site: FakeShinyColorsDB
):
    await syncer.run()
    syncer.corpus.remove("produce_events/200100401")  # as if embedding failed before it was saved
    mirror_site.sent.clear()

    await syncer.run()

    assert mirror_site.sent == []
    assert syncer.corpus.get("produce_events/200100401") is not None


async def test_only_the_idols_asked_for_are_synced(syncer: Syncer, mirror_site: FakeShinyColorsDB):
    await syncer.run(idols=[1])

    assert syncer.corpus.get("produce_events/200100401") is not None
    assert syncer.corpus.get("produce_events/201100402") is None
    assert not any("idolList" in str(r.url) for r in mirror_site.requests)
    assert not any("game_event_communications" in str(r.url) for r in mirror_site.requests)


async def test_requests_go_out_one_at_a_time_with_a_pause_between(mirror_site: FakeShinyColorsDB):
    times: list[float] = []

    def handle(request: httpx.Request) -> httpx.Response:
        times.append(time.monotonic())
        return httpx.Response(200, json={"cardLists": []})

    mirror = Mirror(httpx.AsyncClient(transport=httpx.MockTransport(handle)), interval=0.05)
    try:
        for idol in (1, 2, 3):
            await mirror.cards(idol)
    finally:
        await mirror.aclose()

    assert all(later - earlier >= 0.045 for earlier, later in zip(times, times[1:]))


def test_the_sync_command_reports_what_it_did(
    admin: Admin,
    story: Path,
    characters: CharacterConfig,
    mirror_site: FakeShinyColorsDB,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-test")
    monkeypatch.setattr("eidolon.mirror.Mirror", lambda: mirror_site.mirror())
    monkeypatch.setattr("eidolon.embedding.SiliconFlowEmbedder", lambda *_: _ClosableEmbedder())
    args = ["story", "sync", "--story", str(story), "--cache", str(tmp_path / "mirror")]

    code, out, err = admin.invoke(*args, "--characters", str(characters.path))

    assert code == 0, err
    assert "汉化版：新增 4 段" in out
    assert "原文剧情：下载 4 个剧本，新增 4 段" in out
    assert "有 1 段已有汉化版" in out
    assert "镜像上还没有" in out  # Mano's third episode
    assert "共跳过 3 段失败结局" in out


def test_the_sync_command_exits_2_when_the_mirror_is_unreachable(
    admin: Admin,
    story: Path,
    characters: CharacterConfig,
    mirror_site: FakeShinyColorsDB,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    mirror_site.down = True
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-test")
    monkeypatch.setattr("eidolon.mirror.Mirror", lambda: mirror_site.mirror())
    monkeypatch.setattr("eidolon.embedding.SiliconFlowEmbedder", lambda *_: _ClosableEmbedder())
    args = ["story", "sync", "--story", str(story), "--cache", str(tmp_path / "mirror")]

    code, out, err = admin.invoke(*args, "--characters", str(characters.path))

    assert code == 2
    assert "镜像" in err
    assert "汉化版：新增 4 段" in out


# Events. SCTranslationData has the first episode of event 004 (see `write_sample_stories`),
# so events up to 004 are known; the mirror has events 002 (which SCTranslationData lacks)
# and 004, and after it 005 and 007, 006 having been skipped.
EVENTS_ON_THE_MIRROR = {2: 2, 4: 2, 5: 2, 7: 1}
LIGHT_UP = "Light up the illumination"  # event 004's directory in SCTranslationData


def event(number: int, episode: int) -> str:
    return f"game_event_communications/4001{number:03d}{episode:02d}"


def event_requests(site: FakeShinyColorsDB) -> list[str]:
    return [str(r.url) for r in site.requests if "game_event_communications" in str(r.url)]


@pytest.fixture
def events(mirror_site: FakeShinyColorsDB) -> FakeShinyColorsDB:
    for number, episodes in EVENTS_ON_THE_MIRROR.items():
        for episode in range(1, episodes + 1):
            mirror_site.add_script(event(number, episode), event_frames(number, episode))
    return mirror_site


async def test_events_the_translations_lack_are_filled_in(syncer: Syncer, events: FakeShinyColorsDB):
    await syncer.run()

    gap = [syncer.corpus.get(event(2, episode)) for episode in (1, 2)]
    assert all(e is not None and e.category == "活动剧情" and e.imported_from == "json" for e in gap)
    assert [e.lines[0].ja for e in gap if e is not None] == [
        "イベント2の第1話です\nほわっ", "イベント2の第2話です\nほわっ"
    ]
    # The episode SCTranslationData lacks of an event it has.
    second = syncer.corpus.get(event(4, 2))
    assert second is not None and second.imported_from == "json"
    translated = syncer.corpus.get(event(4, 1))
    assert translated is not None and translated.imported_from == "csv"
    assert event(4, 1) not in events.sent
    # Numbers the mirror has nothing under are no error.
    assert syncer.corpus.get(event(1, 1)) is None and syncer.corpus.get(event(3, 1)) is None


async def test_events_after_the_latest_are_found_even_past_a_skipped_number(
    syncer: Syncer, events: FakeShinyColorsDB
):
    report = await syncer.run()

    for number, episodes in ((5, 2), (7, 1)):
        found = [syncer.corpus.get(event(number, e)) for e in range(1, episodes + 1)]
        assert all(e is not None for e in found)
        assert syncer.corpus.get(event(number, episodes + 1)) is None
    assert report.mirror_error is None


async def test_syncing_again_costs_only_a_few_404s_for_events(
    syncer: Syncer, events: FakeShinyColorsDB
):
    await syncer.run()
    events.requests.clear()
    events.sent.clear()
    syncer.embedder.documents.clear()

    report = await syncer.run()

    assert events.sent == [] and syncer.embedder.documents == []
    # The latest event's next episode, and the numbers after it.
    assert len(event_requests(events)) == PROBE_AHEAD + 1
    assert report.untranslated.imported == 0


async def test_a_new_event_on_the_mirror_comes_in_at_the_next_sync(
    syncer: Syncer, events: FakeShinyColorsDB
):
    await syncer.run()
    events.add_script(event(8, 1), event_frames(8, 1))

    await syncer.run()

    assert syncer.corpus.get(event(8, 1)) is not None


async def test_events_are_named_from_the_table_or_left_unnamed(
    syncer: Syncer, events: FakeShinyColorsDB
):
    report = await syncer.run(event_names={2: "はじめてのイベント", 4: LIGHT_UP})

    named = syncer.corpus.get(event(2, 2))
    assert named is not None and (named.source, named.title) == ("はじめてのイベント", "第2話")
    unnamed = syncer.corpus.get(event(5, 1))
    assert unnamed is not None and (unnamed.source, unnamed.title) == ("活动剧情 005", "第1話")
    assert report.unnamed_events == [5, 7]
    # Grouped with the episode SCTranslationData has, which is filed under the same name.
    translated, second = syncer.corpus.get(event(4, 1)), syncer.corpus.get(event(4, 2))
    assert translated is not None and second is not None
    assert second.source == translated.source == LIGHT_UP


async def test_an_event_the_table_lacks_takes_the_name_its_translated_episodes_have(
    syncer: Syncer, events: FakeShinyColorsDB
):
    report = await syncer.run()

    second = syncer.corpus.get(event(4, 2))
    assert second is not None and second.source == LIGHT_UP
    assert 4 not in report.unnamed_events


async def test_the_catalog_shows_events_by_name_with_episodes_in_order(
    syncer: Syncer, events: FakeShinyColorsDB
):
    await syncer.run(event_names={2: "はじめてのイベント"})

    catalog = {source.source: source for source in syncer.corpus.catalog("mano")}
    assert catalog["はじめてのイベント"].category == "活动剧情"
    assert catalog["はじめてのイベント"].episodes == (
        CatalogEntry(event(2, 1), "第1話"),
        CatalogEntry(event(2, 2), "第2話"),
    )
    assert [e.title for e in catalog["活动剧情 005"].episodes] == ["第1話", "第2話"]


async def test_a_name_filled_in_later_renames_the_event_at_the_next_sync(
    syncer: Syncer, events: FakeShinyColorsDB
):
    await syncer.run()
    events.sent.clear()

    report = await syncer.run(event_names={5: "新しいイベント"})

    assert events.sent == []
    catalog = {source.source: source for source in syncer.corpus.catalog("mano")}
    assert "活动剧情 005" not in catalog
    assert [e.episode_id for e in catalog["新しいイベント"].episodes] == [event(5, 1), event(5, 2)]
    assert syncer.corpus.episode_ids("game_event_communications/4001005") == [event(5, 1), event(5, 2)]
    assert report.unnamed_events == [2, 7]


async def test_a_translation_that_arrives_later_replaces_the_untranslated_event_episode(
    syncer: Syncer, events: FakeShinyColorsDB
):
    names = {2: "はじめてのイベント"}
    await syncer.run(event_names=names)
    write_story(
        syncer.story, "283活动剧情/はじめてのイベント/第1話.csv", EVENT_TRANSLATED, event(2, 1)
    )

    report = await syncer.run(event_names=names)

    episode = syncer.corpus.get(event(2, 1))
    assert episode is not None and episode.imported_from == "csv"
    assert episode.lines[0].zh == "这是活动2的第1话\n呼哇"
    catalog = {source.source: source for source in syncer.corpus.catalog("mano")}
    assert [e.episode_id for e in catalog["はじめてのイベント"].episodes] == [event(2, 1), event(2, 2)]
    assert report.translated.untranslated_replaced == 1


async def test_when_the_api_is_down_events_still_come_from_the_viewer(
    syncer: Syncer, events: FakeShinyColorsDB
):
    del events.idols[1][0]["cardUuid"]

    report = await syncer.run()

    assert report.mirror_error is not None
    assert syncer.corpus.get(event(2, 1)) is not None


def test_the_sync_command_names_events_from_the_table(
    admin: Admin,
    story: Path,
    characters: CharacterConfig,
    events: FakeShinyColorsDB,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    names = tmp_path / "event-names.toml"
    names.write_text('[events]\n002 = "はじめてのイベント"\n4 = "Light up the illumination"\n', encoding="utf-8")
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-test")
    monkeypatch.setattr("eidolon.mirror.Mirror", lambda: events.mirror())
    monkeypatch.setattr("eidolon.embedding.SiliconFlowEmbedder", lambda *_: _ClosableEmbedder())
    args = ["story", "sync", "--story", str(story), "--cache", str(tmp_path / "mirror")]

    code, out, err = admin.invoke(*args, "--characters", str(characters.path), "--events", str(names))

    assert code == 0, err
    assert "活动名对照表里还没有这些活动，暂用「活动剧情 NNN」：005、007" in out


@pytest.mark.parametrize(
    ("content", "complaint"),
    [
        (None, "找不到活动名对照表"),
        ('[events]\n097 = "a"\nabc = "b"\n', "abc"),
        ('[events]\n097 = ""\n', "097"),
        ('[events]\n000 = "a"\n', "000"),
        ("[events\n", "格式有误"),
    ],
)
def test_the_sync_command_rejects_a_broken_table_of_event_names(
    admin: Admin,
    story: Path,
    characters: CharacterConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    content: str | None,
    complaint: str,
):
    names = tmp_path / "event-names.toml"
    if content is not None:
        names.write_text(content, encoding="utf-8")
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-test")

    err = admin.fails(
        "story", "sync", "--story", str(story), "--characters", str(characters.path),
        "--events", str(names),
    )

    assert complaint in err


def test_the_sync_command_reports_a_missing_story_directory(admin: Admin, tmp_path: Path):
    err = admin.fails("story", "sync", "--story", str(tmp_path / "nowhere"))

    assert "nowhere" in err


class _ClosableEmbedder(FakeEmbedder):
    async def aclose(self) -> None:
        pass
