"""Characters come from configuration: the list, the avatars, the image colours, call
backgrounds and stands, and each one's character sheet."""

import logging
from dataclasses import replace
from pathlib import Path

import pytest

from eidolon.characters import CharacterConfigError, Fact, load_characters, parse_facts
from eidolon.config import Settings, stand_assets_url_from_env
from tests.conftest import AVATAR, BACKGROUND, KOGANE_SHEET, MANO_SHEET, CharacterConfig, ClientFactory
from tests.fakes import FakeLLM
from tests.test_text_turn import send_turn, start_conversation

REPO_CHARACTERS = Path(__file__).parents[2] / "characters"


async def test_character_list_shows_name_intro_avatar_colour_and_background_but_not_the_sheet(
    make_client: ClientFactory,
):
    """It is shown before signing in."""
    client = make_client(FakeLLM(), user=None)

    res = await client.get("/api/characters")

    assert res.status_code == 200
    assert res.json() == [
        {
            "id": "mano",
            "name": "櫻木真乃",
            "intro": "illumination STARS 的中心",
            "avatar_url": "/api/characters/mano/avatar",
            "color": "#ffbad6",
            "background_url": "/api/characters/mano/background",
            "stand": None,  # no stand assets URL is configured
        },
        {
            "id": "kogane",
            "name": "月岡恋鐘",
            "intro": "L'Antica 的偶像",
            "avatar_url": None,
            "color": "#f84cad",
            "background_url": None,
            "stand": None,
        },
    ]
    assert "ほわっ" not in res.text


async def test_avatar_is_served_without_a_session_so_img_tags_can_load_it(
    make_client: ClientFactory,
):
    client = make_client(FakeLLM(), user=None)

    res = await client.get("/api/characters/mano/avatar")

    assert res.status_code == 200
    assert res.content == AVATAR
    assert (await client.get("/api/characters/kogane/avatar")).status_code == 404
    assert (await client.get("/api/characters/nobody/avatar")).status_code == 404


async def test_call_background_is_served_without_a_session_like_the_avatar(
    make_client: ClientFactory,
):
    client = make_client(FakeLLM(), user=None)

    res = await client.get("/api/characters/mano/background")

    assert res.status_code == 200
    assert res.content == BACKGROUND
    assert (await client.get("/api/characters/kogane/background")).status_code == 404
    assert (await client.get("/api/characters/nobody/background")).status_code == 404


@pytest.mark.parametrize(
    ("character", "sheet", "other_sheet"),
    [("mano", MANO_SHEET, KOGANE_SHEET), ("kogane", KOGANE_SHEET, MANO_SHEET)],
)
async def test_each_character_talks_with_her_own_character_sheet(
    make_client: ClientFactory, character: str, sheet: str, other_sheet: str
):
    llm = FakeLLM(["<ja>はい</ja><zh>好</zh>"])
    client = make_client(llm)
    conversation_id = await start_conversation(client, character)

    await send_turn(client, conversation_id, "你好")

    system = llm.prompts[0][0]
    assert sheet in system.content
    assert other_sheet not in system.content


async def test_a_character_added_to_the_configuration_can_be_talked_to(
    make_client: ClientFactory, characters: CharacterConfig
):
    characters.add("hiori", "風野灯織", "# 人设\n你是風野灯織。", intro="认真的努力家")
    llm = FakeLLM(["<ja>はい</ja><zh>好</zh>"])
    client = make_client(llm)

    listed = (await client.get("/api/characters")).json()
    conversation_id = await start_conversation(client, "hiori")
    await send_turn(client, conversation_id, "你好")

    assert [c["id"] for c in listed] == ["mano", "kogane", "hiori"]
    assert "你是風野灯織。" in llm.prompts[0][0].content


