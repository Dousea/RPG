"""world-lore: Semantic retrieval: the index of the lorebook and the one embedding per turn."""

import logging
import unittest

import numpy as np

from adapters.lore_index import LoreIndex
from adapters.memory import EMBEDDING_DIMENSION, SemanticMemory
from managers.story.lorebook import get_lorebook


class StubModel:
    """Stands in for the sentence transformer; `failure` makes every encode raise."""

    def __init__(self, failure: Exception | None = None):
        self.calls: list[list[str]] = []
        self.failure = failure

    def encode(self, texts):
        self.calls.append(list(texts))
        if self.failure is not None:
            raise self.failure
        rows = np.zeros((len(texts), EMBEDDING_DIMENSION), dtype=np.float32)
        for row, text in zip(rows, texts, strict=True):
            row[len(text) % EMBEDDING_DIMENSION] = 1.0
        return rows


def memory_over(model: StubModel) -> SemanticMemory:
    memory = SemanticMemory()
    memory._model = model  # pyright: ignore[reportAttributeAccessIssue]
    return memory


def candidates() -> dict[str, str]:
    return {e.entry_id: e.content for e in get_lorebook().world_entries() if e.keys and e.semantic}


class LoreIndexTests(unittest.TestCase):
    def test_nothing_is_embedded_until_the_first_scores_call(self):
        model = StubModel()
        index = LoreIndex(memory_over(model))
        self.assertEqual(model.calls, [])

        index.scores("anything")
        index.scores("something else")
        batch = sorted(candidates().values())
        embedded = [call for call in model.calls if sorted(call) == batch]
        self.assertEqual(len(embedded), 1)

    def test_only_the_candidates_are_indexed_and_each_gets_a_score(self):
        model = StubModel()
        scores = LoreIndex(memory_over(model)).scores("anything")
        wanted = candidates()
        self.assertEqual(set(scores), set(wanted))
        self.assertEqual(sorted(model.calls[0]), sorted(wanted.values()))

    def test_a_score_is_the_cosine_of_the_query_and_the_content(self):
        wanted = candidates()
        entry_id, content = next(iter(wanted.items()))
        scores = LoreIndex(memory_over(StubModel())).scores(content)
        self.assertAlmostEqual(scores[entry_id], 1.0, places=5)

    def test_a_failing_model_gives_nothing_with_one_warning_and_no_exception(self):
        model = StubModel(failure=RuntimeError("no model"))
        index = LoreIndex(memory_over(model))
        with self.assertLogs("adapters.lore_index", logging.WARNING) as logs:
            self.assertEqual(index.scores("first"), {})
            self.assertEqual(index.scores("second"), {})
        self.assertEqual(len(logs.records), 1)
        self.assertEqual(len(model.calls), 1)

    def test_the_input_is_encoded_once_for_the_deep_memory_search_and_the_lore_scores(self):
        model = StubModel()
        memory = memory_over(model)
        memory.rebuild(["an old event"])
        index = LoreIndex(memory)
        model.calls.clear()

        memory.search("who made the sickness")
        index.scores("who made the sickness")
        self.assertEqual(model.calls.count(["who made the sickness"]), 1)


if __name__ == "__main__":
    unittest.main()
