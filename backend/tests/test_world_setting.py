"""The world setting in every turn: what the chat model reads after the character sheet,
taken from the data file beside the character configuration, and the backend refusing to
start when a character is none of its idols."""

import json
import logging
from datetime import UTC, datetime

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


RELEASES = [
    ("LACM-14782", "THE IDOLM@STER SHINY COLORS BRILLI@NT WING 02 ヒカリのdestination", "2018-07-04",
     ["ヒカリのdestination", "Spread the Wings!!（イルミネーションスターズ Ver.）", None]),
    ("LACA-15861", "THE IDOLM@STER SHINY COLORS COLORFUL FE@THERS -Stella-", "2021-01-20",
     ["プラニスフィア ～planisphere～", "ありったけの輝きで", "アポイント・シグナル"]),
    ("LACA-9946～7", "THE IDOLM@STER SHINY COLORS WING COLLECTION -A side-", "2023-01-18",
     ["ヒカリのdestination", "スローモーション"]),
    ("LACA-35264～5", "283 Production MUSICAL Performance 騎士団のヴェール Music Collection【初回限定盤】",
     "2026-03-11", ["愚者の独白"]),
    ("LACA-25301", "THE IDOLM@STER SHINY COLORS HOPEFUL FE@THERS -Stella-", "2026-10-21",
     ["MAGICAL FOREST"]),
    ("LACM-14861", "THE IDOLM@STER SHINY COLORS FR@GMENT WING 01", "2019-04-10", ["Ambitious Eve"]),
]
"""Releases for `write_world`: catalog number, title, release date, and the songs on it
(None for a track that is no song, like a drama)."""

SONGS = [
    ("ヒカリのdestination", ["櫻木真乃", "風野灯織"], None),
    ("Spread the Wings!!（イルミネーションスターズ Ver.）", ["櫻木真乃", "風野灯織"], None),
    ("プラニスフィア ～planisphere～", ["櫻木真乃", "月岡恋鐘"], "Team.Stella"),
    ("ありったけの輝きで", ["櫻木真乃"], None),
    ("アポイント・シグナル", ["月岡恋鐘"], None),
    ("スローモーション", ["風野灯織"], None),
    ("愚者の独白", ["櫻木真乃", "風野灯織", "月岡恋鐘"], None),
    ("MAGICAL FOREST", ["櫻木真乃"], None),
    ("Ambitious Eve", ["櫻木真乃", "風野灯織", "月岡恋鐘"], None),
]
"""Songs for `write_world`: title, singers and the special unit that sang it, if one did.
Mano's are her own two solos, her unit's two songs and nothing else."""


