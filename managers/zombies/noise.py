"""The sounds the player makes, and the skill modifiers that quiet them (spec 09)."""

import math
from dataclasses import dataclass

from data.character import skills as skill_k
from data.character import traits as trait_k
from data.world import barriers as barrier_k
from data.zombies import lore as k
from managers.character.skills import skill_levels
from managers.world.barriers import hammer_mod
from modules.body.parts import BodyLocation
from modules.entity.player import PlayerEntity
from modules.world.pace import Pace


@dataclass(frozen=True)
class Sound:
    """A noise with a radius and a volume, both in tiles."""

    radius: float
    volume: float


@dataclass(frozen=True)
class BarrierSound:
    """A sound a door, window or plank makes; the zombies in `ignored` stand too close to react (spec 13)."""

    sound: Sound
    ignored: frozenset[str] = frozenset()


def perk_level(player: PlayerEntity, skill_id: str) -> int:
    return max(0, min(skill_k.MAX_LEVEL, skill_levels(player).get(skill_id, 0)))


def lightfoot_mod(level: int) -> float:
    return k.LIGHTFOOT_MOD[level]


def nimble_mod(level: int) -> float:
    return k.NIMBLE_MOD[level]


def sneak_spot_mod(level: int) -> float:
    """How much the Sneaking level quiets and hides the player, as a factor."""
    return k.SNEAK_SPOT_BASE[level] * k.SNEAK_SPOT_FACTOR


def footstep_sound(player: PlayerEntity, pace: Pace, *, indoors: bool) -> Sound:
    """The sound one footstep makes at a pace; its volume equals its radius."""
    volume = k.FOOTSTEP_PACE_SPEED[pace] * k.FOOTSTEP_VOLUME_FACTOR
    if trait_k.GRACEFUL_ID in player.traits:
        volume *= k.GRACEFUL_VOLUME_FACTOR
    if trait_k.CLUMSY_ID in player.traits:
        volume *= k.CLUMSY_VOLUME_FACTOR
    if BodyLocation.SHOES not in player.worn:
        volume *= k.BAREFOOT_VOLUME_FACTOR
    volume *= lightfoot_mod(perk_level(player, skill_k.LIGHTFOOTED))
    volume *= 2 - nimble_mod(perk_level(player, skill_k.NIMBLE))
    if pace == Pace.SNEAK:
        volume *= sneak_spot_mod(perk_level(player, skill_k.SNEAKING))
    radius = math.ceil(round(volume * k.RADIUS_PER_VOLUME, 6))
    if indoors:
        radius = math.floor(radius * k.INDOORS_RADIUS_FACTOR)
    if pace == Pace.SNEAK:
        radius = max(1, radius)
    return Sound(radius=radius, volume=radius)


def footstep_emit_chance(player: PlayerEntity, pace: Pace) -> float:
    """The chance a moving minute makes at least one audible footstep."""
    odds = k.STEP_EMIT_ODDS
    if pace == Pace.SNEAK:
        odds = min(
            k.SNEAK_STEP_ODDS_CAP,
            k.SNEAK_STEP_ODDS_BASE + perk_level(player, skill_k.LIGHTFOOTED),
        )
    return 1 - (1 - 1 / odds) ** k.STEPS_PER_MOVING_MINUTE


def cough_sound() -> Sound:
    return Sound(radius=k.COUGH_RADIUS, volume=k.COUGH_VOLUME)


def hammer_sound(carpentry: int) -> Sound:
    """The one sound a plank being nailed on makes; Carpentry quiets it (spec 13)."""
    radius = math.ceil(round(barrier_k.HAMMER_SOUND_RADIUS_BASE * hammer_mod(carpentry), 6))
    return Sound(radius=radius, volume=radius)


def pry_sound() -> Sound:
    return Sound(radius=barrier_k.PRY_SOUND_RADIUS, volume=barrier_k.PRY_SOUND_VOLUME)


def barrier_hit_sound() -> Sound:
    return Sound(radius=barrier_k.HIT_SOUND_RADIUS, volume=barrier_k.HIT_SOUND_VOLUME)
