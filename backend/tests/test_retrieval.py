"""Retrieval in conversation, driven through the text turn API: Jev decides whether a
turn looks anything up; if so, the story corpus (only episodes the character is cast
in) and her character facts are searched, reranked and capped into the prompt."""

from pathlib import Path

import httpx
import pytest

from eidolon.characters import load_characters
from eidolon.config import Settings
from eidolon.corpus import StoryCorpus
from eidolon.retrieval import MAX_REFERENCES
from eidolon.story_import import import_csv_directory
from tests.conftest import KOGANE_SHEET, MANO_SHEET, CharacterConfig, ClientFactory
from tests.fakes import FakeEmbedder, FakeJudge, FakeLLM, FakeReranker
from tests.test_text_turn import send_turn, start_conversation

REPLY = ["<ja>はいっ</ja><zh>好的</zh>"]

MANO_FACTS = """\
# 档案
生日是3月4日，喜欢鸟。

# 人物关系
## 風野灯織
illumination STARS 的伙伴，性格认真。
## 八宮めぐる
illumination STARS 的伙伴，总是很有精神。

# 鸟
## ピーちゃん
常和真乃在一起的鸽子。
## 公園
真乃常去公园看鸟。
"""
KOGANE_FACTS = "# 家乡\n来自长崎，最喜欢什锦面。"

PARK_LINE = "公園で鳩と一緒に歌っていました"


@pytest.fixture
def characters(tmp_path: Path) -> CharacterConfig:
    return (
        CharacterConfig(tmp_path / "characters")
        .add("mano", "櫻木真乃", MANO_SHEET, speakers=["真乃"], facts=MANO_FACTS)
        .add("kogane", "月岡恋鐘", KOGANE_SHEET, speakers=["恋鐘"], facts=KOGANE_FACTS)
    )


@pytest.fixture
async def embedder(settings: Settings, story: Path) -> FakeEmbedder:
    """The embedder the sample stories were imported with."""
    embedder = FakeEmbedder()
    corpus = StoryCorpus(settings.database_path, embedder)
    try:
        characters = load_characters(settings.characters_path)
        await import_csv_directory(story, corpus, characters.values())
    finally:
        corpus.close()
    return embedder


async def system_prompt(
    client: httpx.AsyncClient, llm: FakeLLM, text: str, character: str = "mano"
) -> str:
    conversation_id = await start_conversation(client, character)
    events = await send_turn(client, conversation_id, text)
    assert events[-1]["type"] == "done"
    return llm.prompts[-1][0].content


def reference_count(system: str) -> int:
    return system.count("\n## 剧情\n") + system.count("\n## 角色资料\n")


async def test_small_talk_retrieves_nothing(
    make_client: ClientFactory, embedder: FakeEmbedder
):
    jev, reranker, llm = FakeJudge(answer="nothing"), FakeReranker(), FakeLLM(REPLY)
    client = make_client(llm, retrieval_judge=jev, embedder=embedder, reranker=reranker)

    system = await system_prompt(client, llm, "早上好")

    assert jev.asked == [("櫻木真乃", "早上好")]
    assert embedder.queries == []
    assert reranker.calls == []
    assert "# 回忆与资料" not in system
    assert PARK_LINE not in system


async def test_a_character_recalls_episodes_she_is_cast_in(
    make_client: ClientFactory, embedder: FakeEmbedder
):
    llm = FakeLLM(REPLY)
    client = make_client(llm, retrieval_judge=FakeJudge(), embedder=embedder, reranker=FakeReranker(PARK_LINE))

    system = await system_prompt(client, llm, "公園の鳩のこと覚えてる？")

    assert "# 回忆与资料" in system
    references = system[system.index("# 回忆与资料") :]
    assert references.index("## 剧情\nW.I.N.G.編「公園の歌声」") < references.index("## 角色资料")
    assert PARK_LINE in references


