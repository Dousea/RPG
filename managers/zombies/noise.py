"""The sounds the player makes, and the skill modifiers that quiet them (spec 09)."""

import math
from dataclasses import dataclass

from data.character import skills as skill_k
from data.character import traits as trait_k
from data.world import barriers as barrier_k
from data.zombies import lore as zombie_lore
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
    return zombie_lore.LIGHTFOOT_MOD[level]


def nimble_mod(level: int) -> float:
    return zombie_lore.NIMBLE_MOD[level]


def sneak_spot_mod(level: int) -> float:
    """How much the Sneaking level quiets and hides the player, as a factor."""
    return zombie_lore.SNEAK_SPOT_BASE[level] * zombie_lore.SNEAK_SPOT_FACTOR


def footstep_sound(player: PlayerEntity, pace: Pace, *, indoors: bool) -> Sound:
    """The sound one footstep makes at a pace; its volume equals its radius."""
    volume = zombie_lore.FOOTSTEP_PACE_SPEED[pace] * zombie_lore.FOOTSTEP_VOLUME_FACTOR
    if trait_k.GRACEFUL_ID in player.traits:
        volume *= zombie_lore.GRACEFUL_VOLUME_FACTOR
    if trait_k.CLUMSY_ID in player.traits:
        volume *= zombie_lore.CLUMSY_VOLUME_FACTOR
    if BodyLocation.SHOES not in player.worn:
        volume *= zombie_lore.BAREFOOT_VOLUME_FACTOR
    volume *= lightfoot_mod(perk_level(player, skill_k.LIGHTFOOTED))
    volume *= 2 - nimble_mod(perk_level(player, skill_k.NIMBLE))
    if pace == Pace.SNEAK:
        volume *= sneak_spot_mod(perk_level(player, skill_k.SNEAKING))
    radius = math.ceil(round(volume * zombie_lore.RADIUS_PER_VOLUME, 6))
    if indoors:
        radius = math.floor(radius * zombie_lore.INDOORS_RADIUS_FACTOR)
    if pace == Pace.SNEAK:
        radius = max(1, radius)
    return Sound(radius=radius, volume=radius)


def footstep_emit_chance(player: PlayerEntity, pace: Pace) -> float:
    """The chance a moving minute makes at least one audible footstep."""
    odds = zombie_lore.STEP_EMIT_ODDS
    if pace == Pace.SNEAK:
        odds = min(
            zombie_lore.SNEAK_STEP_ODDS_CAP,
            zombie_lore.SNEAK_STEP_ODDS_BASE + perk_level(player, skill_k.LIGHTFOOTED),
        )
    return 1 - (1 - 1 / odds) ** zombie_lore.STEPS_PER_MOVING_MINUTE


def cough_sound() -> Sound:
    return Sound(radius=zombie_lore.COUGH_RADIUS, volume=zombie_lore.COUGH_VOLUME)


def hammer_sound(carpentry: int) -> Sound:
    """The one sound a plank being nailed on makes; Carpentry quiets it (spec 13)."""
    radius = math.ceil(round(barrier_k.HAMMER_SOUND_RADIUS_BASE * hammer_mod(carpentry), 6))
    return Sound(radius=radius, volume=radius)


def pry_sound() -> Sound:
    return Sound(radius=barrier_k.PRY_SOUND_RADIUS, volume=barrier_k.PRY_SOUND_VOLUME)


def barrier_hit_sound() -> Sound:
    return Sound(radius=barrier_k.HIT_SOUND_RADIUS, volume=barrier_k.HIT_SOUND_VOLUME)
