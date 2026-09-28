"""Importing the world setting (`eidolon world sync`): idols, units, the office's president
and clerk from im@sparql and the official unit pages, releases and songs from Lantis with
ふじわらはじめ filling in what Lantis leaves out, driven through the command against fake
sites and checked in the data file it writes and the report it prints."""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from tests.conftest import Admin, CharacterConfig
from tests.fakes import FakeWorldSites, FujiDisc, LantisRelease

SPARQL_DETAIL = "https://sparql.crssnky.xyz/imasrdf/RDFs/detail/"
OFFICIAL = "https://shinycolors.idolmaster-official.jp/idol/"
LANTIS = "https://shinycolors.lantis.jp/releaseinfo/"

ILLUMINATION = "櫻木真乃（CV.関根 瞳）、風野灯織（CV.近藤玲奈）、八宮めぐる（CV.峯田茉優）"
SOP = "THE IDOLM@STER SHINY COLORS Song for Prism Shower of light / 快盗Vを見逃すな"
HOPEFUL = "THE IDOLM@STER SHINY COLORS HOPEFUL FE@THERS -Stella-"


def lantis_releases() -> list[LantisRelease]:
    """Four CDs in the shapes Lantis's pages come in: a unit's, whose tracks name no
    singers; a special unit's, each track with a 歌： line; one whose track lines read
    「曲名 / 角色 (CV.声优)」 but name a special unit without saying who is in it; and a
    Song for Prism single of two units, which does not say which unit sings which."""
    return [
        LantisRelease(
            "lacm-14782", "THE IDOLM@STER SHINY COLORS BRILLI@NT WING 02 ヒカリのdestination",
            "2018/7/4", "LACM-14782", "イルミネーションスターズ",
            [
                "1．ヒカリのdestination\n作詞：中村彼方　作曲・編曲：中野領太",
                "2．虹になれ\n作詞：中村彼方　作曲：中野領太",
                "3．Spread the Wings!!（イルミネーションスターズ Ver.）",
                "4．スペシャルオーディオドラマ「輝く笑顔に向かって」",
            ],
            artist_members=ILLUMINATION,
        ),
        LantisRelease(
            "laca-15861", "THE IDOLM@STER SHINY COLORS COLORFUL FE@THERS -Stella-",
            "2021/1/20", "LACA-15861", "Team.Stella",
            [
                "1．プラニスフィア ～planisphere～\n歌：Team.Stella\n作詞：松井洋平",
                "2．ありったけの輝きで\n歌：櫻木真乃（CV.関根 瞳）",
                "3．アポイント・シグナル\n歌：月岡恋鐘（CV.礒部花凜）",
                "4．ありったけの輝きで（Off Vocal）",
            ],
            artist_members="櫻木真乃（CV.関根 瞳）、月岡恋鐘（CV.礒部花凜）、小宮果穂（CV.河野ひより）",
        ),
        LantisRelease(
            "laca-25301", HOPEFUL, "2026/9/16", "LACA-25301", "Team.Stella",
            [
                "1. MAGICAL FOREST / 櫻木真乃 (CV.関根 瞳)\n作詞：渡邊亜希子　作曲：石黑剛、常楽寺澪",
                "2. 恋するクオリア / 月岡恋鐘 (CV.礒部花凜)",
                "3. プラニスフィア ～planisphere～ -9 colors- / Team.Stella",
            ],
        ),
        LantisRelease(
            "lacm-24634", f"{SOP} 【イルミネーションスターズ盤】", "2025/1/22", "LACM-24634",
            "イルミネーションスターズ / 放課後クライマックスガールズ",
            [
                "1．Shower of light", "2．快盗Vを見逃すな",
                "3．Shower of light (Game Size)", "4．Shower of light (Off Vocal)",
            ],
        ),
    ]


def fuji_discs() -> list[FujiDisc]:
    """ふじわらはじめ's discs, as it keeps them: it names each song as it was first
    released, whatever version a disc has, and a special unit's song sometimes by its
    idols alone, without the special unit's name."""
    return [
        FujiDisc(4654, SOP, [
            ("Shower of light", [("イルミネーションスターズ", ["櫻木真乃", "風野灯織", "八宮めぐる"])], [], ["orig"]),
            ("快盗Vを見逃すな", [("放課後クライマックスガールズ", ["小宮果穂"])], [], ["orig"]),
            ("Shower of light", [("イルミネーションスターズ", ["櫻木真乃", "風野灯織", "八宮めぐる"])], [], ["gamever"]),
            ("Shower of light", [], [], ["offvocal"]),
        ]),
        FujiDisc(5000, HOPEFUL, [
            ("MAGICAL FOREST", [], ["櫻木真乃"], ["orig"]),
            ("プラニスフィア ～planisphere～", [], ["櫻木真乃", "月岡恋鐘", "小宮果穂", "八宮めぐる"], []),
        ]),
    ]