async def test_a_character_cannot_recall_episodes_she_is_not_in(
    make_client: ClientFactory, embedder: FakeEmbedder
):
    llm, reranker = FakeLLM(REPLY, REPLY), FakeReranker()
    client = make_client(llm, retrieval_judge=FakeJudge(), embedder=embedder, reranker=reranker)

    # Mano's park episode is the closest match, but Kogane is not in it.
    kogane = await system_prompt(client, llm, "公園の鳩のこと覚えてる？", "kogane")
    candidates = reranker.calls[-1][1]
    assert not any(PARK_LINE in c for c in candidates)
    assert PARK_LINE not in kogane
    assert "ちゃんぽん" in kogane  # her own card is still there

    # Hiori's event is about a photo shoot in the park; no configured character is in it.
    mano = await system_prompt(client, llm, "公園で写真を撮ったこと", "mano")
    assert "撮影、頑張ります" not in mano
    assert not any("撮影、頑張ります" in c for _, docs in reranker.calls for c in docs)


async def test_character_facts_are_retrieved_for_their_own_character(
    make_client: ClientFactory, embedder: FakeEmbedder
):
    llm = FakeLLM(REPLY)
    client = make_client(llm, retrieval_judge=FakeJudge(), embedder=embedder, reranker=FakeReranker("風野灯織"))

    system = await system_prompt(client, llm, "灯織ちゃんは元気？")

    references = system[system.index("# 回忆与资料") :]
    assert references.index("## 角色资料\n人物关系 / 風野灯織\nillumination STARS 的伙伴，性格认真。") < (
        references.index("## 剧情")
    )
    assert "来自长崎" not in system  # Kogane's facts are hers alone


async def test_references_are_reranked_then_capped(
    make_client: ClientFactory, embedder: FakeEmbedder
):
    reranker, llm = FakeReranker("ピーちゃん"), FakeLLM(REPLY)
    client = make_client(llm, retrieval_judge=FakeJudge(), embedder=embedder, reranker=reranker)

    system = await system_prompt(client, llm, "鳩の話をしよう")

    [(query, candidates)] = reranker.calls
    assert query == "鳩の話をしよう"
    # Mano's three episodes and five facts all go to the reranker...
    assert len(candidates) == 8 > MAX_REFERENCES
    # ...but only the best few reach the prompt, in the reranker's order.
    assert reference_count(system) == MAX_REFERENCES
    references = system[system.index("# 回忆与资料") :]
    assert references.index("ピーちゃん") < references.index("## 剧情")


async def test_irrelevant_references_are_left_out(
    make_client: ClientFactory, embedder: FakeEmbedder
):
    llm, reranker = FakeLLM(REPLY, REPLY), FakeReranker(PARK_LINE, others=0.01)
    client = make_client(llm, retrieval_judge=FakeJudge(), embedder=embedder, reranker=reranker)

    system = await system_prompt(client, llm, "公園の鳩のこと覚えてる？")

    # Only the park episode is relevant enough; the other candidates are not filler.
    assert reference_count(system) == 1
    assert PARK_LINE in system

    # With nothing relevant, the prompt carries no references section at all.
    reranker.prefer = "（どこにもない）"
    system = await system_prompt(client, llm, "長崎のちゃんぽん、好き？")

    assert "# 回忆与资料" not in system


async def test_edited_facts_take_effect_on_restart(
    make_client: ClientFactory, embedder: FakeEmbedder, characters: CharacterConfig
):
    characters.write("facts/mano.md", "# 鸟\n## ピーちゃん\n最近学会了说「ほわっ」。")
    llm = FakeLLM(REPLY)
    client = make_client(llm, retrieval_judge=FakeJudge(), embedder=embedder, reranker=FakeReranker())

    system = await system_prompt(client, llm, "ピーちゃんは元気？")

    assert "最近学会了说「ほわっ」。" in system
    assert "常和真乃在一起的鸽子。" not in system


async def test_retrieval_goes_ahead_when_jev_is_down(
    make_client: ClientFactory, embedder: FakeEmbedder
):
    llm = FakeLLM(REPLY)
    client = make_client(llm, retrieval_judge=FakeJudge(answer=None), embedder=embedder, reranker=FakeReranker())

    system = await system_prompt(client, llm, "公園の鳩のこと覚えてる？")

    assert PARK_LINE in system


async def test_a_turn_still_gets_a_reply_when_retrieval_fails(
    make_client: ClientFactory, embedder: FakeEmbedder
):
    embedder.down = True
    llm = FakeLLM(REPLY)
    client = make_client(llm, retrieval_judge=FakeJudge(), embedder=embedder, reranker=FakeReranker())

    system = await system_prompt(client, llm, "公園の鳩のこと覚えてる？")

    assert "# 回忆与资料" not in system
