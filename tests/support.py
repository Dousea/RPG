"""Shared test helpers: an isolated save file and stubs for the slow edges."""

import shutil
import tempfile
import unittest
from pathlib import Path

from adapters import persistence
from managers.game import GameManager
from managers.simulation import SimulationCore
from modules.action import AnyAction


def resolve_actions(gm: GameManager, *actions: AnyAction) -> list[str]:
    """Validate and resolve actions directly, bypassing the LLM turn loop.

    The Action Validator and Simulation Core (managers/validator.py,
    managers/simulation.py) are the only path to mutating state. Tests
    that need to set up state (rather than test the pipeline itself) go
    through this helper instead of poking fields directly, so fixtures stay
    honest about what the engine actually allows. Actions are resolved one at
    a time, in order, exactly as `SimulationCore.resolve` does for a real
    turn, so an earlier action (e.g. a move) can unlock a later one (e.g. a
    take) within the same call.
    """
    facts = SimulationCore(gm).resolve(list(actions))
    for action, fact in zip(actions, facts, strict=False):
        assert not fact.startswith("Refused:"), f"setup action {action!r} failed: {fact}"
    return facts


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
    """Replaces adapters.llm's three network calls with canned answers.

    `actions` scripts the parser call (an ACTIONS: block, or "NONE"); `story`
    scripts the narrator call (a STORY:/EVENT: block). Kept as two separate
    scripts because the turn loop now makes two calls, not one.
    """

    def __init__(
        self,
        actions: str = "ACTIONS:\nNONE",
        story: str = "STORY:\n...\n\nEVENT:\n...",
        summary: str = "A summary.",
    ):
        self.actions = actions
        self.story = story
        self.summary = summary
        self.prompts: list[str] = []  # parser-call prompts
        self.narrator_prompts: list[str] = []
        self.summarized: list[str] = []
        self.error: Exception | None = None

    def query_parser(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return self.actions

    def query_narrator(self, prompt: str) -> str:
        self.narrator_prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return self.story

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
