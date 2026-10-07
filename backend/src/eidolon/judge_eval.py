"""Evaluating the judge model (`eidolon eval judge`) against a small labelled set of turns
and segments committed with the code (`eval/judge.toml`), to set its thresholds, choose
the default model, and see whether a long state is cut short.

Each turn is asked as a conversation asks it (`ModelRetrievalJudge`: the character, the
latest messages before, and what the user just said), and what it needs is decided by the
model's thresholds; each segment of a reply is asked as a call asks it
(`ModelEmotionJudge`). The summary sets what turns needed against what was expected, and
spreads each question's probability by whether its answer was expected to be yes or no,
to see where a threshold would fall. The long-context cases, whose history pushes the
state past what Workers AI is said to read, are summed up apart. A request that fails is
counted and the run goes on.

The set holds made-up turns and replies about the real characters, songs and story, never
story text, so it can be committed (ADR-0003).
"""

import statistics
import time
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, TypeVar, get_args

from eidolon.characters import Character
from eidolon.emotion import (
    Emotion,
    EmotionAnswer,
    ModelEmotionJudge,
    Nod,
    SaidSegment,
    SegmentToJudge,
    decide,
)
from eidolon.judge import JudgeError, JudgeReply, JudgeThresholds
from eidolon.retrieval import ModelRetrievalJudge, Need, RetrievalAnswer
from eidolon.store import Message

Question = Literal["needs_retrieval", "recall", "about_producer"]
T = TypeVar("T")

_EXPECTED_YES: dict[Question, tuple[set[Need], set[Need]]] = {
    "needs_retrieval": ({"references", "recall"}, {"nothing", "memories"}),
    "recall": ({"recall"}, {"nothing", "memories", "references"}),
    # A turn that looks references up finds memories too, so whether it is about the
    # user's life matters only against a turn that needs nothing.
    "about_producer": ({"memories"}, {"nothing"}),
}
"""For each question, the needs for which its answer should be yes, and those for which
it should be no."""

_NODS: dict[str, Nod | None] = {"yes": "yes", "no": "no", "none": None}


class JudgeEvalError(RuntimeError):
    pass


@dataclass(frozen=True)
class RetrievalCase:
    """A turn, and what it should need looked up."""

    id: str
    character: str
    history: tuple[Message, ...]
    said: str
    expected: Need
    long: bool = False
    """Its history pushes the state past roughly 2K tokens."""


@dataclass(frozen=True)
class EmotionCase:
    """A segment of a reply, and the emotion and nod it should show."""

    id: str
    character: str
    user_said: str
    before: tuple[SaidSegment, ...]
    segment: SaidSegment
    emotion: Emotion
    nod: Nod | None


@dataclass(frozen=True)
class JudgeEval:
    retrieval: tuple[RetrievalCase, ...]
    emotion: tuple[EmotionCase, ...]


