"""Importing SCTranslationData story CSVs into the story corpus (the spec's cut point
B), checked by querying the corpus afterwards."""

from pathlib import Path

import pytest

from eidolon.characters import load_characters
from eidolon.corpus import Episode, Line, StoryCorpus
from eidolon.story_import import ImportReport, import_csv_directory, is_failure_ending
from tests.conftest import Admin, CharacterConfig
from tests.fakes import FakeEmbedder

PRODUCER = "0000000000000"

# Mano's first W.I.N.G. episode: the producer, the company president and Mano.
PARK = [
    (PRODUCER, "プロデューサー", "（いよいよ俺が、アイドルを\\nプロデュースする時が来た）", "（终于到了我培育偶像的时候了）"),
    ("1902001010010", "社長", "おはよう、お前を待っていたぞ", "早上好，我正等着你呢"),
    ("1001001010110", "真乃", "公園で鳩と一緒に歌っていました", "我在公园和鸽子一起唱歌"),
    ("select", "", "歌が好きなのか？", "喜欢唱歌吗？"),
    ("select", "", "鳩が好きなのか？", "喜欢鸽子吗？"),
    ("1001001010120", "真乃", "ほわっ……はい、どっちも好きです", "呼哇……嗯，两个都喜欢"),
]
# Won the W.I.N.G. final.
WON = [
    ("6001001060050", "真乃", "……ゆ、優勝、したんですねっ", "……优，优胜了呢"),
    (PRODUCER, "プロデューサー", "……ああ、夢なんかじゃないぞ", "……是啊，不是在做梦哦"),
]
# Knocked out of W.I.N.G., under a file name that doesn't say so.
KNOCKED_OUT = [
    ("6001001020010", "真乃", "私……負けちゃいました……", "我……失败了……"),
]
SEASON_FAILED = [
    ("7902001020010", "社長", "結果は聞いた", ""),
    ("7001001020010", "真乃", "だめだったんですね……", "不行呢……"),
]
AUDITION_LOST = [
    ("5001001000120010", "真乃", "ごめんなさい……", "对不起……"),
]
# A card of Kogane's, with a joint line shared with Mano.
KOGANE_CARD = [
    ("2011004010010", "恋鐘", "長崎のちゃんぽん、ばりうまかよ！", "长崎的什锦面超好吃的！"),
    ("2011004010020", "恋鐘の母", "恋鐘、写真ば撮ろうか", "恋钟，拍张照片吧"),
    ("2011004010030", "真乃＆恋鐘", "はいっ！", "好的！"),
]
# An event episode with neither Mano nor Kogane speaking.
HIORI_EVENT = [
    ("4001004010010", "灯織", "写真の撮影、頑張ります", "拍照，我会加油的"),
    ("4001004010020", "めぐる", "公園で撮るんだって！", "听说要在公园拍！"),
]


def write_story(root: Path, relative: str, rows: list[tuple[str, str, str, str]], info: str | None) -> None:
    lines = ["id,name,text,trans", *(",".join(row) for row in rows)]
    if info is not None:
        lines += [f"info,{info}.json,,", "译者,テスト,,"]
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    # SCTranslationData files come with a BOM and CRLF line endings as often as not.
    path.write_text("﻿" + "\r\n".join(lines) + "\r\n", encoding="utf-8")


@pytest.fixture
def story(tmp_path: Path) -> Path:
    root = tmp_path / "story"
    write_story(root, "櫻木真乃/W.I.N.G.編/公園の歌声.csv", PARK, "produce_events/100100101")
    write_story(root, "櫻木真乃/W.I.N.G.編/決勝後コミュ.csv", WON, "produce_events/600100106")
    write_story(root, "櫻木真乃/W.I.N.G.編/produce_events_600100102.csv", KNOCKED_OUT, "produce_events/600100102")
    write_story(root, "櫻木真乃/W.I.N.G.編/シーズン1（失敗）.csv", SEASON_FAILED, "produce_events/700100102")
    write_story(root, "櫻木真乃/W.I.N.G.編/オーディション後②.csv", AUDITION_LOST, "produce_communication_auditions/500100100012")
    write_story(root, "月岡恋鐘/【ばりうまかブルース】月岡恋鐘/長崎の味.csv", KOGANE_CARD, "produce_events/201100401")
    write_story(root, "283活动剧情/Light up the illumination/第1話.csv", HIORI_EVENT, "game_event_communications/400100401")
    return root


class Importer:
    def __init__(self, database: Path, characters: CharacterConfig) -> None:
        self.embedder = FakeEmbedder()
        self.corpus = StoryCorpus(database, self.embedder)
        self._characters = characters

    async def run(self, directory: Path) -> ImportReport:
        characters = load_characters(self._characters.path)
        return await import_csv_directory(directory, self.corpus, characters.values())


