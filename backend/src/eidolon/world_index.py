"""The vector index of songs, releases and live days, shared by every character.

Its entries come from the world setting's data file (`World.entries`), not an import:
like the character facts, they are embedded the first time the index is searched, and
each vector is kept in SQLite by its text and model until the entry is edited or
removed, so a new data file takes effect after a restart without any command and costs
only the changed entries. The vectors are then kept in memory: the data file does not
change while the server runs.
"""

import asyncio
import sqlite3
import threading
from collections.abc import Collection, Sequence
from pathlib import Path

from eidolon.corpus import REEMBED_BATCH
from eidolon.embedding import Document, Embedder, nearest, to_blob
from eidolon.world import EntryKind, World, WorldEntry

_SCHEMA = """
CREATE TABLE IF NOT EXISTS world_entries (
    text TEXT NOT NULL,
    model TEXT NOT NULL,
    embedding BLOB NOT NULL,
    PRIMARY KEY (model, text)
);
"""


class WorldIndex:
    def __init__(self, path: Path, embedder: Embedder, world: World | None) -> None:
        """Without `world` (no data file), the index has no entries: any vectors stored
        for the embedder's model are forgotten the first time it loads."""
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self._lock = threading.Lock()
        self._embedder = embedder
        self._entries = list({e.text: e for e in (world.entries() if world else [])}.values())
        self._vectors: list[bytes] | None = None
        self._loading = asyncio.Lock()
        with self._lock, self._db:
            self._db.executescript(_SCHEMA)

    async def search_by_vector(
        self,
        query_vector: Sequence[float],
        limit: int,
        kinds: Collection[EntryKind] | None = None,
    ) -> list[WorldEntry]:
        """The entries (of `kinds`, or any) most similar to a query embedded with this
        index's embedder."""
        vectors, _ = await self._load()
        among = [i for i, e in enumerate(self._entries) if kinds is None or e.kind in kinds]
        best = nearest([vectors[i] for i in among], query_vector, limit)
        return [self._entries[among[i]] for i, _ in best]

    async def embed_missing(self) -> int:
        """Embed the entries that have no vector from this index's embedder yet; returns
        how many that was."""
        _, embedded = await self._load()
        return embedded

    def forget_other_models(self) -> int:
        """Drop every vector not from this index's embedder; returns how many there were."""
        with self._lock, self._db:
            return self._db.execute(
                "DELETE FROM world_entries WHERE model != ?", (self._embedder.model,)
            ).rowcount

    def close(self) -> None:
        self._db.close()

    async def _load(self) -> tuple[list[bytes], int]:
        """The vector of each entry, in order, embedding those not yet stored (in batches,
        each committed) and forgetting those no longer in the data file; and how many it
        embedded."""
        async with self._loading:
            if self._vectors is not None:
                return self._vectors, 0
            model = self._embedder.model
            with self._lock:
                stored = dict(
                    self._db.execute(
                        "SELECT text, embedding FROM world_entries WHERE model = ?", (model,)
                    ).fetchall()
                )
            texts = {e.text for e in self._entries}
            missing = [e for e in self._entries if e.text not in stored]
            if stale := stored.keys() - texts:
                with self._lock, self._db:
                    self._db.executemany(
                        "DELETE FROM world_entries WHERE model = ? AND text = ?",
                        [(model, t) for t in stale],
                    )
            for start in range(0, len(missing), REEMBED_BATCH):
                batch = missing[start : start + REEMBED_BATCH]
                embedded = await self._embedder.embed_documents(
                    [Document(e.text, e.title) for e in batch]
                )
                rows = [(e.text, model, to_blob(v)) for e, v in zip(batch, embedded, strict=True)]
                with self._lock, self._db:
                    self._db.executemany(
                        "INSERT OR REPLACE INTO world_entries (text, model, embedding)"
                        " VALUES (?, ?, ?)",
                        rows,
                    )
                stored.update((text, blob) for text, _, blob in rows)
            self._vectors = [stored[e.text] for e in self._entries]
            return self._vectors, len(missing)