def load_judge_eval(path: Path, characters: Mapping[str, Character]) -> JudgeEval:
    """The set at `path`, its characters checked against `characters`."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise JudgeEvalError(f"找不到判断模型的 eval 集 {path}") from None
    except tomllib.TOMLDecodeError as e:
        raise JudgeEvalError(f"判断模型的 eval 集 {path} 格式有误：{e}") from None
    ids: set[str] = set()

    def case_id(entry: dict, table: str) -> str:
        id_ = _text(entry, "id", table)
        if id_ in ids:
            raise JudgeEvalError(f"用例 {id_} 重复")
        ids.add(id_)
        character = _text(entry, "character", id_)
        if character not in characters:
            raise JudgeEvalError(f"用例 {id_} 的角色 {character} 不在角色配置里")
        return id_

    retrieval = []
    for entry in data.get("retrieval", []):
        id_ = case_id(entry, "retrieval")
        expected = entry.get("expected")
        if expected not in get_args(Need):
            raise JudgeEvalError(
                f"用例 {id_} 的 expected 只能是 {'、'.join(get_args(Need))}，而不是 {expected}"
            )
        retrieval.append(RetrievalCase(
            id_, entry["character"], _history(entry.get("history", []), id_),
            _text(entry, "said", id_), expected, entry.get("long", False) is True,
        ))
    emotion = []
    for entry in data.get("emotion", []):
        id_ = case_id(entry, "emotion")
        feeling = entry.get("emotion")
        if feeling not in get_args(Emotion):
            raise JudgeEvalError(
                f"用例 {id_} 的 emotion 只能是 {'、'.join(get_args(Emotion))}，而不是 {feeling}"
            )
        nod = entry.get("nod")
        if nod not in _NODS:
            raise JudgeEvalError(f"用例 {id_} 的 nod 只能是 yes、no、none，而不是 {nod}")
        emotion.append(EmotionCase(
            id_, entry["character"], _text(entry, "user_said", id_),
            tuple(_said(s, id_) for s in _list(entry, "before", id_)),
            SaidSegment(_text(entry, "ja", id_), _text(entry, "zh", id_)),
            feeling, _NODS[nod],
        ))
    return JudgeEval(tuple(retrieval), tuple(emotion))


def _text(entry: dict, field: str, where: str) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value:
        raise JudgeEvalError(f"用例 {where} 缺少 {field}")
    return value


def _list(entry: dict, field: str, case_id: str) -> list:
    value = entry.get(field, [])
    if not isinstance(value, list):
        raise JudgeEvalError(f"用例 {case_id} 的 {field} 应为列表")
    return value


def _history(entries: Any, case_id: str) -> tuple[Message, ...]:
    if not isinstance(entries, list):
        raise JudgeEvalError(f"用例 {case_id} 的 history 应为列表")
    messages = []
    for i, entry in enumerate(entries):
        if isinstance(entry, dict) and entry.keys() == {"user"}:
            messages.append(Message(i, "user", entry["user"], None, None, ""))
        elif isinstance(entry, dict) and entry.keys() == {"character"}:
            messages.append(Message(i, "character", None, entry["character"], "", ""))
        else:
            raise JudgeEvalError(
                f"用例 {case_id} 的 history 每一条应为 {{ user = \"…\" }} 或 {{ character = \"…\" }}"
            )
    return tuple(messages)


def _said(entry: Any, case_id: str) -> SaidSegment:
    if not isinstance(entry, dict):
        raise JudgeEvalError(f"用例 {case_id} 的 before 每一条应为 {{ ja = \"…\", zh = \"…\" }}")
    return SaidSegment(_text(entry, "ja", case_id), _text(entry, "zh", case_id))


class MeteredJudgeModel(Protocol):
    async def reply(self, state: dict[str, Any], questions: dict[str, dict]) -> JudgeReply: ...


class _Metered:
    """A judge model's `ask`, keeping the input tokens of the latest answer."""

    def __init__(self, model: MeteredJudgeModel) -> None:
        self._model = model
        self.input_tokens: int | None = None

    async def ask(self, state: dict[str, Any], questions: dict[str, dict]) -> dict[str, Any]:
        self.input_tokens = None
        reply = await self._model.reply(state, questions)
        self.input_tokens = reply.input_tokens
        return reply.answers

    async def aclose(self) -> None:
        pass


@dataclass(frozen=True)
class RetrievalResult:
    case: RetrievalCase
    answer: RetrievalAnswer | None
    """None if the request failed."""
    actual: Need | None
    input_tokens: int | None
    seconds: float
    error: str | None = None


@dataclass(frozen=True)
class EmotionResult:
    case: EmotionCase
    answer: EmotionAnswer | None
    """None if the request failed."""
    emotion: Emotion | None
    nod: Nod | None
    input_tokens: int | None
    seconds: float
    error: str | None = None


@dataclass(frozen=True)
class JudgeEvalResults:
    retrieval: list[RetrievalResult]
    emotion: list[EmotionResult]

    def to_json(self, summary: dict) -> dict:
        """Every case's answer and the summary, for comparing models side by side."""
        return {
            "summary": summary,
            "retrieval": [
                {
                    "id": r.case.id,
                    "long": r.case.long,
                    "expected": r.case.expected,
                    "actual": r.actual,
                    "probabilities": None if r.answer is None else {
                        "needs_retrieval": r.answer.needs_retrieval,
                        "recall": r.answer.recall,
                        "about_producer": r.answer.about_producer,
                    },
                    "input_tokens": r.input_tokens,
                    "seconds": r.seconds,
                    "error": r.error,
                }
                for r in self.retrieval
            ],
            "emotion": [
                {
                    "id": r.case.id,
                    "expected": {"emotion": r.case.emotion, "nod": _nod_name(r.case.nod)},
                    "actual": None if r.answer is None else {
                        "emotion": r.emotion, "nod": _nod_name(r.nod)
                    },
                    "probabilities": None if r.answer is None else {
                        "emotion": dict(r.answer.emotions),
                        "nod": {_nod_name(n): p for n, p in r.answer.nods.items()},
                    },
                    "input_tokens": r.input_tokens,
                    "seconds": r.seconds,
                    "error": r.error,
                }
                for r in self.emotion
            ],
        }


