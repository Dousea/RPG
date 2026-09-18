"""Shared test helpers: an isolated save file and stubs for the slow edges."""

import shutil
import tempfile
import unittest
from pathlib import Path

from adapters import persistence


class FakeMemory:
    """Stands in for SemanticMemory.

    The real one loads a sentence-transformer model on first use, which would
    make every test slow and network-dependent. Recall is scripted instead:
    `next_hits` are the event-log indices the next search returns.
    """

    def __init__(self):
        self.next_hits: list[int] = []
        self.rebuilt_with: list[list[str]] = []
        self.searched_for: list[str] = []

    def rebuild(self, events: list[str]) -> None:
        self.rebuilt_with.append(list(events))

    def search(self, query_text: str, k: int = 2) -> list[int]:
        self.searched_for.append(query_text)
        return list(self.next_hits)


class ScriptedLLM:
    """Replaces adapters.llm's two network calls with canned answers."""

    def __init__(self, response: str = "", summary: str = "A summary."):
        self.response = response
        self.summary = summary
        self.prompts: list[str] = []
        self.summarized: list[str] = []
        self.error: Exception | None = None

    def query_game_master(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return self.response

    def query_summary(self, text: str) -> str:
        self.summarized.append(text)
        return self.summary


class IsolatedSaveTestCase(unittest.TestCase):
    """Base case that redirects the save file into a temp directory.

    Without this, anything that persists would overwrite the player's real
    gamedata/engine_state.json.
    """

    def setUp(self):
        super().setUp()
        self._temp_dir = tempfile.mkdtemp(prefix="rpg-test-")
        self.save_path = str(Path(self._temp_dir) / "engine_state.json")
        self._original_save_file = persistence.SAVE_FILE
        # Resolved at call time by save/load/delete, so patching it here is
        # enough to redirect every default-path write.
        persistence.SAVE_FILE = self.save_path

    def tearDown(self):
        persistence.SAVE_FILE = self._original_save_file
        shutil.rmtree(self._temp_dir, ignore_errors=True)
        super().tearDown()
