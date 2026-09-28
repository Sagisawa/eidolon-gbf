"""The world setting in every turn: what the chat model reads after the character sheet,
taken from the data file beside the character configuration, and the backend refusing to
start when a character is none of its idols."""

import json
import logging

import pytest

from eidolon.assembly import build
from eidolon.config import Settings
from eidolon.characters import load_characters
from eidolon.world import WorldError, load_world, world_path
from tests.conftest import CharacterConfig
from tests.fakes import FakeBackgroundLLM, FakeLLM
from tests.test_characters import REPO_CHARACTERS
from tests.test_turns import REPLY, Turns, turns  # noqa: F401  (the fixture)

CVS = ["関根瞳", "礒部花凜", "近藤玲奈", "津田健次郎"]


def write_world(characters: CharacterConfig, idols: list[tuple[str, str, str]] | None = None) -> None:
    """A data file as `eidolon world sync` writes it: Mano's and Kogane's units, and
    the office's president and clerk."""
    idols = idols or [
        ("櫻木真乃", "illumination STARS", "関根瞳"),
        ("風野灯織", "illumination STARS", "近藤玲奈"),
        ("月岡恋鐘", "L'Antica", "礒部花凜"),
    ]
    source = ["https://example.invalid/source"]
    characters.write("world.json", json.dumps({
        "as_of": "2026-09-28",
        "office": {"name": "283プロダクション", "staff": [
            {"name": "天井努", "reading": "あまいつとむ", "position": "社長", "sources": source},
            {"name": "七草はづき", "reading": "ななくさはづき", "position": "事務員", "sources": source},
        ]},
        "units": [
            {"name": "illumination STARS", "reading": "いるみねーしょんすたーず",
             "members": ["櫻木真乃", "風野灯織"], "sources": source},
            {"name": "L'Antica", "reading": "あんてぃーか", "members": ["月岡恋鐘"], "sources": source},
        ],
        "idols": [
            {"name": name, "reading": "", "unit": unit, "cv": cv, "sources": source}
            for name, unit, cv in idols
        ],
    }, ensure_ascii=False))


def system_prompt(llm: FakeLLM) -> str:
    [prompt] = llm.prompts
    return prompt[0].content


async def test_every_turn_carries_the_world_setting_after_the_character_sheet(
    turns: Turns, characters: CharacterConfig
):
    write_world(characters)
    llm = FakeLLM(REPLY)

    await turns.take(llm, "イルミネのメンバーって誰だっけ")

    system = system_prompt(llm)
    assert system.index("你是櫻木真乃") < system.index("# 世界设定") < system.index("# 制作人")
    assert "资料截止到 2026年9月28日" in system
    assert "社長：天井努" in system and "事務員：七草はづき" in system
    assert "illumination STARS（いるみねーしょんすたーず）：櫻木真乃、風野灯織" in system
    assert "L'Antica（あんてぃーか）：月岡恋鐘" in system  # her unit or not, every unit


async def test_the_world_setting_carries_the_rules_for_facts_of_the_original(
    turns: Turns, characters: CharacterConfig
):
    write_world(characters)
    llm = FakeLLM(REPLY)

    await turns.take(llm, "新曲の歌詞、ちょっと歌ってみて")

    system = system_prompt(llm)
    assert "查不到的，就老实说一时想不起来" in system
    assert "既不说「没有这回事」，也不顺着对方的说法附和" in system
    assert "不引用歌词，也不编造歌词" in system
    assert "不编造台上发生了什么" in system
    assert "不谈论声优" in system
    assert "不谈论具体的周边商品" in system
    assert "2026年9月28日以后的事" in system and "一概不知道" in system


async def test_no_cv_is_named_in_any_prompt(turns: Turns, characters: CharacterConfig):
    write_world(characters)
    llm, memory = FakeLLM(REPLY, REPLY), FakeBackgroundLLM()

    await turns.take(llm, "真乃の声優って誰？", background_llm=memory)
    await turns.take(llm, "中の人は？", background_llm=memory)

    prompts = [m.content for prompt in [*llm.prompts, *memory.prompts] for m in prompt]
    assert prompts
    assert not [cv for cv in CVS for text in prompts if cv in text]


async def test_without_the_data_file_turns_go_on_without_the_world_setting(
    turns: Turns, settings: Settings, caplog: pytest.LogCaptureFixture
):
    llm = FakeLLM(REPLY)

    with caplog.at_level(logging.INFO):
        events = await turns.take(llm, "早上好")

    assert events[-1]["type"] == "done"
    assert "# 世界设定" not in system_prompt(llm)
    assert "world.json" in caplog.text and "world sync" in caplog.text


def test_a_character_who_is_none_of_the_idols_stops_the_backend_from_starting(
    settings: Settings, characters: CharacterConfig
):
    write_world(characters, idols=[("櫻木真乃", "illumination STARS", "関根瞳")])

    with pytest.raises(WorldError, match="kogane.*月岡恋鐘"):
        build(settings, chat_llm=FakeLLM())


def test_every_character_in_the_repository_is_one_of_the_idols_in_its_world_setting():
    path = world_path(REPO_CHARACTERS / "characters.toml")
    world = load_world(path)

    assert world is not None
    world.check_characters(load_characters(REPO_CHARACTERS / "characters.toml"), path)
    assert len(world.units) == 8
