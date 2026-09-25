"""Retrieval for a conversation turn: whether to look anything up, and what to bring back.

Jev (through Vercel AI Gateway) first judges whether what the user just said calls
for looking anything up, so small talk costs no retrieval latency. When it does,
the story corpus (only episodes the character is cast in) and the character's facts
are searched with the same query vector, the candidates are reranked together, and
the best few that are relevant enough go into the prompt.

Retrieval never fails a turn: if Jev cannot answer, the turn retrieves anyway; if
embedding or reranking fails, the turn goes on without references.

The chat model can also look an episode up itself with the recall-story tool, for
general questions like "what happened that time with the photo book": the best
matching episodes she is cast in come back with where they sit in her story catalog
(card or event, and its other episodes) and what happened in them.
"""

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

import httpx

from eidolon.characters import Character
from eidolon.corpus import CatalogSource, Episode, StoryCorpus
from eidolon.embedding import Embedder, EmbeddingError
from eidolon.facts import FactIndex
from eidolon.llm import Tool
from eidolon.rerank import Reranker, RerankError
from eidolon.store import Message

log = logging.getLogger(__name__)

MAX_REFERENCES = 5
"""The most references one turn's prompt carries, after reranking."""
MIN_RELEVANCE = 0.3
"""The reranker's score below which a candidate is left out of the prompt. Qwen3-Reranker
scores relevant passages around 0.9 and unrelated ones below 0.1, so a question about
something the character never lived through brings back nothing rather than filler."""
CANDIDATES_PER_SOURCE = 12
"""How many candidates each source (story corpus, character facts) offers the reranker."""
JUDGE_HISTORY = 4
"""How many of the latest messages Jev sees along with what the user just said."""


RECALL_EPISODES = 2
"""The most episodes one call of the recall-story tool brings back."""
RECALL_EPISODE_CHARS = 3000
"""How much of an episode's dialogue the recall-story tool brings back before cutting it short."""

RECALL_STORY_TOOL = Tool(
    name="recall_story",
    description="回顾剧情：在你亲身经历过的原作剧情中查找和某件事有关的剧情，返回它在你的剧情目录中的位置"
    "（哪张卡或哪个活动）和剧情内容。当制作人问起「那次……是怎么回事」这类过去的事、"
    "而你想不起具体经过时使用；闲聊时不需要。",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "要回顾的事，写成一句概括，例如「拍写真集的那次」「W.I.N.G. 决赛」",
            }
        },
        "required": ["query"],
    },
)


_CANON_RULE = (
    "剧情里没有记录制作人当时选了哪个选项，不要断言制作人当时说了什么或选了什么。"
)


class RetrievalJudge(Protocol):
    async def needs_retrieval(
        self, character: Character, history: Sequence[Message], text: str
    ) -> bool:
        """Whether answering `text` would benefit from the story corpus or character facts."""
        ...


class JudgeError(RuntimeError):
    pass


@dataclass(frozen=True)
class Reference:
    kind: Literal["episode", "fact"]
    text: str


class Retrieval:
    def __init__(
        self,
        judge: RetrievalJudge,
        embedder: Embedder,
        corpus: StoryCorpus,
        facts: FactIndex,
        reranker: Reranker,
    ) -> None:
        self._judge = judge
        self._embedder = embedder
        self._corpus = corpus
        self._facts = facts
        self._reranker = reranker

    async def references(
        self, character: Character, history: Sequence[Message], text: str
    ) -> list[Reference]:
        """What this turn's prompt should carry, most relevant first; empty when the turn
        needs no retrieval."""
        try:
            needed = await self._judge.needs_retrieval(character, history, text)
        except JudgeError:
            log.warning("retrieval judge failed; retrieving anyway", exc_info=True)
            needed = True
        if not needed:
            return []

        try:
            query_vector = await self._embedder.embed_query(text)
            passages, facts = await asyncio.gather(
                asyncio.to_thread(
                    self._corpus.search_by_vector, query_vector, character.id, CANDIDATES_PER_SOURCE
                ),
                self._facts.search_by_vector(query_vector, character, CANDIDATES_PER_SOURCE),
            )
            candidates = [Reference("episode", p.text) for p in passages]
            candidates += [Reference("fact", f) for f in facts]
            if not candidates:
                return []
            best = await self._reranker.rerank(
                text, [c.text for c in candidates], MAX_REFERENCES
            )
        except (EmbeddingError, RerankError):
            log.warning("retrieval failed; replying without references", exc_info=True)
            return []
        return [candidates[i] for i, score in best[:MAX_REFERENCES] if score >= MIN_RELEVANCE]

    async def recall_story(self, character: Character, query: str) -> str:
        """The recall-story tool: the episodes `character` is cast in that best match
        `query`, for the chat model to answer from."""
        try:
            query_vector = await self._embedder.embed_query(query)
            passages = await asyncio.to_thread(
                self._corpus.search_by_vector, query_vector, character.id, CANDIDATES_PER_SOURCE
            )
            best = (
                await self._reranker.rerank(query, [p.text for p in passages], len(passages))
                if passages
                else []
            )
        except (EmbeddingError, RerankError):
            log.warning("recall_story failed", exc_info=True)
            return "暂时想不起来，现在查不到剧情。不要编造经过，可以坦率地说记不太清了。"
        episodes: dict[str, Episode] = {}
        for i, score in best:
            if score >= MIN_RELEVANCE and len(episodes) < RECALL_EPISODES:
                episodes.setdefault(passages[i].episode.id, passages[i].episode)
        if not episodes:
            return (
                f"没有想起和「{query}」有关的剧情：你没有经历过这件事，或者剧情库里没有记录。"
                "不要编造经过，可以坦率地说不记得了，或者问问制作人。"
            )
        catalog = await asyncio.to_thread(self._corpus.catalog, character.id)
        return recall_prompt(query, list(episodes.values()), catalog)

    def close(self) -> None:
        self._corpus.close()
        self._facts.close()


