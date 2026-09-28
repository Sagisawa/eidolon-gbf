"""Importing the world setting (`eidolon world sync`): idols, units, the office's president
and clerk from im@sparql and the official unit pages, driven through the command against
fake sites and checked in the data file it writes and the report it prints."""

import json
from datetime import date
from pathlib import Path

import pytest

from tests.conftest import Admin, CharacterConfig
from tests.fakes import FakeWorldSites

SPARQL_DETAIL = "https://sparql.crssnky.xyz/imasrdf/RDFs/detail/"
OFFICIAL = "https://shinycolors.idolmaster-official.jp/idol/"

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
    assert "Team.Stella" not in world_file(characters).read_text(encoding="utf-8")
    assert "Team.Stella" in out


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


@pytest.mark.parametrize("host", [FakeWorldSites.SPARQL, FakeWorldSites.OFFICIAL])
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
