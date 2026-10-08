"""The plan before it runs: which targets it leaves open, and its steps in words (llm-contract).

The check asks the validator about each action against the scene as it stands, so it
changes nothing and uses the lookups a run would. Actions after the plan's first zone
change are not checked: the scene there is not known yet.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from data.story import mentions as mention_k
from data.time_costs import MAX_PLAN_ACTIONS
from managers import naming
from managers.combat.aim import is_down_target, is_plain_zombie
from managers.combat.melee import MeleeEngine, SwingKind
from managers.game import GameManager
from managers.mentions import body_candidates, body_named, mentionables, zone_candidate
from managers.validator import (
    CORPSE_ID_PATTERN,
    Accepted,
    ActionValidator,
    Asked,
)
from managers.world import locations
from modules.action.choices import Candidate
from modules.action.parser import CORPSE_WORDS
from modules.action.pins import pin_of
from modules.action.types import AnyAction, AttackAction, MoveAction, ShoveAction
from modules.action.words import describe_action
from modules.resolution import MoveBlocked, MoveToZone, TargetZombie
from modules.world.location import Location

_ENTITY_ID = re.compile(r"\b[zc]\d+\b")
_SOMETHING = "something"


@dataclass(frozen=True)
class OpenChoice:
    """A target of the plan's action number `index` (field `attr`) that fits several things."""

    index: int
    attr: str
    candidates: tuple[Candidate, ...]


@dataclass(frozen=True)
class PlanStep:
    """One step of a plan screen: the action in words, whether it is done, the target it defaults to and the open choice it waits on."""

    text: str
    done: bool
    default: str | None
    choice: int | None


def _changes_zone(result: Accepted | Asked) -> bool:
    if isinstance(result, Asked):
        return result.action.verb == "MOVE_TO"
    resolved = result.resolved
    return isinstance(resolved, MoveToZone) or (
        isinstance(resolved, MoveBlocked) and resolved.hops > 0
    )


def open_choices(
    manager: GameManager, actions: Sequence[AnyAction], player_input: str = ""
) -> list[OpenChoice]:
    """The targets of `actions`, up to the first zone change, that fit several things in this scene.

    `player_input` is the player's words (picks as their names): a move to the one zone the
    parser picked is open too when those words only gave a kind word that fits several zones,
    and so is a body target when several bodies are perceived and those words name none.
    """
    validator = ActionValidator(manager)
    found: list[OpenChoice] = []
    for index, action in enumerate(actions[:MAX_PLAN_ACTIONS]):
        if zones := _kind_zones(manager, action, player_input):
            candidates = tuple(zone_candidate(manager, zone, True) for zone in zones)
            found.append(OpenChoice(index, "destination", candidates))
            break

        if body := _body_choice(manager, action, player_input):
            found.append(OpenChoice(index, *body))
            continue

        result = validator.validate(action)
        if isinstance(result, Asked):
            found.append(OpenChoice(index, result.attr, result.candidates))

        if _ends_the_scene(result):
            break
    return found


def _kind_zones(
    manager: GameManager, action: AnyAction, player_input: str
) -> list[Location] | None:
    if not isinstance(action, MoveAction) or pin_of(action.destination, "zone", "room"):
        return None
    target = manager.resolve_location(action.destination)
    if target is None:
        return None
    return locations.kind_choice(
        player_input, target, manager.current_location, manager.world.locations
    )


_BODY_FIELDS = {"SEARCH": "target_name", "CARRY": "corpse_name", "TAKE": "from_name"}


def _body_choice(
    manager: GameManager, action: AnyAction, player_input: str
) -> tuple[str, tuple[Candidate, ...]] | None:
    """The field and the bodies a body target leaves open: the generic body or an id the parser picked, with several perceived and none named."""
    attr = _BODY_FIELDS.get(action.verb)
    target = getattr(action, attr, None) if attr else None
    if attr is None or not isinstance(target, str) or pin_of(target, "corpse"):
        return None
    if not (
        naming.clean_name(target) in CORPSE_WORDS or CORPSE_ID_PATTERN.fullmatch(target.strip())
    ):
        return None

    candidates = body_candidates(manager)
    if len(candidates) < 2:
        return None
    chosen = ActionValidator(manager).corpse_target(target)
    if chosen is None or body_named(manager, player_input, chosen.corpse_id):
        return None
    return attr, tuple(candidates)


