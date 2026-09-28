"""The vector index of character facts.

Facts come from the character configuration, not an import: each character's facts are a
scope of the embedded text set, embedded the first time they are searched and kept until
a fact is edited or removed, so an edit to a facts file takes effect after a restart
without any command and costs only the changed entries.
"""

from collections.abc import Sequence
from pathlib import Path

from eidolon.characters import Character, Fact
from eidolon.embedded_texts import CHARACTER_SCOPES, EmbeddedTexts, character_scope
from eidolon.embedding import Document, Embedder


class FactIndex:
    def __init__(self, path: Path, embedder: Embedder) -> None:
        self._texts = EmbeddedTexts(path, embedder)

    async def search_by_vector(
        self, query_vector: Sequence[float], character: Character, limit: int = 5
    ) -> list[Fact]:
        """The character's facts most similar to a query embedded with this index's embedder."""
        facts = _facts(character)
        best = await self._texts.search(
            character_scope(character.id), _documents(facts), query_vector, limit
        )
        return [facts[i] for i in best]

    async def embed_missing(self, character: Character) -> int:
        """Embed those of the character's facts that have no vector from this index's
        embedder yet; returns how many that was."""
        return await self._texts.embed_missing(
            character_scope(character.id), _documents(_facts(character))
        )

    def forget_other_models(self) -> int:
        """Drop every character's vectors not from this index's embedder; returns how many
        there were."""
        return self._texts.forget_other_models(CHARACTER_SCOPES)

    def close(self) -> None:
        self._texts.close()


def _facts(character: Character) -> list[Fact]:
    """The character's facts, one for each text."""
    return list({f.text: f for f in character.facts}.values())


def _documents(facts: Sequence[Fact]) -> list[Document]:
    return [Document(f.text, f.title) for f in facts]
