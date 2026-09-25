"""Retrieval for a conversation turn: whether to look anything up, and what to bring back.

Jev (through Vercel AI Gateway) first judges what the user just said needs: nothing,
so small talk costs no retrieval latency; memories only, when the user talks about their
own life, for which the memories of what they have told any of the characters are
searched and reranked; references, for which the story corpus
(only episodes the character is cast in) and the character's facts are searched with
the same query vector, along with the memories of what the user has told any of the
characters, the candidates reranked together, and the best few that are relevant enough
go into the prompt; or recall, for a question about how some past
episode went, for which the recall-story tool is run on what the user said and its
result goes into the prompt, saving the chat model a round of calling it.

Retrieval never fails a turn: if Jev cannot answer, the turn retrieves anyway; if
embedding or reranking fails, the turn goes on without references.

The chat model can also look an episode up itself with the recall-story tool, for
general questions like "what happened that time with the photo book" that Jev did
not catch: the best matching episodes she is cast in come back with where they sit in
her story catalog (card or event, and its other episodes) and what happened in them.
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
from eidolon.memory import MemoryIndex
from eidolon.rerank import Reranker, RerankError
from eidolon.store import Memory, Message

log = logging.getLogger(__name__)

MAX_REFERENCES = 5
"""The most references one turn's prompt carries, after reranking."""
MIN_RELEVANCE = 0.3
"""The reranker's score below which a candidate is left out of the prompt. Qwen3-Reranker
scores relevant passages around 0.9 and unrelated ones below 0.1, so a question about
something the character never lived through brings back nothing rather than filler."""
MAX_MEMORIES = 3
"""The most memories one turn's prompt carries, after reranking; they do not count
towards `MAX_REFERENCES`."""
MIN_MEMORY_RELEVANCE = 0.01
"""The reranker's score below which a memory is left out. Qwen3-Reranker scores a short
memory low against a loosely related remark (「我最近要出远门」 against a business trip to
Hokkaido scores 0.03) but unrelated ones lower still (at most 0.005), so memories get a
threshold of their own."""
CANDIDATES_PER_SOURCE = 12
"""How many candidates each source (story corpus, character facts, memories) offers the
reranker."""
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


Need = Literal["nothing", "memories", "references", "recall"]
"""What a turn needs looked up: nothing, the user's memories only, references from the
story corpus and character facts along with the user's memories, or the recall of a past
episode."""


class RetrievalJudge(Protocol):
    async def judge(self, character: Character, history: Sequence[Message], text: str) -> Need:
        """What answering `text` needs looked up."""
        ...


class JudgeError(RuntimeError):
    pass


@dataclass(frozen=True)
class Reference:
    kind: Literal["episode", "fact"]
    text: str


@dataclass(frozen=True)
class Retrieved:
    """What a turn looked up."""

    prompt: str | None
    """The prompt section carrying the references or recalled episodes, if any."""
    memories: tuple[Memory, ...] = ()
    """The user's memories relevant to the turn, most relevant first."""
    recalled: bool = False
    """Whether the recall-story tool already ran, so the chat model need not call it."""