IDOLS = [
    ("Sakuragi_Mano", "櫻木真乃", "さくらぎまの", "関根瞳"),
    ("Kazano_Hiori", "風野灯織", "かざのひおり", "近藤玲奈"),
    ("Hachimiya_Meguru", "八宮めぐる", "はちみやめぐる", "峯田茉優"),
    ("Tsukioka_Kogane", "月岡恋鐘", "つきおかこがね", "礒部花凜"),
    ("Tanaka_Mamimi", "田中摩美々", "たなかまみみ", "菅沼千紗"),
    ("Komiya_Kaho", "小宮果穂", "こみやかほ", "河野ひより"),
]


@pytest.fixture
def sites() -> FakeWorldSites:
    """Six idols in three units, one of which the official site names only in Japanese
    under its logo, and a special unit im@sparql lists beside them."""
    sites = FakeWorldSites()
    sites.idols = [dict(id=i, name=n, kana=k, cv=cv) for i, n, k, cv in IDOLS]
    sites.staff = [
        dict(id="Amai_Tsutomu", name="天井努", kana="あまいつとむ", position="社長"),
        dict(id="Nanakusa_Hazuki", name="七草はづき", kana="ななくさはづき", position="事務員"),
    ]
    sites.sparql_units = {
        "illuminationSTARS": ("いるみねーしょんすたーず", ["櫻木真乃", "風野灯織", "八宮めぐる"]),
        "L'Antica": ("あんてぃーか", ["月岡恋鐘", "田中摩美々"]),
        "放課後クライマックスガールズ": ("ほうかごくらいまっくすがーるず", ["小宮果穂"]),
        "Team.Stella": ("ちーむ すてら", ["櫻木真乃", "月岡恋鐘", "小宮果穂"]),
    }
    sites.official_units = [
        ("illuminationstars", "illumination STARS", "イルミネーションスターズ",
         ["櫻木 真乃", "風野 灯織", "八宮 めぐる"]),
        ("lantica", "L’Antica", "アンティーカ", ["月岡 恋鐘", "田中 摩美々"]),
        ("hokagoclimaxgirls", "", "放課後クライマックスガールズ", ["小宮 果穂"]),
    ]
    sites.releases = lantis_releases()
    sites.blu_rays = [("labx-8376_7", "「THE IDOLM@STER SHINY COLORS 1stLIVE FLY TO THE SHINY SKY」Blu-ray")]
    sites.fuji_discs = {disc.tax_id: disc for disc in fuji_discs()}
    sites.fuji_songs = {
        1491: ("ヒカリのdestination", []),
        3000: ("プラニスフィア ～planisphere～", [5000]),
        3001: ("MAGICAL FOREST", [5000]),
        5930: ("Shower of light", [4654]),
        5931: ("快盗Vを見逃すな", [4654]),
    }
    return sites


