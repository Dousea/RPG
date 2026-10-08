"""FAISS semantic search over the full event log.

The sentence-transformer model is loaded lazily on first use: importing this
module must stay cheap so that `flask --app app` and the test suite do not pay
for a model load they may never need.
"""

import logging

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

import config

logger = logging.getLogger(__name__)

EMBEDDING_MODEL_NAME = config.memory.embedding_model_name
EMBEDDING_DIMENSION = config.memory.embedding_dimension

# Number of past events recalled per turn.
DEFAULT_RECALL = config.memory.default_recall


class SemanticMemory:
    """An IndexFlatIP index over event strings, searched by cosine similarity."""

    def __init__(self):
        self._model: SentenceTransformer | None = None
        self._index = None
        self._size = 0
        self._last_query: tuple[str, np.ndarray] | None = None

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            logger.info(f"Loading sentence transformer '{EMBEDDING_MODEL_NAME}'...")
            self._model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        """L2-normalized float32 vectors, one row per text; the model loads on first use."""
        vectors = np.asarray(self.model.encode(texts), dtype=np.float32)
        faiss.normalize_L2(vectors)
        return vectors

    def encode_query(self, text: str) -> np.ndarray:
        """The vector of one text, kept so that the turn's input is embedded once however many ask."""
        if self._last_query is None or self._last_query[0] != text:
            self._last_query = (text, self.encode([text]))
        return self._last_query[1]

    def rebuild(self, events: list[str]) -> None:
        """Rebuild the index from the full event log."""
        self._size = len(events)
        if not events:
            self._index = None
            return

        # IndexFlatIP on L2-normalized vectors gives cosine similarity.
        embeddings = self.encode(events)

        index = faiss.IndexFlatIP(EMBEDDING_DIMENSION)
        index.add(embeddings)
        self._index = index
        logger.info(f"Indexed {len(events)} events.")

    def search(self, query_text: str, k: int = DEFAULT_RECALL) -> list[int]:
        """Return indices into the event log of the k most similar past events."""
        if self._index is None or self._size == 0 or not query_text.strip():
            return []

        _scores, indices = self._index.search(self.encode_query(query_text), min(k, self._size))
        # FAISS pads unfilled slots with -1.
        return [int(i) for i in indices[0] if i >= 0]
