"""Shared test helpers: an isolated save file and stubs for the slow edges."""

import random
import shutil
import tempfile
import unittest
from pathlib import Path

from adapters.llm import DeltaCallback, ParserReply
from adapters.save import files
from managers import carry
from managers.game import GameManager
from managers.simulation import SimulationCore
from managers.story.check import StateQuestion
from modules.action.types import AnyAction
from modules.body.parts import PART_WEIGHT, BodyPart
from modules.character.equipment import CharacterHoldableSlot
from modules.entity.item import ItemEntity
from modules.entity.npc import NpcEntity
from modules.entity.player import PlayerEntity
from modules.events.modifier import AffinityModifier
from modules.item import HoldableItem


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


def set_health(player: PlayerEntity, health: float) -> None:
    """Spread damage over every part evenly so overall health is `health`."""
    damage = 100.0 - health
    each = damage / sum(PART_WEIGHT.values())
    for state in player.body.values():
        state.health = 100.0 - each


def make_dying(player: PlayerEntity) -> None:
    """Leave the player one health and a bleeding neck, so the next minutes kill them."""
    set_health(player, 1.0)
    player.body[BodyPart.NECK].bleeding_time = 10.0


def npc_of(gm: GameManager, name: str) -> NpcEntity:
    """The NPC called `name`; a test that names someone who does not exist fails here."""
    npc = gm.resolve_npc(name)
    assert npc is not None, name
    return npc


def adjust_regard(gm: GameManager, npc_id: str, affection: int = 0, trust: int = 0) -> None:
    """Move how an NPC regards the player, bypassing the verbs that normally earn it."""
    relationships = gm.relationship_manager
    player_id = gm.player.entity_id
    relationships.apply_affinity_modifier(
        AffinityModifier(source_id=npc_id, target_id=player_id, amount=affection)
    )
    relationships.adjust_trust(npc_id, player_id, trust)


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
        self.searched_k: list[int] = []

    def rebuild(self, events: list[str]) -> None:
        self.rebuilt_with.append(list(events))

    def search(self, query_text: str, k: int = 2) -> list[int]:
        self.searched_for.append(query_text)
        self.searched_k.append(k)
        return list(self.next_hits)


class FakeFactChecker:
    """Stands in for FactChecker, which asks a decision model over HTTP.

    `results` scripts what each story check returns, in order, and
    `plan_results` each plan check; once spent, nothing conflicts. Every story
    check is recorded as (story, questions), with the name the story's "you"
    stands for in `player_names`, and every plan check as (input, questions).
    """

    def __init__(self):
        self.enabled = True
        self.results: list[list[str]] = []
        self.calls: list[tuple[str, list[StateQuestion]]] = []
        self.player_names: list[str] = []
        self.plan_results: list[list[int]] = []
        self.plan_calls: list[tuple[str, list[StateQuestion]]] = []

    def plan_conflicts(self, player_input: str, questions: list[StateQuestion]) -> list[int]:
        self.plan_calls.append((player_input, list(questions)))
        return self.plan_results.pop(0) if self.plan_results else []

    def conflicts(self, story: str, questions: list[StateQuestion], player_name: str) -> list[str]:
        self.calls.append((story, list(questions)))
        self.player_names.append(player_name)
        return self.results.pop(0) if self.results else []


THOUGHT = "Thinking it over."


def stream(reply: str, on_delta: DeltaCallback) -> None:
    """Hand a scripted reply to a streaming listener the way LM Studio does: a thought, then small pieces."""
    on_delta("thinking", THOUGHT)
    for start in range(0, len(reply), 8):
        on_delta("story", reply[start : start + 8])


class ScriptedLLM:
    """Replaces adapters.llm's three network calls with canned answers.

    `actions` scripts the parser call (an ACTIONS: block, or "NONE"); `story`
    scripts the narrator call (a STORY: block). Kept as two separate
    scripts because the turn loop now makes two calls, not one.
    """

    def __init__(
        self,
        actions: str = "ACTIONS:\nNONE",
        story: str = "STORY:\n...",
        summary: str = "A summary.",
        structured: bool = False,
    ):
        self.actions = actions
        self.story = story
        self.summary = summary
        self.structured = structured
        self.schemas: list[dict | None] = []
        self.prompts: list[str] = []  # parser-call prompts
        self.narrator_prompts: list[str] = []
        self.summarized: list[str] = []
        self.error: Exception | None = None
        self.parser_script: list[str | Exception] = []

    def query_parser(self, prompt: str, schema: dict | None = None) -> ParserReply:
        """Answers from `parser_script` first (an Exception is raised), then from `actions`."""
        self.prompts.append(prompt)
        self.schemas.append(schema)
        if self.parser_script:
            scripted = self.parser_script.pop(0)
            if isinstance(scripted, Exception):
                raise scripted
            return ParserReply(scripted, structured=self.structured)
        if self.error is not None:
            raise self.error
        return ParserReply(self.actions, structured=self.structured)

    def query_narrator(self, prompt: str, on_delta: DeltaCallback | None = None) -> str:
        self.narrator_prompts.append(prompt)
        if self.error is not None:
            raise self.error
        if on_delta is not None:
            stream(self.story, on_delta)
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
        self._original_save_file = files.SAVE_FILE
        # Resolved at call time by save/load/delete, so patching it here is
        # enough to redirect every default-path write.
        files.SAVE_FILE = self.save_path

    def tearDown(self):
        files.SAVE_FILE = self._original_save_file
        shutil.rmtree(self._temp_dir, ignore_errors=True)
        super().tearDown()


def simulate(gm: GameManager, *actions: AnyAction, rng: random.Random | None = None) -> list[str]:
    """Resolve actions through a fresh SimulationCore; refusals come back as facts."""
    return SimulationCore(gm, rng=rng).resolve(list(actions))


class ScriptedRandom(random.Random):
    """A `random.Random` whose `random()` and `randrange()` replay lists, then answer 0.

    `randrange` ignores its bounds: the script holds the value the test wants drawn.
    """

    def __init__(self, random: list[float] | None = None, randrange: list[int] | None = None):
        super().__init__(0)
        self._floats = list(random or [])
        self._ints = list(randrange or [])

    def random(self) -> float:
        return self._floats.pop(0) if self._floats else 0.0

    def randrange(self, start: int, stop: int | None = None, step: int = 1) -> int:
        return self._ints.pop(0) if self._ints else 0


def load_pack(player: PlayerEntity, kg: float) -> None:
    """Add dead weight loose in the pack so the player carries `kg` in all."""
    ballast = HoldableItem(
        id="item_test_ballast",
        name="Ballast",
        description="Dead weight.",
        max_hit_points=1,
        tags=[],
        slots=[CharacterHoldableSlot.RIGHT_HAND],
        is_two_handed=False,
        weight=kg - carry.carried_weight(player),
    )
    assert ballast.weight > 0
    player.inventory.append(ItemEntity(item=ballast))
