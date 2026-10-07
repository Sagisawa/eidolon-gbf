"""`eidolon eval judge`: the judge eval set's turns and segments are asked of the judge
model as a conversation would ask them, and what it answers is summed up against what was
expected: the confusion of what turns need, how sure it is of each question's yes and no,
the long-context cases apart, how right its emotions and nods are, and how long it took."""

import json
from pathlib import Path
from typing import Any

import pytest

from eidolon.judge import JudgeError, JudgeReply, JudgeThresholds
from eidolon.judge_eval import (
    JudgeEvalError,
    evaluate,
    load_judge_eval,
    report,
    summarize,
)
from tests.test_retrieval_services import MANO

HALF = JudgeThresholds(needs_retrieval=0.5, recall=0.5, about_producer=0.5, emotion=0.5)

EVAL = """
[[retrieval]]
id = "hello"
character = "mano"
history = []
said = "おはよう"
expected = "nothing"

[[retrieval]]
id = "cat"
character = "mano"
history = [{ user = "ただいま" }, { character = "[happily]おかえりなさい！" }]
said = "うちの猫が風邪をひいてさ"
expected = "memories"

[[retrieval]]
id = "song"
character = "mano"
history = []
said = "イルミネの新曲って誰が歌ってる？"
expected = "references"

[[retrieval]]
id = "wing"
character = "mano"
history = []
said = "W.I.N.G.の決勝、どうだった？"
expected = "recall"

[[retrieval]]
id = "long-wing"
character = "mano"
history = [{ user = "長い話" }]
said = "W.I.N.G.の決勝、どうだった？"
expected = "recall"
long = true

[[emotion]]
id = "thanks"
character = "mano"
user_said = "可愛いね"
before = [{ ja = "[shyly]ほわっ……", zh = "哇……" }]
ja = "ありがとうございます……"
zh = "谢谢……"
emotion = "shy"
nod = "none"

[[emotion]]
id = "yes"
character = "mano"
user_said = "明日レッスンね"
ja = "はい、がんばります"
zh = "好的，我会加油"
emotion = "calm"
nod = "yes"
"""


def noul(retrieve: float, recall: float, about: float) -> dict:
    return {
        "needs_retrieval": {"type": "noul", "noul": retrieve},
        "recall": {"type": "noul", "noul": recall},
        "about_producer": {"type": "noul", "noul": about},
    }


def choice(emotions: dict[str, float], nods: dict[str, float]) -> dict:
    return {
        "emotion": {"type": "choice", "probabilities": emotions},
        "nod": {"type": "choice", "probabilities": nods},
    }


ANSWERS: dict[str, dict] = {
    "おはよう": noul(0.1, 0.05, 0.2),  # nothing, right
    "うちの猫が風邪をひいてさ": noul(0.6, 0.1, 0.9),  # references, but memories expected
    "イルミネの新曲って誰が歌ってる？": noul(0.9, 0.2, 0.1),  # references, right
    "W.I.N.G.の決勝、どうだった？": noul(0.95, 0.8, 0.1),  # recall, right
    "ありがとうございます……": choice({"害羞": 0.7, "开心": 0.3}, {"都不是": 0.9, "同意": 0.1}),
    "はい、がんばります": choice({"开心": 0.6, "平静": 0.4}, {"同意": 0.4, "都不是": 0.35}),
}


class FakeJudgeModel:
    """Answers by what was just said or the segment; fails the long case."""

    def __init__(self) -> None:
        self.states: list[dict[str, Any]] = []

    async def reply(self, state: dict[str, Any], questions: dict[str, dict]) -> JudgeReply:
        self.states.append(state)
        if state.get("上文") == ["制作人：長い話"]:
            raise JudgeError("Workers AI 返回 500")
        said = state.get("制作人最新的一句话") or state["这一段台词"]
        return JudgeReply(ANSWERS[said], input_tokens=100 + len(self.states))

    async def ask(self, state: dict[str, Any], questions: dict[str, dict]) -> dict[str, Any]:
        return (await self.reply(state, questions)).answers

    async def aclose(self) -> None:
        pass


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "judge.toml"
    path.write_text(text, encoding="utf-8")
    return path


async def run(tmp_path: Path) -> tuple[FakeJudgeModel, dict]:
    judge_eval = load_judge_eval(write(tmp_path, EVAL), {"mano": MANO})
    model = FakeJudgeModel()
    ticks = iter(range(100))
    results = await evaluate(judge_eval, {"mano": MANO}, model, HALF, clock=lambda: next(ticks))
    return model, summarize(results, "clef-flash", HALF)


async def test_turns_and_segments_are_asked_as_a_conversation_asks_them(tmp_path: Path):
    model, _ = await run(tmp_path)

    cat = model.states[1]
    assert cat == {
        "角色": "櫻木真乃",
        "上文": ["制作人：ただいま", "櫻木真乃：おかえりなさい！"],  # without the cue
        "制作人最新的一句话": "うちの猫が風邪をひいてさ",
    }
    thanks = model.states[5]
    assert thanks["这条回复前面几段"] == ["[shyly]ほわっ……（哇……）"]
    assert model.states[6]["这条回复前面几段"] == "（这是回复的第一段）"