def _ends_the_scene(result: object) -> bool:
    return isinstance(result, Accepted | Asked) and _changes_zone(result)


def _zone_change_at(manager: GameManager, actions: Sequence[AnyAction]) -> int | None:
    validator = ActionValidator(manager)
    for index, action in enumerate(actions[:MAX_PLAN_ACTIONS]):
        if _ends_the_scene(validator.validate(action)):
            return index
    return None


def steps_in_this_scene(manager: GameManager, actions: Sequence[AnyAction]) -> int:
    """How many of `actions` run before the plan's first zone change, that change included."""
    change = _zone_change_at(manager, actions)
    return len(actions) if change is None else change + 1


def bind_choices(
    actions: Sequence[AnyAction], choices: Sequence[OpenChoice], picked: Sequence[Candidate]
) -> list[AnyAction]:
    """`actions` with each pick written into the field its open choice asks about."""
    bound = list(actions)
    for choice, pick in zip(choices, picked, strict=True):
        bound[choice.index] = replace(bound[choice.index], **{choice.attr: pick.written()})
    return bound


def _looks(manager: GameManager) -> dict[str, tuple[str, str]]:
    return {
        mention.id: (mention.name, mention.description)
        for mention in mentionables(manager)
        if mention.kind in ("zombie", "corpse")
    }


def _words(action: AnyAction, looks: Mapping[str, tuple[str, str]]) -> str:
    text = describe_action(action)
    return _ENTITY_ID.sub(lambda found: looks.get(found.group(), (_SOMETHING, ""))[0], text)


def _is_plain_zombie_target(action: AnyAction) -> bool:
    return isinstance(action, AttackAction | ShoveAction) and (
        is_plain_zombie(action.target_name) or is_down_target(action.target_name)
    )


def _nearest_zombie(manager: GameManager, action: AnyAction) -> str | None:
    """The id of the zombie a plain "the zombie" attack or shove would take, if there is one."""
    if not _is_plain_zombie_target(action):
        return None
    result = ActionValidator(manager).validate(action)
    if isinstance(result, Accepted) and isinstance(result.resolved, TargetZombie):
        return result.resolved.zombie_id
    return None


def _stomps(manager: GameManager, action: AnyAction, zombie_id: str | None) -> bool:
    """Whether `action` at `zombie_id` is a stomp: a shove, or a bare-handed attack, at a zombie on the floor."""
    if zombie_id is None:
        return False
    kind = MeleeEngine.kind_at(
        manager.player,
        manager.world.zombies[zombie_id],
        shove=isinstance(action, ShoveAction),
        now=manager.narrative.minutes,
    )
    return kind == SwingKind.STOMP


def _reaches_several(manager: GameManager, action: AnyAction, zombie_id: str) -> bool:
    """Whether the swing of `action` at `zombie_id` would hit more than that zombie."""
    hit = MeleeEngine.reach(
        manager.world,
        manager.player,
        manager.world.zombies[zombie_id],
        shove=isinstance(action, ShoveAction),
        now=manager.narrative.minutes,
    )
    return len(hit) > 1


def steps_of(
    manager: GameManager,
    done: Sequence[AnyAction],
    pending: Sequence[AnyAction],
    choices: Sequence[OpenChoice],
) -> list[PlanStep]:
    """The steps of a plan screen: what is done, then what is still to do with its default targets and open choices."""
    looks = _looks(manager)
    change = _zone_change_at(manager, pending)
    waiting = {choice.index: number for number, choice in enumerate(choices)}
    steps = [PlanStep(_words(action, looks), True, None, None) for action in done]
    for index, action in enumerate(pending[: None if change is None else change + 1]):
        text, default = _words(action, looks), None
        nearest = _nearest_zombie(manager, action)
        verb = "shove" if isinstance(action, ShoveAction) else "hit"
        if nearest in looks:
            if _stomps(manager, action, nearest):
                verb = "stomp"
            name, description = looks[nearest]
            beside = " and the ones beside it" if _reaches_several(manager, action, nearest) else ""
            text, default = f"{verb} the nearest zombie{beside}", f"{name}, {description}"
        steps.append(PlanStep(text, False, default, waiting.get(index)))
    if change is not None:
        steps.append(PlanStep(mention_k.AFTER_THE_MOVE, False, None, None))
    return steps