def references_prompt(references: Sequence[Reference]) -> str:
    """The prompt section carrying a turn's references."""
    lines = [
        "# 回忆与资料",
        "下面是和制作人这句话可能有关的内容，按相关程度排列，和话题无关的可以忽略。",
        "- 「剧情」是你亲身经历过的原作剧情，可以像回忆往事一样自然地提起，不要照搬台词。"
        + _CANON_RULE,
        "- 「角色资料」是关于你自己和身边人物的设定。",
    ]
    for reference in references:
        heading = "剧情" if reference.kind == "episode" else "角色资料"
        lines += ["", f"## {heading}", reference.text]
    return "\n".join(lines)


def recall_prompt(query: str, episodes: Sequence[Episode], catalog: Sequence[CatalogSource]) -> str:
    """The recall-story tool's result: each episode under its place in the story catalog."""
    lines = [
        f"# 回顾剧情：{query}",
        "下面是你经历过的剧情中和这件事最相关的，按相关程度排列。用自己的话回忆经过，不要照搬台词。"
        + _CANON_RULE,
    ]
    for episode in episodes:
        source = next(
            (s for s in catalog if any(e.episode_id == episode.id for e in s.episodes)), None
        )
        lines += ["", f"## {episode.category} / {episode.source} /「{episode.title}」"]
        if source is not None and len(source.episodes) > 1:
            titles = "".join(f"「{e.title}」" for e in source.episodes)
            lines.append(f"（{episode.source}中你出场的剧情依次是：{titles}）")
        lines.append(_transcript(episode))
    return "\n".join(lines)


def _transcript(episode: Episode) -> str:
    text = ""
    for line in episode.lines:
        said = f"{line.speaker}：{line.ja}" if line.speaker else line.ja
        if line.zh:
            said += f"（{line.zh}）"
        if len(text) + len(said) > RECALL_EPISODE_CHARS:
            return (text or said[:RECALL_EPISODE_CHARS]) + "……（后略）"
        text += said + "\n"
    return text.rstrip("\n")


_JUDGE_QUESTION = {
    "type": "boolean",
    "instructions": "角色扮演对话中，角色是《偶像大师 闪耀色彩》的偶像，正在和她的制作人对话。"
    "可检索的资料有两类：她亲身经历过的原作剧情，以及关于她自己和身边人物的设定（档案、人物关系等）。"
    "回答制作人最新的一句话，是否需要检索这些资料？",
    "criteria": {
        "true": "需要回忆过去的具体经历、提到具体的人物或事件、或需要确认角色设定细节",
        "false": "只是寒暄、闲聊、情绪回应，或只凭上文就能回答",
    },
}
JUDGE_THRESHOLD = 0.5
"""Jev's probability at or above which a turn retrieves."""


class JevJudge:
    """Jev through Vercel AI Gateway's evaluation endpoint (`/v1/evaluate`): Jev is an
    evaluation model, answering typed questions about a state with probabilities, and is
    not served by the Chat Completions endpoint."""

    def __init__(
        self, api_key: str, model: str, base_url: str, client: httpx.AsyncClient | None = None
    ) -> None:
        self._url = base_url.rstrip("/") + "/evaluate"
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(5, connect=3))

    async def needs_retrieval(
        self, character: Character, history: Sequence[Message], text: str
    ) -> bool:
        recent = []
        for message in history[-JUDGE_HISTORY:]:
            if message.role == "user":
                recent.append(f"制作人：{message.text}")
            else:
                recent.append(f"{character.name}：{message.ja}")
        body = {
            "model": self._model,
            "state": {
                "角色": character.name,
                "上文": recent or "（对话刚开始）",
                "制作人最新的一句话": text,
            },
            "questions": {"needs_retrieval": _JUDGE_QUESTION},
        }
        try:
            res = await self._client.post(
                self._url, json=body, headers={"Authorization": f"Bearer {self._api_key}"}
            )
        except httpx.HTTPError as e:
            raise JudgeError(f"无法连接 Jev：{e!r}") from e
        if res.status_code >= 400:
            raise JudgeError(f"Jev 返回 {res.status_code}: {res.text[:500]}")
        try:
            probability = float(res.json()["answers"]["needs_retrieval"]["probability"])
        except (ValueError, KeyError, TypeError) as e:
            raise JudgeError(f"Jev 的返回无法解析：{res.text[:500]}") from e
        return probability >= JUDGE_THRESHOLD

    async def aclose(self) -> None:
        await self._client.aclose()
