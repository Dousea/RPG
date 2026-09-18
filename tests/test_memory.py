"""SemanticMemory against real FAISS and a real embedding model.

Skipped by default: the first run downloads the sentence-transformer model.
Opt in with RPG_TEST_EMBEDDINGS=1.
"""

import os
import unittest

from adapters.memory import SemanticMemory

REQUIRES_MODEL = unittest.skipUnless(
    os.environ.get("RPG_TEST_EMBEDDINGS") == "1",
    "set RPG_TEST_EMBEDDINGS=1 to run (downloads an embedding model)",
)


class EmptyIndexTests(unittest.TestCase):
    """These need no model, because an empty index short-circuits."""

    def test_search_on_an_empty_index_returns_nothing(self):
        memory = SemanticMemory()
        memory.rebuild([])
        self.assertEqual(memory.search("anything"), [])

    def test_search_before_any_rebuild_returns_nothing(self):
        self.assertEqual(SemanticMemory().search("anything"), [])

    def test_model_is_not_loaded_for_an_empty_rebuild(self):
        memory = SemanticMemory()
        memory.rebuild([])
        self.assertIsNone(memory._model)


@REQUIRES_MODEL
class SemanticSearchTests(unittest.TestCase):
    EVENTS = [
        "Orton found a crowbar in the office.",
        "Emma shared her groceries in the hallway.",
        "The radio broadcast a quarantine warning.",
        "Orton barricaded the apartment door.",
    ]

    def setUp(self):
        self.memory = SemanticMemory()
        self.memory.rebuild(self.EVENTS)

    def test_search_returns_valid_indices(self):
        hits = self.memory.search("what did I pick up?")
        self.assertTrue(hits)
        for index in hits:
            self.assertGreaterEqual(index, 0)
            self.assertLess(index, len(self.EVENTS))

    def test_search_finds_the_topically_closest_event(self):
        hits = self.memory.search("Tell me about the neighbour and the food.")
        self.assertIn(1, hits)

    def test_k_caps_the_result_count(self):
        self.assertLessEqual(len(self.memory.search("anything", k=2)), 2)

    def test_k_larger_than_the_index_is_safe(self):
        hits = self.memory.search("anything", k=99)
        self.assertLessEqual(len(hits), len(self.EVENTS))

    def test_blank_query_returns_nothing(self):
        self.assertEqual(self.memory.search("   "), [])

    def test_rebuild_shrinks_the_index(self):
        self.memory.rebuild(self.EVENTS[:1])
        self.assertEqual(self.memory.search("anything", k=5), [0])


if __name__ == "__main__":
    unittest.main()
