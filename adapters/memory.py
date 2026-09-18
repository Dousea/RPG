"""FAISS semantic search over the full event log.

The sentence-transformer model is loaded lazily on first use: importing this
module must stay cheap so that `flask --app app` and the test suite do not pay
for a model load they may never need.
"""

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384

# Number of past events recalled per turn.
DEFAULT_RECALL = 2


class SemanticMemory:
    """An IndexFlatIP index over event strings, searched by cosine similarity."""

    def __init__(self):
        self._model: SentenceTransformer | None = None
        self._index = None
        self._size = 0

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            print(f"[Memory] Loading sentence transformer '{EMBEDDING_MODEL_NAME}'...")
            self._model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        return self._model

    def rebuild(self, events: list[str]) -> None:
        """Rebuild the index from the full event log."""
        self._size = len(events)
        if not events:
            self._index = None
            return

        embeddings = self.model.encode(events)
        embeddings = np.asarray(embeddings, dtype=np.float32)
        # IndexFlatIP on L2-normalized vectors gives cosine similarity.
        faiss.normalize_L2(embeddings)

        index = faiss.IndexFlatIP(EMBEDDING_DIMENSION)
        index.add(embeddings)
        self._index = index
        print(f"[Memory] Indexed {len(events)} events.")

    def search(self, query_text: str, k: int = DEFAULT_RECALL) -> list[int]:
        """Return indices into the event log of the k most similar past events."""
        if self._index is None or self._size == 0 or not query_text.strip():
            return []

        query = np.asarray(self.model.encode([query_text]), dtype=np.float32)
        faiss.normalize_L2(query)

        _scores, indices = self._index.search(query, min(k, self._size))
        # FAISS pads unfilled slots with -1.
        return [int(i) for i in indices[0] if i >= 0]