@pytest.fixture
def importer(tmp_path: Path, characters: CharacterConfig):
    importer = Importer(tmp_path / "eidolon.db", characters)
    yield importer
    importer.corpus.close()


async def test_each_file_becomes_an_episode_with_source_title_category_and_lines(
    importer: Importer, story: Path
):
    await importer.run(story)

    park = importer.corpus.get("produce_events/100100101")
    assert park is not None
    assert (park.category, park.source, park.title) == ("培育剧情", "W.I.N.G.編", "公園の歌声")
    assert park.lines[0] == Line(
        "プロデューサー", "（いよいよ俺が、アイドルを\nプロデュースする時が来た）", "（终于到了我培育偶像的时候了）"
    )
    assert [line.speaker for line in park.lines] == ["プロデューサー", "社長", "真乃", "真乃"]

    card = importer.corpus.get("produce_events/201100401")
    assert card is not None
    assert (card.category, card.source) == ("P卡剧情", "【ばりうまかブルース】月岡恋鐘")
    event = importer.corpus.get("game_event_communications/400100401")
    assert event is not None
    assert (event.category, event.source, event.title) == (
        "活动剧情", "Light up the illumination", "第1話"
    )


async def test_the_producers_choices_are_dropped_but_the_characters_reaction_kept(
    importer: Importer, story: Path
):
    await importer.run(story)

    park = importer.corpus.get("produce_events/100100101")
    assert park is not None
    texts = [line.ja for line in park.lines]
    assert "歌が好きなのか？" not in texts and "鳩が好きなのか？" not in texts
    assert "ほわっ……はい、どっちも好きです" in texts


async def test_cast_is_the_configured_characters_who_speak(importer: Importer, story: Path):
    await importer.run(story)

    def cast(episode_id: str) -> frozenset[str]:
        episode = importer.corpus.get(episode_id)
        assert episode is not None
        return episode.cast

    # The producer and the president speak here too, but only Mano is cast.
    assert cast("produce_events/100100101") == {"mano"}
    # A joint line casts both; Kogane's mother is not Kogane.
    assert cast("produce_events/201100401") == {"kogane", "mano"}
    # Idols who are not configured characters are not cast.
    assert cast("game_event_communications/400100401") == frozenset()


async def test_failure_endings_are_not_imported(importer: Importer, story: Path):
    report = await importer.run(story)

    ids = {episode.id for episode in importer.corpus.list_episodes()}
    assert ids == {
        "produce_events/100100101",
        "produce_events/600100106",
        "produce_events/201100401",
        "game_event_communications/400100401",
    }
    assert report.imported == 4
    assert report.skipped_failures == 3
    assert all("負け" not in text for text in importer.embedder.documents)


async def test_importing_again_updates_in_place_without_duplicates(
    importer: Importer, story: Path
):
    await importer.run(story)
    embedded_first = len(importer.embedder.documents)

    report = await importer.run(story)

    assert len(importer.corpus.list_episodes()) == 4
    assert len(importer.corpus.list_episodes("mano")) == 3
    # Nothing changed, so nothing is embedded again.
    assert report.embedded_passages == 0
    assert len(importer.embedder.documents) == embedded_first

    revised = [*WON, ("6001001060070", "真乃", "今まで、本当にありがとうございましたっ！", "直到现在，真的非常感谢！")]
    write_story(story, "櫻木真乃/W.I.N.G.編/決勝後コミュ.csv", revised, "produce_events/600100106")
    await importer.run(story)

    won = importer.corpus.get("produce_events/600100106")
    assert won is not None
    assert [line.ja for line in won.lines][-1] == "今まで、本当にありがとうございましたっ！"
    assert len(importer.corpus.list_episodes()) == 4


async def test_search_only_finds_episodes_the_character_is_cast_in(
    importer: Importer, story: Path
):
    await importer.run(story)

    mano = await importer.corpus.search("鳩の話", "mano", limit=1)
    assert [p.episode.id for p in mano] == ["produce_events/100100101"]
    assert "公園で鳩と一緒に歌っていました" in mano[0].text

    kogane = await importer.corpus.search("鳩の話", "kogane")
    assert "produce_events/100100101" not in {p.episode.id for p in kogane}
    assert {p.episode.id for p in kogane} == {"produce_events/201100401"}

    # Hiori's event is about a photo shoot in the park, but no configured character is in it.
    for character in ("mano", "kogane"):
        hits = await importer.corpus.search("公園で写真", character)
        assert "game_event_communications/400100401" not in {p.episode.id for p in hits}