class Retrieval:
    def __init__(
        self,
        judge: RetrievalJudge,
        embedder: Embedder,
        corpus: StoryCorpus,
        facts: FactIndex,
        memories: MemoryIndex,
        reranker: Reranker,
    ) -> None:
        self._judge = judge
        self._embedder = embedder
        self._corpus = corpus
        self._facts = facts
        self._memories = memories
        self._reranker = reranker

    async def retrieve(
        self, character: Character, user_id: str, history: Sequence[Message], text: str
    ) -> Retrieved:
        """Look up what this turn of `user_id`'s needs."""
        try:
            need = await self._judge.judge(character, history, text)
        except JudgeError:
            log.warning("retrieval judge failed; retrieving anyway", exc_info=True)
            need = "references"
        if need == "recall":
            return Retrieved(await self.recall_story(character, text), recalled=True)
        if need in ("references", "memories"):
            references, memories = await self._references(
                character, user_id, text, memories_only=need == "memories"
            )
            return Retrieved(
                references_prompt(references) if references else None, tuple(memories)
            )
        return Retrieved(None)

    async def _references(
        self, character: Character, user_id: str, text: str, memories_only: bool
    ) -> tuple[list[Reference], list[Memory]]:
        """The references (unless `memories_only`) and the user's memories for `text`, each
        most relevant first."""
        try:
            query_vector = await self._embedder.embed_query(text)
            memory_search = self._memories.search_by_vector(
                query_vector, user_id, CANDIDATES_PER_SOURCE
            )
            if memories_only:
                memories, passages, facts = await memory_search, [], []
            else:
                memories, passages, facts = await asyncio.gather(
                    memory_search,
                    asyncio.to_thread(
                        self._corpus.search_by_vector,
                        query_vector,
                        character.id,
                        CANDIDATES_PER_SOURCE,
                    ),
                    self._facts.search_by_vector(query_vector, character, CANDIDATES_PER_SOURCE),
                )
            candidates = [Reference("episode", p.text) for p in passages]
            candidates += [Reference("fact", f) for f in facts]
            documents = [c.text for c in candidates] + [m.text for m in memories]
            if not documents:
                return [], []
            best = await self._reranker.rerank(text, documents, len(documents))
        except (EmbeddingError, RerankError):
            log.warning("retrieval failed; replying without references", exc_info=True)
            return [], []
        references = [
            candidates[i] for i, score in best if i < len(candidates) and score >= MIN_RELEVANCE
        ]
        relevant_memories = [
            memories[i - len(candidates)]
            for i, score in best
            if i >= len(candidates) and score >= MIN_MEMORY_RELEVANCE
        ]
        return references[:MAX_REFERENCES], relevant_memories[:MAX_MEMORIES]

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
        self._memories.close()


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
_RECALL_QUESTION = {
    "type": "boolean",
    "instructions": "制作人最新的一句话，是不是在问角色过去某一次具体经历的来龙去脉"
    "（例如「那次……是怎么回事」「还记得……那次吗」），需要回想那段经历的完整经过才能回答？",
    "criteria": {
        "true": "问的是过去某一次具体的事情、活动、工作或比赛的经过和当时的心情",
        "false": "寒暄闲聊、问喜好或设定、问身边人物近况，或者只是顺口提到过去",
    },
}
_ABOUT_PRODUCER_QUESTION = {
    "type": "boolean",
    "instructions": "角色扮演对话中，角色是《偶像大师 闪耀色彩》的偶像，正在和她的制作人对话。"
    "制作人最新的一句话，是否说起或问起制作人自己的事（生活、近况、工作安排、计划、家人、宠物、喜好、"
    "身体状况等），而制作人以前对偶像们说过的相关的事可能有助于回应？",
    "criteria": {
        "true": "说起或问起制作人自己的生活、近况、计划、家人宠物、喜好，或提到以前对偶像说过的事",
        "false": "只是打招呼、说偶像自己的事、问原作剧情或角色设定，与制作人自己的生活无关",
    },
}
JUDGE_THRESHOLD = 0.5
"""Jev's probability at or above which a turn retrieves, or recalls."""


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

    async def judge(self, character: Character, history: Sequence[Message], text: str) -> Need:
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
            "questions": {
                "needs_retrieval": _JUDGE_QUESTION,
                "recall": _RECALL_QUESTION,
                "about_producer": _ABOUT_PRODUCER_QUESTION,
            },
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
            answers = res.json()["answers"]
            retrieve = float(answers["needs_retrieval"]["probability"])
            recall = float(answers["recall"]["probability"])
            about_producer = float(answers["about_producer"]["probability"])
        except (ValueError, KeyError, TypeError) as e:
            raise JudgeError(f"Jev 的返回无法解析：{res.text[:500]}") from e
        if recall >= JUDGE_THRESHOLD:
            return "recall"
        if retrieve >= JUDGE_THRESHOLD:
            return "references"
        return "memories" if about_producer >= JUDGE_THRESHOLD else "nothing"

    async def aclose(self) -> None:
        await self._client.aclose()