async def test_conversation_with_a_character_removed_from_the_configuration_is_gone(
    make_client: ClientFactory, characters: CharacterConfig
):
    characters.add("hiori", "風野灯織", "# 人设\n你是風野灯織。")
    conversation_id = await start_conversation(make_client(FakeLLM()), "hiori")
    CharacterConfig(characters.directory).add("mano", "櫻木真乃", MANO_SHEET)
    client = make_client(FakeLLM())

    res = await client.post(f"/api/conversations/{conversation_id}/turns", json={"text": "你好"})

    assert res.status_code == 404
    assert res.json()["detail"] == "角色不存在"


def test_repository_configures_its_idols_with_their_voices():
    loaded = load_characters(REPO_CHARACTERS / "characters.toml")

    assert {id: c.voice_id for id, c in loaded.items()} == {
        "mano": "a1150f3d14ac46fb8ea59c7803cd8357",
        "hiori": "df43849d16ae48fe87f5670b6a2b81b3",
        "meguru": "17ce7b6d4ccb43a2bedac1fdb4a219cb",
        "kogane": "a11bfd046e924099a84f989fb4049e95",
        "mamimi": "1cbb1ba24d094810a6cada880dd8dec0",
        "sakuya": "3543f8d3e498439794f14be23dafbe89",
        "yuika": "e6b09fdf01874e63adf5f8aa45c0d2ea",
        "kiriko": "115e921e1b4740b08f3ec723666b2b40",
        "toru": "",
        "madoka": "",
        "koito": "",
        "hinana": "",
    }
    assert {id: c.name for id, c in loaded.items()} == {
        "mano": "櫻木真乃",
        "hiori": "風野灯織",
        "meguru": "八宮めぐる",
        "kogane": "月岡恋鐘",
        "mamimi": "田中摩美々",
        "sakuya": "白瀬咲耶",
        "yuika": "三峰結華",
        "kiriko": "幽谷霧子",
        "toru": "浅倉透",
        "madoka": "樋口円香",
        "koito": "福丸小糸",
        "hinana": "市川雛菜",
    }
    assert {id: c.speakers for id, c in loaded.items()} == {
        "mano": ("真乃",),
        "hiori": ("灯織",),
        "meguru": ("めぐる",),
        "kogane": ("恋鐘",),
        "mamimi": ("摩美々",),
        "sakuya": ("咲耶",),
        "yuika": ("結華",),
        "kiriko": ("霧子",),
        "toru": ("透",),
        "madoka": ("円香",),
        "koito": ("小糸",),
        "hinana": ("雛菜",),
    }
    assert all(c.sheet and c.facts and c.avatar for c in loaded.values())  # committed (ADR-0003)
    assert {id: c.color for id, c in loaded.items()} == {
        "mano": "#ffbad6",
        "hiori": "#144384",
        "meguru": "#ffe012",
        "kogane": "#f84cad",
        "mamimi": "#a846fb",
        "sakuya": "#006047",
        "yuika": "#3b91c4",
        "kiriko": "#d9f2ff",
        "toru": "#50d0d0",
        "madoka": "#be1e3e",
        "koito": "#7967c3",
        "hinana": "#ffc639",
    }


def test_character_facts_are_split_by_heading(characters: CharacterConfig):
    characters.add(
        "hiori", "風野灯織", "sheet",
        facts="# 档案\n生日是2月27日。\n\n# 人物关系\n\n## 櫻木真乃\n同组合的伙伴。\n### 趣事\n一起去看鸟。\n",
    )

    assert load_characters(characters.path)["hiori"].facts == (
        Fact("档案", "档案\n生日是2月27日。"),
        Fact("人物关系 / 櫻木真乃", "人物关系 / 櫻木真乃\n同组合的伙伴。"),
        Fact("人物关系 / 櫻木真乃 / 趣事", "人物关系 / 櫻木真乃 / 趣事\n一起去看鸟。"),
    )


def test_text_before_any_heading_is_an_untitled_fact():
    assert parse_facts("生日是2月27日。\n\n# 档案\n身高155cm。") == (
        Fact(None, "生日是2月27日。"),
        Fact("档案", "档案\n身高155cm。"),
    )