async def test_adding_a_characters_speaker_name_casts_her_on_the_next_import(
    importer: Importer, story: Path, characters: CharacterConfig
):
    await importer.run(story)
    characters.add("hiori", "風野灯織", "# 人设\n你是風野灯織。", speakers=["灯織"])

    await importer.run(story)

    hits = await importer.corpus.search("公園で写真", "hiori")
    assert [p.episode.id for p in hits] == ["game_event_communications/400100401"]


async def test_a_failure_ending_left_from_an_earlier_import_is_removed(
    importer: Importer, story: Path
):
    # As if an earlier version of the importer had not recognised it.
    await importer.corpus.save(
        [
            Episode(
                id="produce_events/600100102",
                category="培育剧情",
                source="W.I.N.G.編",
                title="敗退コミュ",
                cast=frozenset({"mano"}),
                lines=(Line("真乃", "私……負けちゃいました……"),),
            )
        ]
    )

    report = await importer.run(story)

    assert importer.corpus.get("produce_events/600100102") is None
    assert report.removed == 1
    assert "produce_events/600100102" not in {
        p.episode.id for p in await importer.corpus.search("負け", "mano")
    }


async def test_a_file_without_an_info_row_is_keyed_by_its_path(importer: Importer, tmp_path: Path):
    root = tmp_path / "story"
    write_story(root, "櫻木真乃/W.I.N.G.編/公園の歌声.csv", PARK, None)

    report = await importer.run(root)

    assert [e.id for e in importer.corpus.list_episodes()] == ["csv/櫻木真乃/W.I.N.G.編/公園の歌声"]
    assert any("info" in w for w in report.warnings)


def test_import_command_needs_the_siliconflow_key(
    admin: Admin, story: Path, characters: CharacterConfig, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)

    err = admin.fails("story", "import-csv", str(story), "--characters", str(characters.path))

    assert "SILICONFLOW_API_KEY" in err


def test_import_command_reports_a_missing_directory(admin: Admin, tmp_path: Path):
    err = admin.fails("story", "import-csv", str(tmp_path / "nowhere"))

    assert "nowhere" in err


async def test_files_translated_from_the_same_script_import_once(
    importer: Importer, story: Path
):
    # A second translation of Mano's first episode, filed elsewhere.
    write_story(story, "櫻木真乃/W.I.N.G.編/公園の歌声 (1).csv", PARK[:3], "produce_events/100100101")
    await importer.run(story)
    embedded_first = len(importer.embedder.documents)

    report = await importer.run(story)

    assert len(importer.corpus.list_episodes("mano")) == 3
    assert report.embedded_passages == 0
    assert len(importer.embedder.documents) == embedded_first
    assert any("produce_events/100100101" in w for w in report.warnings)
    # The partial copy sorts first, but the complete one is kept.
    park = importer.corpus.get("produce_events/100100101")
    assert park is not None and park.title == "公園の歌声"
    assert park.lines[-1].ja == "ほわっ……はい、どっちも好きです"


async def test_a_file_named_like_a_failure_ending_that_no_rule_catches_is_flagged(
    importer: Importer, tmp_path: Path
):
    root = tmp_path / "story"
    write_story(root, "櫻木真乃/W.I.N.G.編/新しい敗北.csv", KNOCKED_OUT, "produce_events/600100199")

    report = await importer.run(root)

    assert importer.corpus.get("produce_events/600100199") is not None
    assert any("新しい敗北" in w and "失败结局" in w for w in report.warnings)


@pytest.mark.parametrize(
    ("source_id", "failure"),
    [
        ("produce_events/600100106", False),  # W.I.N.G. won the final
        ("produce_events/600100107", True),  # W.I.N.G. lost the final
        ("produce_events/700100107", False),  # W.I.N.G. season 4 cleared
        ("produce_events/700100108", True),  # W.I.N.G. season 4 not cleared
        ("produce_events/600100302", False),  # G.R.A.D. won the preliminary
        ("produce_events/600100305", True),  # G.R.A.D. repechage, after losing it
        ("produce_events/1012003071", True),  # G.R.A.D. elimination route
        ("produce_events/101200309", False),  # G.R.A.D. true end
        ("produce_events/600100414", False),  # Landing Point: a plain success
        ("produce_communication_auditions/500100100021", False),
        ("produce_communication_auditions/500100100022", True),
        ("produce_communication_promise_results/201200100131", False),
        ("produce_communication_promise_results/201200100112", True),
    ],
)
def test_failure_endings_are_recognised_by_their_script(source_id: str, failure: bool):
    assert is_failure_ending(source_id) is failure