@pytest.fixture
def world_sync(
    admin: Admin, characters: CharacterConfig, sites: FakeWorldSites, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("eidolon.world_sync.open_client", sites.client)

    def run() -> tuple[int, str, str]:
        return admin.invoke("world", "sync", "--characters", str(characters.path))

    return run


def world_file(characters: CharacterConfig) -> Path:
    return characters.directory / "world.json"


def read_world(characters: CharacterConfig) -> dict:
    return json.loads(world_file(characters).read_text(encoding="utf-8"))


def test_the_import_writes_the_office_idols_and_units_beside_the_character_configuration(
    world_sync, characters: CharacterConfig
):
    code, _, err = world_sync()

    assert code == 0, err
    world = read_world(characters)
    assert world["as_of"] == date.today().isoformat()
    assert world["office"] == {
        "name": "283プロダクション",
        "staff": [
            {"name": "天井努", "reading": "あまいつとむ", "position": "社長",
             "sources": [SPARQL_DETAIL + "Amai_Tsutomu"]},
            {"name": "七草はづき", "reading": "ななくさはづき", "position": "事務員",
             "sources": [SPARQL_DETAIL + "Nanakusa_Hazuki"]},
        ],
    }
    assert world["units"] == [
        {"name": "illumination STARS", "reading": "いるみねーしょんすたーず",
         "members": ["櫻木真乃", "風野灯織", "八宮めぐる"],
         "sources": [OFFICIAL + "illuminationstars/", SPARQL_DETAIL + "illuminationSTARS"]},
        {"name": "L'Antica", "reading": "あんてぃーか", "members": ["月岡恋鐘", "田中摩美々"],
         "sources": [OFFICIAL + "lantica/", SPARQL_DETAIL + "L'Antica"]},
        {"name": "放課後クライマックスガールズ", "reading": "ほうかごくらいまっくすがーるず",
         "members": ["小宮果穂"],
         "sources": [OFFICIAL + "hokagoclimaxgirls/", SPARQL_DETAIL + "放課後クライマックスガールズ"]},
    ]
    assert world["idols"][0] == {
        "name": "櫻木真乃", "reading": "さくらぎまの", "unit": "illumination STARS", "cv": "関根瞳",
        "sources": [SPARQL_DETAIL + "Sakuragi_Mano", OFFICIAL + "illuminationstars/"],
    }
    assert [(i["name"], i["unit"]) for i in world["idols"]] == [
        ("櫻木真乃", "illumination STARS"), ("風野灯織", "illumination STARS"),
        ("八宮めぐる", "illumination STARS"), ("月岡恋鐘", "L'Antica"), ("田中摩美々", "L'Antica"),
        ("小宮果穂", "放課後クライマックスガールズ"),
    ]


def test_special_units_are_left_out_of_the_units_and_named_in_the_report(
    world_sync, characters: CharacterConfig
):
    code, out, _ = world_sync()

    assert code == 0
    world = read_world(characters)
    assert "Team.Stella" not in [unit["name"] for unit in world["units"]]
    assert all(idol["unit"] != "Team.Stella" for idol in world["idols"])
    assert "没有收录：Team.Stella" in out


def test_the_report_counts_each_kind_and_what_changed_since_the_last_import(
    world_sync, sites: FakeWorldSites
):
    _, first, _ = world_sync()
    sites.idols.append(dict(id="Suzuki_Hana", name="鈴木羽那", kana="すずきはな", cv="三川華月"))
    sites.sparql_units["CoMETIK"] = ("こめてぃっく", ["鈴木羽那"])
    sites.official_units.append(("cometik", "CoMETIK", "コメティック", ["鈴木 羽那"]))
    sites.idols = [i for i in sites.idols if i["name"] != "田中摩美々"]
    sites.sparql_units["L'Antica"] = ("あんてぃーか", ["月岡恋鐘"])
    sites.official_units[1] = ("lantica", "L’Antica", "アンティーカ", ["月岡 恋鐘"])

    code, second, err = world_sync()

    assert code == 0, err
    assert "偶像：6 位" in first
    assert "组合：3 个" in first
    assert "社长和事务员：2 位" in first
    assert "偶像：6 位（新增 鈴木羽那；移除 田中摩美々）" in second
    assert "组合：4 个（新增 CoMETIK；成员有变化 L'Antica）" in second
    assert "社长和事务员：2 位（没有变化）" in second


def test_where_im_sparql_and_the_official_unit_pages_disagree_is_reported(
    world_sync, sites: FakeWorldSites, characters: CharacterConfig
):
    sites.official_units[0] = (
        "illuminationstars", "illumination STARS", "イルミネーションスターズ",
        ["櫻木 真乃", "風野 灯織"],
    )

    code, out, _ = world_sync()

    assert code == 0
    assert "对不上" in out
    assert "illumination STARS" in out and "八宮めぐる" in out
    world = read_world(characters)
    assert world["units"][0]["members"] == ["櫻木真乃", "風野灯織"]  # the official page decides
    meguru = next(i for i in world["idols"] if i["name"] == "八宮めぐる")
    assert meguru["unit"] is None


@pytest.mark.parametrize(
    "host", [FakeWorldSites.SPARQL, FakeWorldSites.OFFICIAL, FakeWorldSites.LANTIS, FakeWorldSites.FUJI]
)
def test_when_a_source_fails_the_import_fails_and_the_old_file_is_kept(
    world_sync, sites: FakeWorldSites, characters: CharacterConfig, host: str
):
    world_sync()
    before = world_file(characters).read_text(encoding="utf-8")
    sites.idols.append(dict(id="Suzuki_Hana", name="鈴木羽那", kana="すずきはな", cv="三川華月"))
    sites.down.add(host)

    code, _, err = world_sync()

    assert code != 0
    assert host in err
    assert world_file(characters).read_text(encoding="utf-8") == before
    assert list(characters.directory.glob("world.json*")) == [world_file(characters)]


def test_a_unit_page_missing_from_the_official_site_fails_the_import(
    world_sync, sites: FakeWorldSites, characters: CharacterConfig
):
    sites.official_units.append(("gone", "Gone", "ゴーン", ["櫻木 真乃"]))
    sites.missing.add("idol/gone")

    code, _, err = world_sync()

    assert code != 0
    assert "idol/gone" in err
    assert not world_file(characters).exists()


def test_a_unit_im_sparql_names_differently_is_matched_by_its_members(
    world_sync, sites: FakeWorldSites, characters: CharacterConfig
):
    sites.sparql_units["ホウカゴ"] = sites.sparql_units.pop("放課後クライマックスガールズ")

    code, out, _ = world_sync()

    assert code == 0
    assert read_world(characters)["units"][2]["reading"] == "ほうかごくらいまっくすがーるず"
    assert "im@sparql 里叫 ホウカゴ" in out
    assert "没有收录：Team.Stella\n" in out  # not taken for a special unit


def songs_by_title(characters: CharacterConfig) -> dict[str, dict]:
    return {song["title"]: song for song in read_world(characters)["songs"]}


def release(characters: CharacterConfig, catalog: str) -> dict:
    return next(r for r in read_world(characters)["releases"] if r["catalog"] == catalog)


def test_releases_come_from_lantis_s_cds_with_their_tracks_in_order(
    world_sync, characters: CharacterConfig
):
    code, _, err = world_sync()

    assert code == 0, err
    world = read_world(characters)
    assert [r["catalog"] for r in world["releases"]] == [
        "LACM-14782", "LACA-15861", "LACM-24634", "LACA-25301",  # by release date
    ]
    assert release(characters, "LACM-14782") == {
        "catalog": "LACM-14782",
        "title": "THE IDOLM@STER SHINY COLORS BRILLI@NT WING 02 ヒカリのdestination",
        "date": "2018-07-04",
        "tracks": [
            {"title": "ヒカリのdestination", "song": "ヒカリのdestination"},
            {"title": "虹になれ", "song": "虹になれ"},
            {"title": "Spread the Wings!!（イルミネーションスターズ Ver.）",
             "song": "Spread the Wings!!（イルミネーションスターズ Ver.）"},
            {"title": "スペシャルオーディオドラマ「輝く笑顔に向かって」", "song": None},
        ],
        "sources": [LANTIS + "lacm-14782/"],
    }
    assert "Blu-ray" not in world_file(characters).read_text(encoding="utf-8")


def test_track_lines_are_parsed_into_their_singers(world_sync, characters: CharacterConfig):
    world_sync()

    songs = songs_by_title(characters)
    assert songs["MAGICAL FOREST"]["singers"] == ["櫻木真乃"]  # 「曲名 / 角色 (CV.声优)」
    assert songs["恋するクオリア"]["singers"] == ["月岡恋鐘"]
    assert songs["ありったけの輝きで"]["singers"] == ["櫻木真乃"]  # a 歌： line
    assert songs["アポイント・シグナル"]["singers"] == ["月岡恋鐘"]
    illumination = ["櫻木真乃", "風野灯織", "八宮めぐる"]
    assert songs["ヒカリのdestination"]["singers"] == illumination  # the unit the CD is by
    assert songs["Spread the Wings!!（イルミネーションスターズ Ver.）"]["singers"] == illumination
    assert songs["MAGICAL FOREST"] == {
        "id": "MAGICAL FOREST", "title": "MAGICAL FOREST", "singers": ["櫻木真乃"],
        "special_unit": None, "releases": ["LACA-25301"], "sources": [LANTIS + "laca-25301/"],
    }
    assert "ありったけの輝きで（Off Vocal）" not in songs


def test_a_singers_line_the_page_breaks_in_two_is_read_whole(
    world_sync, sites: FakeWorldSites, characters: CharacterConfig
):
    sites.releases[1].index += [
        "5．ふたりの歌\n歌：櫻木真乃 (CV.関根 瞳)、月岡恋鐘 (CV.礒部\n花凜)\n作詞：誰か",
        "6．さんにんの歌\n歌：櫻木真乃 (CV.関根 瞳)、月岡恋鐘 (CV.礒部花凜)、\n小宮果穂 (CV.河野ひより)",
    ]

    code, _, err = world_sync()

    assert code == 0, err
    songs = songs_by_title(characters)
    assert songs["ふたりの歌"]["singers"] == ["櫻木真乃", "月岡恋鐘"]
    assert songs["さんにんの歌"]["singers"] == ["櫻木真乃", "月岡恋鐘", "小宮果穂"]


def test_tracks_numbered_m1_m2_are_read_and_credit_lines_are_no_tracks(
    world_sync, sites: FakeWorldSites, characters: CharacterConfig
):
    sites.releases.append(LantisRelease(
        "lacm-24828", "283 Production MUSIC COLLECTION", "2026/4/22", "LACM-24828", "L'Antica",
        ["M1. One Live One Love", "M2. One Live One Love (Mortal Remix)\nリミックス：坪井リヒト"],
        artist_members="月岡恋鐘（CV.礒部花凜）、田中摩美々（CV.菅沼千紗）",
    ))

    code, _, err = world_sync()

    assert code == 0, err
    assert [t["title"] for t in release(characters, "LACM-24828")["tracks"]] == [
        "One Live One Love", "One Live One Love (Mortal Remix)",
    ]
    assert songs_by_title(characters)["One Live One Love"]["singers"] == ["月岡恋鐘", "田中摩美々"]


def test_idols_the_cd_is_by_sing_its_one_song_together_beside_their_own_versions(
    world_sync, sites: FakeWorldSites, characters: CharacterConfig
):
    sites.releases.append(LantisRelease(
        "lacm-24531", "THE IDOLM@STER SHINY COLORS シャイニーPRオファー Vol.1", "2024/4/17", "LACM-24531",
        "櫻木真乃(CV.関根 瞳)、月岡恋鐘(CV.礒部花凜)",
        ["1．輝きにかわる", "2．輝きにかわる (櫻木真乃 Ver.)", "3．輝きにかわる (月岡恋鐘Ver.)",
         "4．輝きにかわる (Off Vocal)"],
    ))

    code, _, err = world_sync()

    assert code == 0, err
    songs = songs_by_title(characters)
    assert songs["輝きにかわる"]["singers"] == ["櫻木真乃", "月岡恋鐘"]
    assert songs["輝きにかわる (櫻木真乃 Ver.)"]["singers"] == ["櫻木真乃"]
    assert songs["輝きにかわる (月岡恋鐘Ver.)"]["singers"] == ["月岡恋鐘"]


def test_a_special_unit_s_song_is_split_into_its_idols_and_keeps_the_special_unit_s_name(
    world_sync, characters: CharacterConfig
):
    world_sync()

    song = songs_by_title(characters)["プラニスフィア ～planisphere～"]
    assert song["singers"] == ["櫻木真乃", "月岡恋鐘", "小宮果穂"]
    assert song["special_unit"] == "Team.Stella"
    assert "Team.Stella" not in [u["name"] for u in read_world(characters)["units"]]


def test_a_release_not_out_yet_is_imported_all_the_same(
    world_sync, sites: FakeWorldSites, characters: CharacterConfig
):
    coming = date.today() + timedelta(days=60)
    sites.releases[2].date = f"{coming.year}/{coming.month}/{coming.day}"

    code, _, err = world_sync()

    assert code == 0, err
    assert release(characters, "LACA-25301")["date"] == coming.isoformat()
    assert songs_by_title(characters)["MAGICAL FOREST"]["releases"] == ["LACA-25301"]


def test_a_singer_who_is_none_of_the_idols_is_reported_and_the_song_not_written(
    world_sync, sites: FakeWorldSites, characters: CharacterConfig
):
    sites.releases.append(LantisRelease(
        "lacm-24027", "THE IDOLM@STER シリーズ15周年記念曲「なんどでも笑おう」【シャイニーカラーズ盤】",
        "2020/9/30", "LACM-24027", "THE IDOLM@STER FIVE STARS!!!!!",
        [
            "1．なんどでも笑おう\n歌：THE IDOLM@STER FIVE STARS!!!!!",
            "2．はづきさんの歌 / 七草はづき (CV.誰か)",
            "3．ふたりの歌 / 櫻木真乃 (CV.関根 瞳)、天海春香 (CV.中村繪里子)",
        ],
    ))

    code, out, err = world_sync()

    assert code == 0, err
    songs = songs_by_title(characters)
    assert not {"なんどでも笑おう", "はづきさんの歌", "ふたりの歌"} & set(songs)
    assert [t["song"] for t in release(characters, "LACM-24027")["tracks"]] == [None, None, None]
    assert "THE IDOLM@STER FIVE STARS!!!!!" in out
    assert "七草はづき" in out
    assert "天海春香" in out


def test_fujiwarahaji_fills_in_the_singers_lantis_leaves_out(
    world_sync, characters: CharacterConfig
):
    code, out, err = world_sync()

    assert code == 0, err
    songs = songs_by_title(characters)
    assert songs["Shower of light"]["singers"] == ["櫻木真乃", "風野灯織", "八宮めぐる"]
    assert songs["Shower of light"]["sources"] == [LANTIS + "lacm-24634/", "https://fujiwarahaji.me/disc/4654"]
    assert songs["快盗Vを見逃すな"]["singers"] == ["小宮果穂"]
    ninth = songs["プラニスフィア ～planisphere～ -9 colors-"]  # ふじわらはじめ names it as first released
    assert ninth["singers"] == ["櫻木真乃", "月岡恋鐘", "小宮果穂", "八宮めぐる"]
    assert ninth["special_unit"] == "Team.Stella"
    assert "ふじわらはじめ" in out and "Shower of light" in out
    assert "Shower of light (Game Size)" not in songs


def test_where_lantis_and_fujiwarahaji_disagree_lantis_wins_and_it_is_reported(
    world_sync, sites: FakeWorldSites, characters: CharacterConfig
):
    sites.releases[3].index[0] = "1．Shower of light\n歌：イルミネーションスターズ"
    disc = sites.fuji_discs[4654]
    disc.tracks[0] = ("Shower of light", [("放課後クライマックスガールズ", ["小宮果穂"])], [], ["orig"])

    code, out, err = world_sync()

    assert code == 0, err
    assert songs_by_title(characters)["Shower of light"]["singers"] == ["櫻木真乃", "風野灯織", "八宮めぐる"]
    assert songs_by_title(characters)["快盗Vを見逃すな"]["singers"] == ["小宮果穂"]
    assert "冲突" in out
    conflict = next(line for line in out.splitlines() if "Shower of light" in line and "小宮果穂" in line)
    assert "櫻木真乃" in conflict


def test_a_disc_fujiwarahaji_answers_empty_for_is_noted_and_its_tracks_left_unknown(
    world_sync, sites: FakeWorldSites, characters: CharacterConfig
):
    sites.empty.add("v4/tax?id=4654")

    code, out, err = world_sync()

    assert code == 0, err
    assert "Shower of light" not in songs_by_title(characters)
    assert "https://api.fujiwarahaji.me/v4/tax?id=4654" in out
    assert any("LACM-24634" in line and "Shower of light" in line for line in out.splitlines())


def test_songs_come_without_lyrics_or_credits_and_every_entry_has_its_source(
    world_sync, characters: CharacterConfig
):
    world_sync()

    text = world_file(characters).read_text(encoding="utf-8")
    assert "作詞" not in text and "作曲" not in text and "中村彼方" not in text
    world = read_world(characters)
    assert world["songs"] and world["releases"]
    assert all(song["sources"] for song in world["songs"])
    assert all(r["sources"] for r in world["releases"])
    assert all(
        set(song) == {"id", "title", "singers", "special_unit", "releases", "sources"}
        for song in world["songs"]
    )


def test_the_report_counts_releases_and_songs_and_what_changed(
    world_sync, sites: FakeWorldSites
):
    _, first, _ = world_sync()
    sites.releases.pop(0)

    code, second, err = world_sync()

    assert code == 0, err
    assert "唱片：4 张（第一次导入）" in first
    assert "唱片：3 张（移除 LACM-14782）" in second
    assert "歌曲：" in second and "移除 ヒカリのdestination" in second


def test_a_release_page_missing_from_lantis_fails_the_import(
    world_sync, sites: FakeWorldSites, characters: CharacterConfig
):
    sites.missing.add("releaseinfo/laca-15861")

    code, _, err = world_sync()

    assert code != 0
    assert "laca-15861" in err
    assert not world_file(characters).exists()


def test_two_dates_on_one_lantis_page_are_reported_and_the_release_date_line_kept(
    world_sync, sites: FakeWorldSites, characters: CharacterConfig
):
    sites.releases[0].banner_date = "2018.07.14"

    code, out, err = world_sync()

    assert code == 0, err
    assert release(characters, "LACM-14782")["date"] == "2018-07-04"
    assert "LACM-14782" in out and "2018.07.14" in out


SIX = "、".join([
    "櫻木真乃（CV.関根 瞳）", "風野灯織（CV.近藤玲奈）", "八宮めぐる（CV.峯田茉優）",
    "月岡恋鐘（CV.礒部花凜）", "田中摩美々（CV.菅沼千紗）", "小宮果穂（CV.河野ひより）",
])
EVERYONE = ["櫻木真乃", "風野灯織", "八宮めぐる", "月岡恋鐘", "田中摩美々", "小宮果穂"]
L_ANTICA = ["月岡恋鐘", "田中摩美々"]


def section(out: str, heading: str) -> str:
    """The lines of the report's section that opens with `heading`."""
    lines = out.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(heading))
    end = next((i for i in range(start + 1, len(lines)) if not lines[i].startswith("  ")), len(lines))
    return "\n".join(lines[start:end])