async def evaluate(
    judge_eval: JudgeEval,
    characters: Mapping[str, Character],
    judge_model: MeteredJudgeModel,
    thresholds: JudgeThresholds,
    clock: Callable[[], float] = time.perf_counter,
) -> JudgeEvalResults:
    """Ask `judge_model` about every case, one at a time, deciding by `thresholds`."""
    metered = _Metered(judge_model)
    retrieval_judge = ModelRetrievalJudge(metered, thresholds)
    emotion_judge = ModelEmotionJudge(metered)
    retrieval = []
    for case in judge_eval.retrieval:
        start = clock()
        try:
            answer = await retrieval_judge.ask(characters[case.character], case.history, case.said)
        except JudgeError as e:
            retrieval.append(RetrievalResult(case, None, None, None, clock() - start, str(e)))
            continue
        retrieval.append(RetrievalResult(
            case, answer, retrieval_judge.decide(answer), metered.input_tokens, clock() - start
        ))
    emotion = []
    for case in judge_eval.emotion:
        segment = SegmentToJudge(
            characters[case.character], case.user_said, case.before, case.segment
        )
        start = clock()
        try:
            answer = await emotion_judge.judge_emotion(segment)
        except JudgeError as e:
            emotion.append(EmotionResult(case, None, None, None, None, clock() - start, str(e)))
            continue
        feeling, nod = decide(answer, thresholds.emotion)
        emotion.append(EmotionResult(
            case, answer, feeling, nod, metered.input_tokens, clock() - start
        ))
    return JudgeEvalResults(retrieval, emotion)


def summarize(results: JudgeEvalResults, model: str, thresholds: JudgeThresholds) -> dict:
    """The figures to compare models by, as JSON."""
    timed = [r.seconds for r in [*results.retrieval, *results.emotion]]
    return {
        "model": model,
        "thresholds": {
            "needs_retrieval": thresholds.needs_retrieval,
            "recall": thresholds.recall,
            "about_producer": thresholds.about_producer,
            "emotion": thresholds.emotion,
        },
        "retrieval": {
            "all": _retrieval_summary(results.retrieval),
            "short": _retrieval_summary([r for r in results.retrieval if not r.case.long]),
            "long": _retrieval_summary([r for r in results.retrieval if r.case.long]),
        },
        "emotion": _emotion_summary(results.emotion),
        "mean_seconds": statistics.fmean(timed) if timed else None,
    }


def _retrieval_summary(results: Sequence[RetrievalResult]) -> dict:
    answered = [r for r in results if r.answer is not None]
    confusion: dict[str, dict[str, int]] = {need: {} for need in get_args(Need)}
    for r in answered:
        row = confusion[r.case.expected]
        row[str(r.actual)] = row.get(str(r.actual), 0) + 1
    probabilities = {}
    for question, (yes, no) in _EXPECTED_YES.items():
        def spread(needs: set[Need], question: Question = question) -> dict:
            return _distribution(
                [getattr(r.answer, question) for r in answered if r.case.expected in needs]
            )
        probabilities[question] = {"yes": spread(yes), "no": spread(no)}
    return {
        "cases": len(results),
        "failed": len(results) - len(answered),
        "accuracy": _share(answered, lambda r: r.actual == r.case.expected),
        "confusion": confusion,
        "probabilities": probabilities,
        "input_tokens": _distribution(
            [r.input_tokens for r in answered if r.input_tokens is not None]
        ),
    }


def _emotion_summary(results: Sequence[EmotionResult]) -> dict:
    answered = [r for r in results if r.answer is not None]

    def likeliest(r: EmotionResult, of: str) -> tuple[Any, float]:
        assert r.answer is not None
        options: Mapping[Any, float] = r.answer.emotions if of == "emotion" else r.answer.nods
        return max(options.items(), key=lambda item: item[1])

    def spread(of: str, right: bool) -> dict:
        return _distribution([
            likeliest(r, of)[1] for r in answered
            if (likeliest(r, of)[0] == getattr(r.case, of)) == right
        ])

    return {
        "cases": len(results),
        "failed": len(results) - len(answered),
        "emotion_accuracy": _share(answered, lambda r: r.emotion == r.case.emotion),
        "nod_accuracy": _share(answered, lambda r: r.nod == r.case.nod),
        # How sure it is of its likeliest option when that is the one expected, and when
        # not: `JUDGE_EMOTION_MIN_PROBABILITY` should fall between.
        "likeliest_emotion": {"right": spread("emotion", True), "wrong": spread("emotion", False)},
        "likeliest_nod": {"right": spread("nod", True), "wrong": spread("nod", False)},
        "input_tokens": _distribution(
            [r.input_tokens for r in answered if r.input_tokens is not None]
        ),
    }


def _share(items: Sequence[T], right: Callable[[T], bool]) -> float | None:
    return sum(map(right, items)) / len(items) if items else None


def _distribution(values: Sequence[float]) -> dict:
    if not values:
        return {"n": 0}
    return {
        "n": len(values), "min": min(values), "median": statistics.median(values),
        "max": max(values),
    }


