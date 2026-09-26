"""Embedding everything again after the embedding service, model or dimensions change
(ADR-0005), from the text already in the database: the story corpus, the character facts
and every user's memories. Nothing is downloaded or imported again.

Only what has no vector from the current model is embedded, in batches that are each
committed, so an interrupted run loses nothing and a rerun picks up where it stopped.
Only once all three are done are the other models' vectors dropped; a failure drops
nothing. The server can keep running meanwhile: its searches find only what is done.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from eidolon.characters import Character
from eidolon.clock import utc_now
from eidolon.corpus import REEMBED_BATCH, StoryCorpus
from eidolon.embedding import Embedder
from eidolon.facts import FactIndex
from eidolon.memory import Memories

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReembedReport:
    passages: int
    """Story passages embedded."""
    facts: int
    """Character facts embedded."""
    memories: int
    """Memories embedded."""
    forgotten: int
    """Vectors of other models dropped (character facts' and memories'; each story passage
    keeps only one vector, which re-embedding replaces)."""


async def reembed(
    path: Path,
    characters: Iterable[Character],
    embedder: Embedder,
    batch: int = REEMBED_BATCH,
) -> ReembedReport:
    """Embed with `embedder` whatever in the database at `path` has no vector from it yet,
    then drop the other models' vectors. Raises EmbeddingError, having dropped nothing
    but kept what it finished, if the embedding service fails."""
    by_id = {c.id: c for c in characters}
    corpus = StoryCorpus(path, embedder)
    facts = FactIndex(path, embedder)
    memories = Memories(path, by_id, utc_now)
    try:
        missing = corpus.count_missing_vectors()
        log.info("剧情库：%d 段需要重新向量化", missing)
        passages = await corpus.embed_missing(
            batch, lambda done: log.info("剧情库：%d/%d 段", done, missing)
        )
        embedded_facts = 0
        for character in by_id.values():
            embedded_facts += await facts.embed_missing(character)
        log.info("角色资料：新向量化 %d 条", embedded_facts)
        embedded_memories = await memories.embed_missing(
            embedder, batch, lambda done: log.info("记忆：%d 条", done)
        )
        forgotten = facts.forget_other_models() + memories.forget_other_models(embedder.model)
    finally:
        corpus.close()
        facts.close()
        await memories.aclose()
    return ReembedReport(passages, embedded_facts, embedded_memories, forgotten)