async def test_what_turns_need_is_set_against_what_was_expected(tmp_path: Path):
    _, summary = await run(tmp_path)

    turns = summary["retrieval"]["all"]
    assert turns["cases"] == 5 and turns["failed"] == 1
    assert turns["accuracy"] == pytest.approx(3 / 4)
    assert turns["confusion"]["memories"] == {"references": 1}
    assert turns["confusion"]["recall"] == {"recall": 1}
    assert turns["confusion"]["nothing"] == {"nothing": 1}


async def test_each_questions_probabilities_are_spread_by_the_answer_expected(tmp_path: Path):
    _, summary = await run(tmp_path)

    spread = summary["retrieval"]["all"]["probabilities"]
    # Retrieval is needed for references and recall, not for nothing or memories.
    assert spread["needs_retrieval"]["yes"] == {"n": 2, "min": 0.9, "median": 0.925, "max": 0.95}
    assert spread["needs_retrieval"]["no"] == {"n": 2, "min": 0.1, "median": 0.35, "max": 0.6}
    assert spread["recall"]["yes"]["n"] == 1 and spread["recall"]["no"]["n"] == 3
    # Whether it is about the producer matters only against nothing.
    assert spread["about_producer"]["yes"] == {"n": 1, "min": 0.9, "median": 0.9, "max": 0.9}
    assert spread["about_producer"]["no"] == {"n": 1, "min": 0.2, "median": 0.2, "max": 0.2}


async def test_the_long_cases_are_counted_apart(tmp_path: Path):
    _, summary = await run(tmp_path)

    long, short = summary["retrieval"]["long"], summary["retrieval"]["short"]
    assert (long["cases"], long["failed"], long["accuracy"]) == (1, 1, None)
    assert (short["cases"], short["failed"]) == (4, 0)


async def test_emotions_and_nods_are_scored(tmp_path: Path):
    _, summary = await run(tmp_path)

    segments = summary["emotion"]
    assert segments["cases"] == 2 and segments["failed"] == 0
    assert segments["emotion_accuracy"] == 0.5  # happy at 0.6, where calm was expected
    assert segments["nod_accuracy"] == 0.5  # yes at 0.4 is below 0.5, so none
    assert segments["likeliest_emotion"]["right"]["max"] == 0.7
    assert segments["likeliest_emotion"]["wrong"]["max"] == 0.6


async def test_latency_and_input_tokens_are_reported(tmp_path: Path):
    _, summary = await run(tmp_path)

    assert summary["mean_seconds"] == 1  # each request one tick of the clock
    assert summary["retrieval"]["all"]["input_tokens"]["min"] == 101


async def test_the_report_and_the_json_carry_each_case(tmp_path: Path):
    judge_eval = load_judge_eval(write(tmp_path, EVAL), {"mano": MANO})
    results = await evaluate(judge_eval, {"mano": MANO}, FakeJudgeModel(), HALF)
    summary = summarize(results, "clef-flash", HALF)

    text = report(results, summary)
    assert "cat" in text and "long-wing" in text and "500" in text
    dumped = json.loads(json.dumps(results.to_json(summary), ensure_ascii=False))
    [cat] = [c for c in dumped["retrieval"] if c["id"] == "cat"]
    assert cat["expected"] == "memories" and cat["actual"] == "references"
    assert cat["probabilities"]["about_producer"] == 0.9
    assert cat["input_tokens"] > 100
    assert dumped["summary"]["model"] == "clef-flash"


@pytest.mark.parametrize(
    "text, error",
    [
        ('[[retrieval]]\nid = "a"\ncharacter = "mano"\nsaid = "x"\nexpected = "maybe"', "expected"),
        ('[[retrieval]]\nid = "a"\ncharacter = "rin"\nsaid = "x"\nexpected = "nothing"', "rin"),
        ('[[retrieval]]\nid = "a"\ncharacter = "mano"\nsaid = "x"\nexpected = "nothing"\n'
         'history = [{ boss = "x" }]', "history"),
        ('[[emotion]]\nid = "a"\ncharacter = "mano"\nuser_said = "x"\nja = "y"\nzh = "z"\n'
         'emotion = "bored"\nnod = "none"', "emotion"),
        ('[[emotion]]\nid = "a"\ncharacter = "mano"\nuser_said = "x"\nja = "y"\nzh = "z"\n'
         'emotion = "calm"\nnod = "maybe"', "nod"),
        ('[[retrieval]]\nid = "a"\ncharacter = "mano"\nsaid = "x"\nexpected = "nothing"\n'
         '[[retrieval]]\nid = "a"\ncharacter = "mano"\nsaid = "y"\nexpected = "nothing"', "重复"),
        ("[[retrieval", "格式"),
    ],
)
def test_a_malformed_set_is_refused(tmp_path: Path, text: str, error: str):
    with pytest.raises(JudgeEvalError, match=error):
        load_judge_eval(write(tmp_path, text), {"mano": MANO})


def test_the_committed_set_loads(tmp_path: Path):
    from eidolon.characters import load_characters

    repo = Path(__file__).parents[2]
    characters = load_characters(repo / "characters" / "characters.toml")
    judge_eval = load_judge_eval(repo / "backend" / "eval" / "judge.toml", characters)

    assert judge_eval.retrieval and judge_eval.emotion
    assert any(case.long for case in judge_eval.retrieval)