def test_missing_character_sheet_is_reported_with_its_path(tmp_path: Path):
    config = CharacterConfig(tmp_path).add("mano", "櫻木真乃", sheet=None)

    with pytest.raises(CharacterConfigError, match=r"sheets[/\\]mano\.md"):
        load_characters(config.path)


def test_duplicate_character_ids_are_rejected(tmp_path: Path):
    config = CharacterConfig(tmp_path).add("mano", "櫻木真乃", "a").add("mano", "真乃", "b")

    with pytest.raises(CharacterConfigError, match="mano"):
        load_characters(config.path)


def test_character_missing_a_required_field_is_rejected(tmp_path: Path):
    config = CharacterConfig(tmp_path)
    config.write("characters.toml", '[[characters]]\nid = "mano"\nname = "櫻木真乃"\n')

    with pytest.raises(CharacterConfigError, match="intro、voice_id、sheet、color"):
        load_characters(config.path)


def test_character_id_must_be_safe_to_put_in_a_url(tmp_path: Path):
    config = CharacterConfig(tmp_path)
    config.write("characters.toml", '[[characters]]\nid = "Mano San"\nname = "a"\n'
                 'intro = ""\nvoice_id = "v"\nsheet = "s.md"\ncolor = "#ffbad6"\n')

    with pytest.raises(CharacterConfigError, match="Mano San"):
        load_characters(config.path)


def test_speakers_must_be_a_list_of_names(tmp_path: Path):
    config = CharacterConfig(tmp_path).add("mano", "櫻木真乃", "a")
    config.path.write_text(
        config.path.read_text(encoding="utf-8") + 'speakers = "真乃"\n', encoding="utf-8"
    )

    with pytest.raises(CharacterConfigError, match="speakers"):
        load_characters(config.path)


def test_two_characters_cannot_share_a_speaker_name(tmp_path: Path):
    config = (
        CharacterConfig(tmp_path)
        .add("mano", "櫻木真乃", "a", speakers=["真乃"])
        .add("mano2", "真乃", "b", speakers=["真乃"])
    )

    with pytest.raises(CharacterConfigError, match="真乃"):
        load_characters(config.path)


def test_missing_configuration_file_is_reported(tmp_path: Path):
    with pytest.raises(CharacterConfigError, match="characters.toml"):
        load_characters(tmp_path / "characters.toml")


@pytest.mark.parametrize("color", ["ffbad6", "#fff", "#ffbad", "#ffbad6ff", "#ggbad6", "pink", ""])
def test_image_colour_must_be_a_hex_rrggbb(tmp_path: Path, color: str):
    config = CharacterConfig(tmp_path).add("mano", "櫻木真乃", "a", color=color)

    with pytest.raises(CharacterConfigError, match="角色 mano 的 color.*#rrggbb"):
        load_characters(config.path)


def test_image_colour_is_read_in_lower_case(tmp_path: Path):
    config = CharacterConfig(tmp_path).add("mano", "櫻木真乃", "a", color="#FFBAD6")

    assert load_characters(config.path)["mano"].color == "#ffbad6"


