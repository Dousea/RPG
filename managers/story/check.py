"""State questions about the end of the story, built from the engine's truth."""

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass

from data.story import check as story_check_k
from managers.context import CORPSE_ID, ZOMBIE_ID, zombie_ids_to_words
from managers.game import GameManager
from managers.mentions import seen_by_looks
from modules.action.types import AnyAction, UnsupportedAction
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


def plan_questions(
    manager: GameManager, actions: Sequence[AnyAction], verbs: str = ""
) -> list[StateQuestion]:
    """One question per parsed action, in order: did the player ask for it?

    An `UNSUPPORTED` action is asked instead whether one of the listed `verbs`
    does it. A conflict's correction is the refusal fact that replaces the action.
    """
    name = manager.player.appearance.forename
    questions = []
    for action in actions:
        words = _action_words(manager, action)
        if isinstance(action, UnsupportedAction):
            questions.append(
                StateQuestion(
                    story_check_k.UNSUPPORTED_QUESTION.format(verbs=verbs, action=words),
                    story_check_k.UNSUPPORTED_OPTIONS,
                    frozenset({"no", "unclear"}),
                    story_check_k.PLAN_NOT_UNDERSTOOD_FACT.format(name=name),
                )
            )
            continue
        questions.append(
            StateQuestion(
                story_check_k.PLAN_QUESTION.format(action=words),
                story_check_k.PLAN_OPTIONS,
                frozenset({"yes", "unclear"}),
                story_check_k.PLAN_REFUSED_FACT.format(name=name, action=words),
            )
        )
    return questions


def _action_words(manager: GameManager, action: AnyAction) -> str:
    """The action in words with each zombie or body the player can see told by its looks, never by id.

    An id with nothing behind it any more reads as "the zombie" or "the body".
    """
    seen = seen_by_looks(manager)
    nouns = {"zombie": story_check_k.ZOMBIE_NOUN, "corpse": story_check_k.CORPSE_NOUN}

    def by_looks(match: re.Match[str]) -> str:
        if (found := seen.get(match.group())) is None:
            return match.group()
        kind, looks = found
        return story_check_k.SEEN_BY_LOOKS.format(noun=nouns[kind], looks=looks)

    text = CORPSE_ID.sub(by_looks, ZOMBIE_ID.sub(by_looks, describe_action(action)))
    return zombie_ids_to_words(text)
