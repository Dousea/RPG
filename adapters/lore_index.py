"""Embedding similarity between the player's input and the lorebook (world-lore: Semantic retrieval)."""

import logging

import numpy as np

from adapters.memory import SemanticMemory
from managers.story.lorebook import get_lorebook

logger = logging.getLogger(__name__)


class LoreIndex:
    """Cosine similarity of a query to every keyed `world` entry that allows it.

    The lorebook is static, so the entries are embedded once, on the first `scores` call.
    A model that fails to load or encode gives `{}` from then on, with one warning.
    """

    def __init__(self, memory: SemanticMemory):
        self._memory = memory
        self._ids: list[str] = []
        self._vectors: np.ndarray | None = None
        self._failed = False

    def scores(self, query_text: str) -> dict[str, float]:
        """Entry id to similarity for every candidate; `{}` once the model has failed."""
        if self._failed:
            return {}

        try:
            if self._vectors is None:
                self._embed_candidates()
            assert self._vectors is not None
            query = np.asarray(self._memory.encode_query(query_text), dtype=np.float32)
            similarity = self._vectors @ query[0]
        except Exception as exc:
            self._failed = True
            logger.warning(f"Lore similarity is off: {exc}")
            return {}

        return {
            entry_id: float(score) for entry_id, score in zip(self._ids, similarity, strict=True)
        }

    def _embed_candidates(self) -> None:
        candidates = [
            entry for entry in get_lorebook().world_entries() if entry.keys and entry.semantic
        ]
        vectors = np.asarray(
            self._memory.encode([entry.content for entry in candidates]), dtype=np.float32
        )
        self._ids = [entry.entry_id for entry in candidates]
        self._vectors = vectors
        logger.info(f"Embedded {len(candidates)} lore entries.")
