"""The recall-story tool, driven through the text turn API: the model calls it with a
general question, the engine looks the episode up through the story catalog, and the
model answers from what comes back."""

from pathlib import Path

import pytest

from eidolon.characters import load_characters
from eidolon.config import Settings
from eidolon.corpus import StoryCorpus
from eidolon.engine import MAX_TOOL_ROUNDS
from eidolon.llm import ChatMessage, ToolCall
from eidolon.story_import import import_csv_directory
from tests.conftest import ClientFactory
from tests.fakes import FakeEmbedder, FakeJudge, FakeLLM, FakeReranker
from tests.test_text_turn import send_turn, start_conversation

PARK_LINE = "公園で鳩と一緒に歌っていました"
ANSWER = ["<ja>公園でピーちゃんたちと歌ってたんです</ja><zh>我在公园和小皮它们唱歌</zh>"]


def recall(query: str, id: str = "call_1") -> ToolCall:
    return ToolCall(id, "recall_story", {"query": query})


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


def tool_results(prompt: list[ChatMessage]) -> list[str]:
    return [m.content for m in prompt if m.role == "tool"]


async def test_the_reply_is_based_on_the_recalled_episode_and_its_place_in_the_catalog(
    make_client: ClientFactory, embedder: FakeEmbedder
):
    llm = FakeLLM([recall("公園で鳩と歌った日")], ANSWER)
    # Jev sees no need to retrieve; the model asks for the episode itself.
    client = make_client(
        llm, jev=FakeJudge(answer="nothing"), embedder=embedder, reranker=FakeReranker(PARK_LINE)
    )
    conversation_id = await start_conversation(client)

    events = await send_turn(client, conversation_id, "那次在公园唱歌是怎么回事？")

    assert [t.name for t in llm.tools[0]] == ["recall_story"]
    first, second = llm.prompts
    assert second[: len(first)] == first
    call, result = second[len(first) :]
    assert (call.role, call.tool_calls) == ("assistant", (recall("公園で鳩と歌った日"),))
    assert (result.role, result.tool_call_id) == ("tool", "call_1")
    # Where the episode sits in her catalog, the other episodes there, and what happened.
    assert "培育剧情 / W.I.N.G.編 /「公園の歌声」" in result.content
    assert "「決勝後コミュ」" in result.content
    assert f"真乃：{PARK_LINE}" in result.content
    assert "歌が好きなのか？" not in result.content  # the producer's choices never were

    assert events[-1]["type"] == "done"
    assert events[-1]["message"]["ja"] == "公園でピーちゃんたちと歌ってたんです"
    messages = (await client.get(f"/api/conversations/{conversation_id}/messages")).json()
    assert [(m["role"], m["text"], m["ja"]) for m in messages] == [
        ("user", "那次在公园唱歌是怎么回事？", None),
        ("character", None, "公園でピーちゃんたちと歌ってたんです"),
    ]


async def test_a_character_only_recalls_episodes_she_is_cast_in(
    make_client: ClientFactory, embedder: FakeEmbedder
):
    llm, reranker = FakeLLM([recall("公園の鳩")], ANSWER), FakeReranker(PARK_LINE, others=0.01)
    client = make_client(llm, jev=FakeJudge(answer="nothing"), embedder=embedder, reranker=reranker)
    conversation_id = await start_conversation(client, "kogane")

    await send_turn(client, conversation_id, "那次在公园和鸽子唱歌是怎么回事？")

    # Mano's park episode is never a candidate for Kogane, and nothing of hers is about it.
    assert not any(PARK_LINE in doc for _, docs in reranker.calls for doc in docs)
    [result] = tool_results(llm.prompts[-1])
    assert PARK_LINE not in result
    assert "没有想起" in result


async def test_the_tool_is_not_offered_without_retrieval(make_client: ClientFactory):
    llm = FakeLLM(ANSWER)
    client = make_client(llm)
    conversation_id = await start_conversation(client)

    await send_turn(client, conversation_id, "那次在公园唱歌是怎么回事？")

    assert llm.tools == [[]]


async def test_what_she_says_before_calling_the_tool_is_part_of_the_reply(
    make_client: ClientFactory, embedder: FakeEmbedder
):
    llm = FakeLLM(["<ja>えっと……</ja><zh>嗯……</zh>", recall("公園")], ANSWER)
    client = make_client(
        llm, jev=FakeJudge(answer="nothing"), embedder=embedder, reranker=FakeReranker(PARK_LINE)
    )
    conversation_id = await start_conversation(client)

    events = await send_turn(client, conversation_id, "公园那次呢？")

    assert llm.prompts[1][-2].content == "<ja>えっと……</ja><zh>嗯……</zh>"
    assert events[-1]["message"]["segments"] == [
        {"ja": "えっと……", "zh": "嗯……"},
        {"ja": "公園でピーちゃんたちと歌ってたんです", "zh": "我在公园和小皮它们唱歌"},
    ]


