"""The vector index of songs, releases and live days, shared by every character.

Its entries come from the world setting's data file (`World.entries`), not an import:
they are the work's scope of the embedded text set, embedded the first time the index is
searched and kept until an entry is edited or removed, so a new data file takes effect
after a restart without any command and costs only the changed entries.
"""

from collections.abc import Collection, Sequence
from pathlib import Path

from eidolon.embedded_texts import WORK_SCOPE, EmbeddedTexts
from eidolon.embedding import Document, Embedder
from eidolon.world import EntryKind, World, WorldEntry


class WorldIndex:
    def __init__(self, path: Path, embedder: Embedder, world: World | None) -> None:
        """Without `world` (no data file), the index has no entries: any vectors stored
        for the embedder's model are forgotten the first time it loads."""
        self._texts = EmbeddedTexts(path, embedder)
        self._entries = list({e.text: e for e in (world.entries() if world else [])}.values())
        self._documents = [Document(e.text, e.title) for e in self._entries]

    async def search_by_vector(
        self,
        query_vector: Sequence[float],
        limit: int,
        kinds: Collection[EntryKind] | None = None,
    ) -> list[WorldEntry]:
        """The entries (of `kinds`, or any) most similar to a query embedded with this
        index's embedder."""
        among = [i for i, e in enumerate(self._entries) if kinds is None or e.kind in kinds]
        best = await self._texts.search(WORK_SCOPE, self._documents, query_vector, limit, among)
        return [self._entries[i] for i in best]

    async def embed_missing(self) -> int:
        """Embed the entries that have no vector from this index's embedder yet; returns
        how many that was."""
        return await self._texts.embed_missing(WORK_SCOPE, self._documents)

    def forget_other_models(self) -> int:
        """Drop every vector not from this index's embedder; returns how many there were."""
        return self._texts.forget_other_models(WORK_SCOPE)

    def close(self) -> None:
        self._texts.close()