def test_the_whole_cast_lantis_names_with_a_head_count_is_no_special_unit(
    world_sync, sites: FakeWorldSites, characters: CharacterConfig
):
    sites.releases.append(LantisRelease(
        "laca-25133", "THE IDOLM@STER SHINY COLORS みんなのCD", "2024/5/1", "LACA-25133", "シャイニーカラーズ",
        [f"1．みんなの歌\n歌：シャイニーカラーズ(6人)\n{SIX}"],
    ))

    code, _, err = world_sync()

    assert code == 0, err
    song = songs_by_title(characters)["みんなの歌"]
    assert song["singers"] == EVERYONE
    assert song["special_unit"] is None


def test_the_whole_cast_or_one_unit_fujiwarahaji_fills_in_is_no_special_unit(
    world_sync, sites: FakeWorldSites, characters: CharacterConfig
):
    title = "THE IDOLM@STER SHINY COLORS WING COLLECTION -A side-"
    sites.releases.append(LantisRelease(
        "laca-9946_7", title, "2023/1/18", "LACA-9946～7", "シャイニーカラーズ",
        [
            "1．Spread the Wings!! -6 colors-", "2．NEO THEORY FANTASY（2023 Ver.）",
            "3．みんなの歌 / シャイニーカラーズ",
        ],
    ))
    sites.fuji_discs[6000] = FujiDisc(6000, title, [
        ("Spread the Wings!!", [("シャイニーカラーズ(6人・新)", EVERYONE)], [], ["orig"]),
        ("NEO THEORY FANTASY", [("アンティーカ", L_ANTICA)], [], []),
        ("みんなの歌", [("シャイニーカラーズ(6人)", EVERYONE)], [], []),
    ])
    sites.fuji_songs[6001] = ("Spread the Wings!!", [6000])
    sites.fuji_songs[6002] = ("NEO THEORY FANTASY", [6000])
    sites.fuji_songs[6003] = ("みんなの歌", [6000])

    code, _, err = world_sync()

    assert code == 0, err
    songs = songs_by_title(characters)
    assert songs["Spread the Wings!! -6 colors-"]["singers"] == EVERYONE
    assert songs["Spread the Wings!! -6 colors-"]["special_unit"] is None
    assert songs["NEO THEORY FANTASY（2023 Ver.）"]["singers"] == L_ANTICA
    assert songs["NEO THEORY FANTASY（2023 Ver.）"]["special_unit"] is None
    assert songs["みんなの歌"]["singers"] == EVERYONE  # Lantis names the whole cast alone
    assert songs["みんなの歌"]["special_unit"] is None