def _nod_name(nod: Nod | None) -> str:
    return nod or "none"


def report(results: JudgeEvalResults, summary: dict) -> str:
    """The summary, then every case: expected, actual, and the probabilities."""
    t = summary["thresholds"]
    lines = [
        f"判断模型：{summary['model']}",
        f"阈值：needs_retrieval {t['needs_retrieval']:g}，recall {t['recall']:g}，"
        f"about_producer {t['about_producer']:g}，情绪 {t['emotion']:g}",
        f"平均延迟：{_seconds(summary['mean_seconds'])}",
    ]
    for group, title in (("all", "全部"), ("short", "普通上文"), ("long", "长上文")):
        s = summary["retrieval"][group]
        if not s["cases"]:
            continue
        lines += [
            "",
            f"## 检索判断 · {title}（{s['cases']} 条，失败 {s['failed']}）",
            f"准确率 {_percent(s['accuracy'])}　输入 token {_spread(s['input_tokens'], 'd')}",
            "混淆矩阵（行：期望，列：实际）",
            "　　　　　" + "".join(f"{need:>12}" for need in get_args(Need)),
        ]
        for expected, row in s["confusion"].items():
            lines.append(
                f"{expected:>10}" + "".join(f"{row.get(need, 0):>12}" for need in get_args(Need))
            )
        if group == "all":
            lines.append("各题概率（期望为是 / 期望为否）")
            for question, spread in s["probabilities"].items():
                lines.append(f"  {question}")
                lines.append(f"    是 {_spread(spread['yes'])}")
                lines.append(f"    否 {_spread(spread['no'])}")
    e = summary["emotion"]
    if e["cases"]:
        lines += [
            "",
            f"## 情绪判断（{e['cases']} 条，失败 {e['failed']}）",
            f"情绪准确率 {_percent(e['emotion_accuracy'])}　点头准确率 {_percent(e['nod_accuracy'])}"
            f"　输入 token {_spread(e['input_tokens'], 'd')}",
            f"最可能的情绪，猜对时的概率 {_spread(e['likeliest_emotion']['right'])}",
            f"　　　　　　　猜错时的概率 {_spread(e['likeliest_emotion']['wrong'])}",
            f"最可能的点头，猜对时的概率 {_spread(e['likeliest_nod']['right'])}",
            f"　　　　　　　猜错时的概率 {_spread(e['likeliest_nod']['wrong'])}",
        ]
    lines += ["", "## 逐条检索判断（✓ 对，✗ 错，! 失败）"]
    for r in results.retrieval:
        long = "［长］" if r.case.long else ""
        if r.answer is None:
            lines.append(f"! {r.case.id}{long} 期望 {r.case.expected}：{r.error}")
            continue
        mark = "✓" if r.actual == r.case.expected else "✗"
        lines.append(
            f"{mark} {r.case.id}{long} 期望 {r.case.expected} 实际 {r.actual}"
            f"　needs_retrieval {r.answer.needs_retrieval:.3f} recall {r.answer.recall:.3f}"
            f" about_producer {r.answer.about_producer:.3f}"
            f"　{r.input_tokens or '?'} token {_seconds(r.seconds)}"
        )
    lines += ["", "## 逐条情绪判断"]
    for r in results.emotion:
        expected = f"{r.case.emotion}/{_nod_name(r.case.nod)}"
        if r.answer is None:
            lines.append(f"! {r.case.id} 期望 {expected}：{r.error}")
            continue
        mark = "✓" if (r.emotion, r.nod) == (r.case.emotion, r.case.nod) else "✗"
        emotions = " ".join(
            f"{k} {v:.2f}" for k, v in sorted(r.answer.emotions.items(), key=lambda i: -i[1])
        )
        nods = " ".join(
            f"{_nod_name(k)} {v:.2f}" for k, v in sorted(r.answer.nods.items(), key=lambda i: -i[1])
        )
        lines.append(
            f"{mark} {r.case.id} 期望 {expected} 实际 {r.emotion}/{_nod_name(r.nod)}"
            f"　{emotions}　｜ {nods}　{r.input_tokens or '?'} token {_seconds(r.seconds)}"
        )
    return "\n".join(lines)


def _spread(d: dict, form: str = ".3f") -> str:
    if not d["n"]:
        return "n=0"
    return (
        f"n={d['n']} 最低 {d['min']:{form}} 中位 {d['median']:{'.1f' if form == 'd' else form}}"
        f" 最高 {d['max']:{form}}"
    )


def _percent(share: float | None) -> str:
    return "—" if share is None else f"{share:.0%}"


def _seconds(seconds: float | None) -> str:
    return "—" if seconds is None else f"{seconds:.2f}s"
