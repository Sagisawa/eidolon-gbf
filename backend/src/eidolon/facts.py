"""The vector index of character facts.

Facts come from the character configuration, not an import: each is embedded the
first time its character's facts are searched, and the vector is kept in SQLite
until the fact is edited or removed, so an edit to a facts file takes effect after
a restart without any command and costs only the changed entries.
"""

import sqlite3
import threading
from collections.abc import Sequence
from pathlib import Path

from eidolon.characters import Character
from eidolon.embedding import Embedder, nearest, to_blob

_SCHEMA = """
CREATE TABLE IF NOT EXISTS character_facts (
    character_id TEXT NOT NULL,
    text TEXT NOT NULL,
    model TEXT NOT NULL,
    embedding BLOB NOT NULL,
    PRIMARY KEY (character_id, model, text)
);
"""


class FactIndex:
    def __init__(self, path: Path, embedder: Embedder) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self._lock = threading.Lock()
        self._embedder = embedder
        with self._lock, self._db:
            self._db.executescript(_SCHEMA)

    async def search_by_vector(
        self, query_vector: Sequence[float], character: Character, limit: int = 5
    ) -> list[str]:
        """The character's facts most similar to a query embedded with this index's embedder."""
        vectors = await self._vectors(character)
        facts = list(vectors)
        best = nearest([vectors[f] for f in facts], query_vector, limit)
        return [facts[i] for i, _ in best]

    def close(self) -> None:
        self._db.close()

    async def _vectors(self, character: Character) -> dict[str, bytes]:
        """The vector of each of the character's facts, embedding those not yet stored and
        forgetting those no longer configured."""
        model = self._embedder.model
        with self._lock:
            stored = dict(
                self._db.execute(
                    "SELECT text, embedding FROM character_facts"
                    " WHERE character_id = ? AND model = ?",
                    (character.id, model),
                ).fetchall()
            )
        missing = [f for f in dict.fromkeys(character.facts) if f not in stored]
        stale = stored.keys() - set(character.facts)
        if missing:
            embedded = await self._embedder.embed_documents(missing)
            stored.update(zip(missing, (to_blob(v) for v in embedded), strict=True))
        if missing or stale:
            with self._lock, self._db:
                self._db.executemany(
                    "INSERT OR REPLACE INTO character_facts (character_id, text, model, embedding)"
                    " VALUES (?, ?, ?, ?)",
                    [(character.id, f, model, stored[f]) for f in missing],
                )
                self._db.executemany(
                    "DELETE FROM character_facts WHERE character_id = ? AND model = ? AND text = ?",
                    [(character.id, model, f) for f in stale],
                )
        return {f: stored[f] for f in character.facts}