async def test_tool_calls_stop_after_a_few_rounds(
    make_client: ClientFactory, embedder: FakeEmbedder
):
    llm = FakeLLM(*[[recall("公園", f"call_{i}")] for i in range(MAX_TOOL_ROUNDS)], ANSWER)
    client = make_client(
        llm, jev=FakeJudge(answer="nothing"), embedder=embedder, reranker=FakeReranker(PARK_LINE)
    )
    conversation_id = await start_conversation(client)

    events = await send_turn(client, conversation_id, "公园那次呢？")

    # The last round offers no tools, so the model has to answer.
    assert [len(tools) for tools in llm.tools] == [1] * MAX_TOOL_ROUNDS + [0]
    assert events[-1]["type"] == "done"


async def test_a_call_made_when_no_tool_was_offered_goes_unanswered(
    make_client: ClientFactory, embedder: FakeEmbedder
):
    rounds = [[recall("公園", f"call_{i}")] for i in range(MAX_TOOL_ROUNDS)]
    llm = FakeLLM(*rounds, [*ANSWER, recall("公園", "call_last")])
    client = make_client(
        llm, jev=FakeJudge(answer="nothing"), embedder=embedder, reranker=FakeReranker(PARK_LINE)
    )
    conversation_id = await start_conversation(client)

    events = await send_turn(client, conversation_id, "公园那次呢？")

    assert len(llm.prompts) == MAX_TOOL_ROUNDS + 1
    assert events[-1]["message"]["ja"] == "公園でピーちゃんたちと歌ってたんです"


async def test_a_failed_or_malformed_call_is_answered_and_the_turn_goes_on(
    make_client: ClientFactory, embedder: FakeEmbedder
):
    llm = FakeLLM(
        [
            ToolCall("call_1", "recall_story", None),
            ToolCall("call_2", "take_selfie", {}),
            recall("公園", "call_3"),
        ],
        ANSWER,
    )
    client = make_client(
        llm, jev=FakeJudge(answer="nothing"), embedder=embedder, reranker=FakeReranker(PARK_LINE)
    )
    conversation_id = await start_conversation(client)
    embedder.down = True

    events = await send_turn(client, conversation_id, "公园那次呢？")

    malformed, unknown, failed = tool_results(llm.prompts[-1])
    assert "query" in malformed
    assert "take_selfie" in unknown
    assert "暂时想不起来" in failed
    assert events[-1]["type"] == "done"


async def test_when_jev_sees_a_recall_question_the_episode_is_recalled_before_the_model_answers(
    make_client: ClientFactory, embedder: FakeEmbedder
):
    llm, reranker = FakeLLM(ANSWER), FakeReranker(PARK_LINE)
    client = make_client(llm, jev=FakeJudge(answer="recall"), embedder=embedder, reranker=reranker)
    conversation_id = await start_conversation(client)

    events = await send_turn(client, conversation_id, "那次在公园唱歌是怎么回事？")

    # One model call: the episode is already in the prompt, and the tool is not offered again.
    [prompt] = llm.prompts
    assert llm.tools == [[]]
    system = prompt[0].content
    assert "# 回顾剧情：那次在公园唱歌是怎么回事？" in system
    assert "培育剧情 / W.I.N.G.編 /「公園の歌声」" in system
    assert f"真乃：{PARK_LINE}" in system
    # Recalling takes the place of the turn's general retrieval.
    assert "# 回忆与资料" not in system
    assert [query for query, _ in reranker.calls] == ["那次在公园唱歌是怎么回事？"]
    assert events[-1]["type"] == "done"


async def test_a_recall_question_about_someone_elses_episode_recalls_nothing(
    make_client: ClientFactory, embedder: FakeEmbedder
):
    llm = FakeLLM(ANSWER)
    client = make_client(
        llm, jev=FakeJudge(answer="recall"), embedder=embedder,
        reranker=FakeReranker(PARK_LINE, others=0.01),
    )
    conversation_id = await start_conversation(client, "kogane")

    await send_turn(client, conversation_id, "那次你在公园和鸽子一起唱歌是怎么回事？")

    system = llm.prompts[0][0].content
    assert PARK_LINE not in system
    assert "没有想起" in system
