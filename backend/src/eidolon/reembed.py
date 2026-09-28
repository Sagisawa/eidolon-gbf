"""Embedding everything again after the embedding service, model or dimensions change
(ADR-0005), from the text already in the database and the character configuration: the
story corpus, the character facts, the work facts (songs, releases and live days), and
every user's memories. Nothing is downloaded or imported again.

Only what has no vector from the current model is embedded, in batches that are each
committed, so an interrupted run loses nothing and a rerun picks up where it stopped.
Only once all four are done are the other models' vectors dropped; a failure drops
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
from eidolon.facts import CharacterFacts
from eidolon.memory import Memories
from eidolon.work_facts import WorkFacts
from eidolon.world import World

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReembedReport:
    passages: int
    """Story passages embedded."""
    facts: int
    """Character facts embedded."""
    work: int
    """Work facts (songs, releases and live days) embedded."""
    memories: int
    """Memories embedded."""
    forgotten: int
    """Vectors of other models dropped (character facts', the work facts' and memories';
    each story passage keeps only one vector, which re-embedding replaces)."""


async def reembed(
    path: Path,
    characters: Iterable[Character],
    embedder: Embedder,
    batch: int = REEMBED_BATCH,
    world: World | None = None,
) -> ReembedReport:
    """Embed with `embedder` whatever in the database at `path` has no vector from it yet,
    the entries of `world` included, then drop the other models' vectors. Raises
    EmbeddingError, having dropped nothing but kept what it finished, if the embedding
    service fails."""
    by_id = {c.id: c for c in characters}
    corpus = StoryCorpus(path, embedder)
    facts = CharacterFacts(path, embedder, by_id.values())
    work = WorkFacts(path, embedder, world)
    memories = Memories(path, by_id, utc_now)
    try:
        missing = corpus.count_missing_vectors()
        log.info("剧情库：%d 段需要重新向量化", missing)
        passages = await corpus.embed_missing(
            batch, lambda done: log.info("剧情库：%d/%d 段", done, missing)
        )
        embedded_facts = await facts.embed_missing()
        log.info("角色资料：新向量化 %d 条", embedded_facts)
        embedded_work = await work.embed_missing()
        log.info("作品资料：新向量化 %d 条", embedded_work)
        embedded_memories = await memories.embed_missing(
            embedder, batch, lambda done: log.info("记忆：%d 条", done)
        )
        forgotten = (
            facts.forget_other_models()
            + work.forget_other_models()
            + memories.forget_other_models(embedder.model)
        )
    finally:
        corpus.close()
        facts.close()
        work.close()
        await memories.aclose()
    return ReembedReport(passages, embedded_facts, embedded_work, embedded_memories, forgotten)
