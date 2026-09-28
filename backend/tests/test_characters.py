"""Characters come from configuration: the list, the avatars, the image colours and call
backgrounds, and each one's character sheet."""

import logging
from pathlib import Path

import pytest

from eidolon.characters import CharacterConfigError, Fact, load_characters, parse_facts
from tests.conftest import AVATAR, BACKGROUND, KOGANE_SHEET, MANO_SHEET, CharacterConfig, ClientFactory
from tests.fakes import FakeLLM
from tests.test_text_turn import send_turn, start_conversation

REPO_CHARACTERS = Path(__file__).parents[2] / "characters"


async def test_character_list_shows_name_intro_avatar_colour_and_background_but_not_the_sheet(
    make_client: ClientFactory,
):
    client = make_client(FakeLLM())

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
        },
        {
            "id": "kogane",
            "name": "月岡恋鐘",
            "intro": "L'Antica 的偶像",
            "avatar_url": None,
            "color": "#f84cad",
            "background_url": None,
        },
    ]
    assert "ほわっ" not in res.text


async def test_character_list_is_shown_before_signing_in(make_client: ClientFactory):
    client = make_client(FakeLLM(), user=None)

    res = await client.get("/api/characters")

    assert res.status_code == 200
    assert [c["name"] for c in res.json()] == ["櫻木真乃", "月岡恋鐘"]


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


def test_voice_id_is_read_from_the_configuration(characters: CharacterConfig):
    characters.add("hiori", "風野灯織", "sheet", voice_id="my-private-voice")

    assert load_characters(characters.path)["hiori"].voice_id == "my-private-voice"


def test_repository_configures_mano_and_kogane_with_their_voices():
    loaded = load_characters(REPO_CHARACTERS / "characters.toml")

    assert {id: c.voice_id for id, c in loaded.items()} == {
        "mano": "a1150f3d14ac46fb8ea59c7803cd8357",
        "kogane": "a11bfd046e924099a84f989fb4049e95",
    }
    assert loaded["mano"].name == "櫻木真乃"
    assert loaded["kogane"].name == "月岡恋鐘"
    assert {id: c.speakers for id, c in loaded.items()} == {"mano": ("真乃",), "kogane": ("恋鐘",)}
    assert all(c.sheet and c.facts and c.avatar for c in loaded.values())  # committed (ADR-0003)
    assert {id: c.color for id, c in loaded.items()} == {"mano": "#ffbad6", "kogane": "#f84cad"}


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


def test_character_without_an_image_colour_is_rejected_by_name(tmp_path: Path):
    config = CharacterConfig(tmp_path).add("mano", "櫻木真乃", "a", color=None)

    with pytest.raises(CharacterConfigError, match="角色 mano 缺少字段 color"):
        load_characters(config.path)


@pytest.mark.parametrize("color", ["ffbad6", "#fff", "#ffbad", "#ffbad6ff", "#ggbad6", "pink", ""])
def test_image_colour_must_be_a_hex_rrggbb(tmp_path: Path, color: str):
    config = CharacterConfig(tmp_path).add("mano", "櫻木真乃", "a", color=color)

    with pytest.raises(CharacterConfigError, match="角色 mano 的 color.*#rrggbb"):
        load_characters(config.path)


def test_image_colour_is_read_in_lower_case(tmp_path: Path):
    config = CharacterConfig(tmp_path).add("mano", "櫻木真乃", "a", color="#FFBAD6")

    assert load_characters(config.path)["mano"].color == "#ffbad6"


def test_call_background_is_found_relative_to_the_configuration(tmp_path: Path):
    config = CharacterConfig(tmp_path).add("mano", "櫻木真乃", "a", background=BACKGROUND)

    background = load_characters(config.path)["mano"].background

    assert background is not None
    assert background.read_bytes() == BACKGROUND


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
