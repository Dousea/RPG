"""State questions about the end of the story, built from the engine's truth."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from data.story import check as story_check_k
from managers.context import ZOMBIE_ID, zombie_ids_to_words
from managers.game import GameManager
from modules.action.types import AnyAction
from modules.action.words import describe_action

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StateQuestion:
    """One question for the decision model, the answers the engine allows and the fact that corrects a conflict."""

    text: str
    options: tuple[tuple[str, str], ...]
    allowed: frozenset[str]
    correction: str


def build_questions(
    manager: GameManager,
    outcome_facts: list[str],
    refused_actions: Sequence[tuple[str, str]] = (),
    found_items: bool = False,
) -> list[StateQuestion]:
    """The turn's questions: the zombie's state, each refused action, and finds a story may deny.

    `outcome_facts` are raw (zombie ids not yet worded). One zombie id gives one
    question; with none or several there is none, since the narrator's "the
    zombie" would be ambiguous. `refused_actions` are the refused actions in
    words, each with the validator's reason, and `found_items` says whether a search turned anything up.
    """
    name = manager.player.appearance.forename
    questions = _zombie_questions(manager, outcome_facts)
    for raw_action, raw_reason in refused_actions:
        action = zombie_ids_to_words(raw_action)
        reason = zombie_ids_to_words(raw_reason)
        questions.append(
            StateQuestion(
                story_check_k.REFUSED_ACTION_QUESTION.format(name=name, action=action),
                story_check_k.REFUSED_ACTION_OPTIONS,
                frozenset({"no", "unclear"}),
                story_check_k.REFUSED_ACTION_FACT.format(name=name, action=action, reason=reason),
            )
        )
    if found_items:
        questions.append(
            StateQuestion(
                story_check_k.FOUND_NOTHING_QUESTION.format(name=name),
                story_check_k.FOUND_NOTHING_OPTIONS,
                frozenset({"no", "unclear"}),
                story_check_k.FOUND_ITEMS_FACT.format(name=name),
            )
        )
    return questions


def _zombie_questions(manager: GameManager, outcome_facts: list[str]) -> list[StateQuestion]:
    ids = {match for fact in outcome_facts for match in ZOMBIE_ID.findall(fact)}
    if len(ids) > 1:
        logger.debug(f"Story check skipped: {len(ids)} zombies in the facts.")
        return []
    if not ids:
        return []
    (zombie_id,) = ids
    if zombie_id in manager.world.zombies:
        allowed = frozenset({"no", "unclear"})
        correction = story_check_k.ZOMBIE_ALIVE_FACT
    else:
        allowed = frozenset({"yes", "unclear"})
        correction = story_check_k.ZOMBIE_DEAD_FACT
    return [
        StateQuestion(
            story_check_k.ZOMBIE_DEATH_QUESTION,
            story_check_k.ZOMBIE_DEATH_OPTIONS,
            allowed,
            correction,
        )
    ]


def plan_questions(manager: GameManager, actions: Sequence[AnyAction]) -> list[StateQuestion]:
    """One question per parsed action, in order: did the player ask for it?

    A conflict's correction is the refusal fact that replaces the action.
    """
    name = manager.player.appearance.forename
    questions = []
    for action in actions:
        words = zombie_ids_to_words(describe_action(action))
        questions.append(
            StateQuestion(
                story_check_k.PLAN_QUESTION.format(action=words),
                story_check_k.PLAN_OPTIONS,
                frozenset({"yes", "unclear"}),
                story_check_k.PLAN_REFUSED_FACT.format(name=name, action=words),
            )
        )
    return questions