def test_singers_lantis_names_who_are_none_of_the_idols_are_not_filled_in_by_fujiwarahaji(
    world_sync, sites: FakeWorldSites, characters: CharacterConfig
):
    title = "THE IDOLM@STER SHINY COLORS ないしょのCD"
    sites.releases.append(LantisRelease(
        "lacm-24999", title, "2024/6/1", "LACM-24999", "THE IDOLM@STER FIVE STARS!!!!!",
        [
            "1．はづきさんの歌 / 七草はづき (CV.誰か)",
            "2．なんどでも笑おう\n歌：THE IDOLM@STER FIVE STARS!!!!!",
        ],
    ))
    sites.fuji_discs[6100] = FujiDisc(6100, title, [
        ("はづきさんの歌", [], ["櫻木真乃"], ["orig"]),
        ("なんどでも笑おう", [("シャイニーカラーズ", ["櫻木真乃", "月岡恋鐘"])], [], ["orig"]),
    ])
    sites.fuji_songs[6101] = ("はづきさんの歌", [6100])
    sites.fuji_songs[6102] = ("なんどでも笑おう", [6100])

    code, out, err = world_sync()

    assert code == 0, err
    assert not {"はづきさんの歌", "なんどでも笑おう"} & set(songs_by_title(characters))
    unmatched = section(out, "演唱者对应不到偶像名单的曲目")
    assert "はづきさんの歌" in unmatched and "七草はづき" in unmatched
    assert "なんどでも笑おう" in unmatched and "THE IDOLM@STER FIVE STARS!!!!!" in unmatched
    filled = section(out, "Lantis 没写演唱者")
    assert "はづきさんの歌" not in filled and "なんどでも笑おう" not in filled