def write_world(characters: CharacterConfig, idols: list[tuple[str, str, str]] | None = None) -> None:
    """A data file as `eidolon world sync` writes it: Mano's and Kogane's units, the
    office's president and clerk, and the songs and releases above."""
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
        "releases": [
            {"catalog": catalog, "title": title, "date": day,
             "tracks": [{"title": song or "スペシャルオーディオドラマ", "song": song} for song in songs],
             "sources": source}
            for catalog, title, day, songs in RELEASES
        ],
        "songs": [
            {"id": title, "title": title, "singers": singers, "special_unit": special,
             "releases": [catalog for catalog, _, _, songs in RELEASES if title in songs],
             "sources": source}
            for title, singers, special in SONGS
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


def her_songs(system: str) -> str:
    """The part of the system prompt that lists her songs."""
    start = system.index("# 你的歌")
    end = system.find("\n# ", start + 1)
    return system[start:] if end == -1 else system[start:end]


async def test_every_turn_carries_her_songs_with_their_releases(
    turns: Turns, characters: CharacterConfig
):
    write_world(characters)
    llm = FakeLLM(REPLY)

    await turns.take(llm, "真乃のソロ曲って何があったっけ")

    system = system_prompt(llm)
    assert system.index("# 世界设定") < system.index("# 你的歌") < system.index("# 制作人")
    songs = her_songs(system)
    assert "- ありったけの輝きで：" in songs  # sung by her alone
    assert "- ヒカリのdestination：" in songs  # sung by her whole unit
    assert "- Spread the Wings!!（イルミネーションスターズ Ver.）：" in songs
    line = next(line for line in songs.splitlines() if line.startswith("- ヒカリのdestination："))
    assert "《THE IDOLM@STER SHINY COLORS BRILLI@NT WING 02 ヒカリのdestination》（2018年7月4日发售）" in line
    assert "《THE IDOLM@STER SHINY COLORS WING COLLECTION -A side-》（2023年1月18日发售）" in line


async def test_her_songs_leave_out_anyone_elses(turns: Turns, characters: CharacterConfig):
    write_world(characters)
    llm = FakeLLM(REPLY)

    await turns.take(llm, "どんな歌を歌ってきたの？")

    songs = her_songs(system_prompt(llm))
    assert "アポイント・シグナル" not in songs  # another idol's solo
    assert "スローモーション" not in songs  # her unit mate's solo
    assert "プラニスフィア" not in songs  # a special unit's, with her in it
    assert "愚者の独白" not in songs  # her unit with someone from outside it
    assert "Ambitious Eve" not in songs  # everyone's


def song_line(system: str, title: str) -> str:
    return next(line for line in her_songs(system).splitlines() if line.startswith(f"- {title}"))


async def test_a_release_still_to_come_is_told_as_one(turns: Turns, characters: CharacterConfig):
    write_world(characters)  # the turn is on 2026-09-26; the release is on 2026-10-21
    llm = FakeLLM(REPLY)

    await turns.take(llm, "新しいCD、いつ出るんだっけ")

    line = song_line(system_prompt(llm), "MAGICAL FOREST")
    assert "（将于2026年10月21日发售）" in line
    assert "还没有发售" not in line
    past = song_line(system_prompt(llm), "ヒカリのdestination")
    assert "（2018年7月4日发售）" in past and "将于" not in past


async def test_whether_a_release_is_out_goes_by_the_day_of_each_turn(
    turns: Turns, settings: Settings, characters: CharacterConfig
):
    write_world(characters)  # the data runs to 2026-09-28; the release is on 2026-10-21
    now = [datetime(2026, 10, 20, 12, 0, tzinfo=UTC)]
    llm = FakeLLM(REPLY, REPLY)
    backend = build(settings, chat_llm=llm, clock=lambda: now[0])
    try:
        llms = backend.own_keys.for_turn(turns.conversation.user_id).llms
        async for _ in backend.engine.turn(turns.conversation, "新しいCD、いつ出るんだっけ", llms):
            pass
        now[0] = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)  # the same backend, two days on
        async for _ in backend.engine.turn(turns.conversation, "新しいCD、もう出た？", llms):
            pass
    finally:
        await backend.aclose()

    before, after = (prompt[0].content for prompt in llm.prompts)
    assert "（将于2026年10月21日发售）" in song_line(before, "MAGICAL FOREST")
    assert "（2026年10月21日发售）" in song_line(after, "MAGICAL FOREST")


async def test_a_special_unit_s_song_is_not_hers_even_if_its_idols_are_her_unit(
    turns: Turns, characters: CharacterConfig
):
    write_world(characters)
    path = characters.directory / "world.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["songs"].append({
        "id": "とくべつな歌", "title": "とくべつな歌", "singers": ["櫻木真乃", "風野灯織"],
        "special_unit": "Team.Hikari", "releases": ["LACM-14782"],
        "sources": ["https://example.invalid/source"],
    })
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    llm = FakeLLM(REPLY)

    await turns.take(llm, "どんな歌を歌ってきたの？")

    songs = her_songs(system_prompt(llm))
    assert "特别组合或者全体一起唱的歌不在这里" in songs
    assert "とくべつな歌" not in songs


async def test_a_song_whose_releases_are_all_missing_is_listed_by_its_title_alone(
    turns: Turns, characters: CharacterConfig
):
    write_world(characters)
    path = characters.directory / "world.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["songs"].append({
        "id": "まぼろしの歌", "title": "まぼろしの歌", "singers": ["櫻木真乃"], "special_unit": None,
        "releases": ["NONE-0000"], "sources": ["https://example.invalid/source"],
    })
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    llm = FakeLLM(REPLY)

    await turns.take(llm, "どんな歌を歌ってきたの？")

    assert song_line(system_prompt(llm), "まぼろしの歌") == "- まぼろしの歌"


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
