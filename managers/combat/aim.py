"""Group words in a swing's target: the zombie they pick, read from the target and from the player's input (melee)."""

import re
from collections.abc import Sequence
from dataclasses import replace

from data import melee as melee_k
from modules.action.pins import pin_of
from modules.action.types import AnyAction, AttackAction, ShoveAction

_DOWN_TARGET = re.compile(melee_k.DOWN_TARGET_PATTERN)
_DOWN_INPUT = re.compile(melee_k.DOWN_INPUT_PATTERN)


def is_plain_zombie(name: str) -> bool:
    return name.strip().casefold() in melee_k.PLAIN_ZOMBIE_WORDS


def is_down_target(name: str) -> bool:
    return _DOWN_TARGET.fullmatch(name.strip().casefold()) is not None


def aimed(actions: Sequence[AnyAction], player_input: str) -> list[AnyAction]:
    """`actions` with each plain zombie target of an attack or shove that the player's own words put on the floor written as a down target.

    A pinned target is never touched.
    """
    on_the_floor = _DOWN_INPUT.search(player_input.casefold()) is not None
    return [
        replace(action, target_name=melee_k.DOWN_TARGET)
        if on_the_floor
        and isinstance(action, AttackAction | ShoveAction)
        and pin_of(action.target_name) is None
        and is_plain_zombie(action.target_name)
        else action
        for action in actions
    ]