def test_a_fujiwarahaji_disc_without_a_name_is_no_release_of_lantis_s(
    world_sync, sites: FakeWorldSites, characters: CharacterConfig
):
    sites.releases.append(LantisRelease(
        "lacm-24998", "THE IDOLM@STER SHINY COLORS ふしぎなCD", "2024/7/1", "LACM-24998",
        "櫻木真乃（CV.関根 瞳）、月岡恋鐘（CV.礒部花凜）",
        ["1．ふしぎな歌", "2．ほかの歌"],
    ))
    sites.fuji_discs[6200] = FujiDisc(6200, "", [("ふしぎな歌", [], ["小宮果穂"], ["orig"])])
    sites.fuji_songs[6201] = ("ふしぎな歌", [6200])

    code, out, err = world_sync()

    assert code == 0, err
    assert "ふしぎな歌" not in songs_by_title(characters)
    assert "ふしぎな歌" in section(out, "哪个来源都没写演唱者的曲目")


def test_a_later_version_where_lantis_and_fujiwarahaji_disagree_is_reported(
    world_sync, sites: FakeWorldSites, characters: CharacterConfig
):
    sites.releases[2].index.append("4. ヒカリのdestination -5 colors- / 櫻木真乃 (CV.関根 瞳)")
    sites.fuji_discs[5000].tracks.append(("ヒカリのdestination", [], ["小宮果穂"], []))

    code, out, err = world_sync()

    assert code == 0, err
    assert songs_by_title(characters)["ヒカリのdestination -5 colors-"]["singers"] == ["櫻木真乃"]
    conflicts = section(out, "Lantis 和ふじわらはじめ冲突的地方")
    assert "ヒカリのdestination -5 colors-" in conflicts and "小宮果穂" in conflicts