def test_missing_call_background_is_a_warning_and_treated_as_none(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    config = CharacterConfig(tmp_path).add("mano", "櫻木真乃", "a")
    config.path.write_text(
        config.path.read_text(encoding="utf-8") + 'background = "backgrounds/mano.jpg"\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING, logger="eidolon.characters"):
        mano = load_characters(config.path)["mano"]

    assert mano.background is None
    assert "backgrounds" in caplog.text and "mano" in caplog.text


STAND_ASSETS = "https://stand.example/eidolon"


async def test_character_with_an_idol_and_a_default_outfit_has_a_stand_and_her_outfit_list_once_assets_are_served(
    make_client: ClientFactory, settings: Settings
):
    client = make_client(FakeLLM(), settings=replace(settings, stand_assets_url=STAND_ASSETS), user=None)

    listed = {c["id"]: c for c in (await client.get("/api/characters")).json()}

    assert listed["mano"]["stand"] == {
        "default_outfit": {
            "id": "stand/1030010010",
            "url": f"{STAND_ASSETS}/spine/idols/stand/1030010010/",
        },
        "outfits_url": f"{STAND_ASSETS}/outfits/1.json",
    }
    assert listed["kogane"]["stand"] is None  # no idol, no default outfit


@pytest.mark.parametrize(
    ("idol_id", "default_outfit"), [(1, None), (None, "stand_costume/1030010010")]
)
async def test_character_missing_her_idol_or_her_default_outfit_has_no_stand(
    make_client: ClientFactory,
    settings: Settings,
    characters: CharacterConfig,
    idol_id: int | None,
    default_outfit: str | None,
):
    characters.add("hiori", "風野灯織", "sheet", idol_id=idol_id, default_outfit=default_outfit)
    client = make_client(FakeLLM(), settings=replace(settings, stand_assets_url=STAND_ASSETS))

    listed = {c["id"]: c for c in (await client.get("/api/characters")).json()}

    assert listed["hiori"]["stand"] is None


def add_raw(config: CharacterConfig, line: str) -> None:
    config.path.write_text(config.path.read_text(encoding="utf-8") + line + "\n", encoding="utf-8")


@pytest.mark.parametrize("value", ['"1"', "0", "1.5", "true"])
def test_idol_id_must_be_a_positive_whole_number(tmp_path: Path, value: str):
    config = CharacterConfig(tmp_path).add("mano", "櫻木真乃", "a")
    add_raw(config, f"idol_id = {value}")

    with pytest.raises(CharacterConfigError, match="角色 mano 的 idol_id"):
        load_characters(config.path)


@pytest.mark.parametrize(
    "value",
    [
        '"1030010010"',
        '"cb/1030010010"',
        '"stand/103001001"',
        '"stand/1030010010/"',
        '"spine/idols/stand/1030010010"',
        "1030010010",
    ],
)
def test_default_outfit_must_name_a_stand_outfit(tmp_path: Path, value: str):
    config = CharacterConfig(tmp_path).add("mano", "櫻木真乃", "a")
    add_raw(config, f"default_outfit = {value}")

    with pytest.raises(CharacterConfigError, match="角色 mano 的 default_outfit.*stand/<enzaId>"):
        load_characters(config.path)


def test_repository_gives_its_idols_their_idol_ids_and_default_outfits():
    loaded = load_characters(REPO_CHARACTERS / "characters.toml")

    assert {id: (c.idol_id, c.default_outfit) for id, c in loaded.items()} == {
        "mano": (1, "stand/1030010010"),
        "hiori": (2, "stand/1030020010"),
        "meguru": (3, "stand/1030030010"),
        "kogane": (4, "stand/1030040010"),
        "mamimi": (5, "stand/1030050010"),
        "sakuya": (6, "stand/1030060010"),
        "yuika": (7, "stand/1030070010"),
        "kiriko": (8, "stand/1030080010"),
        "toru": (20, "stand/1030200010"),
        "madoka": (21, "stand/1030210010"),
        "koito": (22, "stand/1030220010"),
        "hinana": (23, "stand/1030230010"),
    }


def test_stand_assets_url_is_read_without_its_trailing_slash(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("EIDOLON_STAND_ASSETS_URL", raising=False)
    assert stand_assets_url_from_env() is None

    monkeypatch.setenv("EIDOLON_STAND_ASSETS_URL", " https://stand.example/eidolon/ ")
    assert stand_assets_url_from_env() == "https://stand.example/eidolon"

    monkeypatch.setenv("EIDOLON_STAND_ASSETS_URL", "http://localhost:8765")
    assert stand_assets_url_from_env() == "http://localhost:8765"


@pytest.mark.parametrize("value", ["stand.example/eidolon", "/stand", "ftp://stand.example"])
def test_stand_assets_url_must_be_a_web_address(monkeypatch: pytest.MonkeyPatch, value: str):
    monkeypatch.setenv("EIDOLON_STAND_ASSETS_URL", value)

    with pytest.raises(RuntimeError, match="EIDOLON_STAND_ASSETS_URL"):
        stand_assets_url_from_env()
