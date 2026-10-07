"""State questions about the end of the story, built from the engine's truth."""

import logging
from dataclasses import dataclass

from data import story_check as words
from managers.context import ZOMBIE_ID
from managers.game import GameManager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StateQuestion:
    """One question for the decision model, the answers the engine allows and the fact that corrects a conflict."""

    text: str
    options: tuple[tuple[str, str], ...]
    allowed: frozenset[str]
    correction: str


def build_questions(manager: GameManager, outcome_facts: list[str]) -> list[StateQuestion]:
    """The turn's questions from its raw outcome facts (zombie ids not yet worded).

    One zombie id gives one question; with none or several there is none, since
    the narrator's "the zombie" would be ambiguous.
    """
    ids = {match for fact in outcome_facts for match in ZOMBIE_ID.findall(fact)}
    if len(ids) > 1:
        logger.debug(f"Story check skipped: {len(ids)} zombies in the facts.")
        return []
    if not ids:
        return []
    (zombie_id,) = ids
    if zombie_id in manager.world.zombies:
        allowed = frozenset({"no", "unclear"})
        correction = words.ZOMBIE_ALIVE_FACT
    else:
        allowed = frozenset({"yes", "unclear"})
        correction = words.ZOMBIE_DEAD_FACT
    return [
        StateQuestion(words.ZOMBIE_DEATH_QUESTION, words.ZOMBIE_DEATH_OPTIONS, allowed, correction)
    ]