def test_singers_told_by_another_release_s_track_keep_that_release_as_a_source(
    world_sync, sites: FakeWorldSites, characters: CharacterConfig
):
    sites.releases += [
        LantisRelease(
            "lacm-24100", "THE IDOLM@STER SHINY COLORS ふたりのCD", "2019/1/1", "LACM-24100",
            "櫻木真乃（CV.関根 瞳）、月岡恋鐘（CV.礒部花凜）",
            ["1．ふたりの約束", "2．べつの歌 / 月岡恋鐘 (CV.礒部花凜)"],
        ),
        LantisRelease(
            "lacm-24200", "THE IDOLM@STER SHINY COLORS ふたりのCD 2", "2020/1/1", "LACM-24200",
            "櫻木真乃（CV.関根 瞳）、月岡恋鐘（CV.礒部花凜）",
            ["1．ふたりの約束 / 櫻木真乃 (CV.関根 瞳)、月岡恋鐘 (CV.礒部花凜)"],
        ),
    ]

    code, _, err = world_sync()

    assert code == 0, err
    song = songs_by_title(characters)["ふたりの約束"]
    assert song["singers"] == ["櫻木真乃", "月岡恋鐘"]
    assert song["releases"] == ["LACM-24100", "LACM-24200"]
    assert set(song["sources"]) == {LANTIS + "lacm-24100/", LANTIS + "lacm-24200/"}
