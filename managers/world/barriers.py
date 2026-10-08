"""The rules for doors, windows and planks: blocking, vision, damage and distance (doors)."""

import random
from dataclasses import dataclass

from data.world import barriers as barrier_k
from managers import carry
from modules.entity.barrier import BarrierEntity, BarrierKind
from modules.entity.item import ItemEntity
from modules.entity.player import PlayerEntity
from modules.item import MeleeWeaponItem
from modules.world.location import World

BARRICADE = "barricade"
BARRIER = "barrier"


@dataclass(frozen=True)
class Target:
    """What a thump or a hit lands on: a side's barricade, or the door or window itself."""

    kind: str
    side: str


@dataclass(frozen=True)
class Damage:
    """What a thump or a hit did: where it landed, how much, and what gave way."""

    target: Target | None
    damage: int = 0
    plank_broke: bool = False
    gave: bool = False


def barriers_between(world: World, zone_a: str, zone_b: str) -> list[BarrierEntity]:
    """The barriers on the connection between two zones."""
    pair = frozenset((zone_a, zone_b))
    return [barrier for barrier in world.barriers.values() if barrier.joins == pair]


def barriers_of(world: World, zone_id: str) -> list[BarrierEntity]:
    """Every barrier on one of a zone's connections, in id order."""
    return [barrier for barrier in world.barriers.values() if zone_id in barrier.zones]


def find_barrier(world: World, here: str, name: str) -> BarrierEntity | None:
    """The barrier `name` points at: its id, its name or an alias, those of zone `here` first."""
    needle = name.strip().strip("\"'.,;:").casefold()
    needle = needle.removeprefix("the ").removeprefix("my ").strip()
    if not needle:
        return None
    for barrier in sorted(world.barriers.values(), key=lambda b: here not in b.zones):
        names = (barrier.barrier_id, barrier.name, *barrier.aliases)
        if needle in (n.casefold().removeprefix("the ") for n in names):
            return barrier
    return None


def blocks(barrier: BarrierEntity) -> bool:
    """Whether the barrier stops the way: a plank anywhere, or a closed door or window that is whole."""
    if barrier.total_planks:
        return True
    return not barrier.broken and not barrier.open


def connection_blocked(world: World, zone_a: str, zone_b: str) -> bool:
    return any(blocks(barrier) for barrier in barriers_between(world, zone_a, zone_b))


def state_word(barrier: BarrierEntity) -> str:
    """A barrier's state in words: open, closed (and locked), broken or smashed."""
    if barrier.broken:
        return "broken" if barrier.kind == BarrierKind.DOOR else "smashed"
    if barrier.open:
        return "open"
    return "closed, locked" if barrier.locked else "closed"


def can_see_through(barrier: BarrierEntity) -> bool:
    """Whether a zombie on one side sees the other: not past a closed door or three planks."""
    if any(
        len(planks) >= barrier_k.SIGHT_BLOCKING_PLANKS for planks in barrier.barricades.values()
    ):
        return False
    if barrier.kind == BarrierKind.DOOR:
        return barrier.open or barrier.broken
    return True


def thumpable_for(barrier: BarrierEntity, side: str) -> Target | None:
    """The first thing a thump or a hit from `side` lands on, or None when there is nothing."""
    near = Target(BARRICADE, side) if barrier.plank_count(side) else None
    far_side = barrier.far_side(side)
    far = Target(BARRICADE, far_side) if barrier.plank_count(far_side) else None
    itself = Target(BARRIER, side) if not barrier.broken and not barrier.open else None
    order = (near, itself, far) if barrier.kind == BarrierKind.WINDOW else (near, far, itself)
    return next((target for target in order if target is not None), None)


def _hurt(barrier: BarrierEntity, target: Target, amount: int) -> Damage:
    if target.kind == BARRICADE:
        planks = barrier.barricades[target.side]
        planks[-1] = max(0, planks[-1] - amount)
        broke = planks[-1] == 0
        if broke:
            planks.pop()
        return Damage(target, amount, plank_broke=broke)
    barrier.health = max(0, barrier.health - amount)
    gave = barrier.health == 0
    if gave:
        barrier.broken = True
    return Damage(target, amount, gave=gave)


def thump(barrier: BarrierEntity, side: str, thumpers: int) -> Damage:
    """One thump from `side` with `thumpers` zombies at the barrier."""
    target = thumpable_for(barrier, side)
    if target is None:
        return Damage(None)
    if (
        target.kind == BARRIER
        and barrier.kind == BarrierKind.DOOR
        and thumpers < barrier_k.THUMPERS_TO_BREAK_DOOR
    ):
        return Damage(target)
    return _hurt(barrier, target, barrier_k.THUMP_STRENGTH)


def door_damage(weapon: MeleeWeaponItem | None, sharpness_mult: float = 1.0) -> int:
    """A weapon's damage to doors; bare hands do none, any weapon at least 1."""
    if weapon is None or weapon.door_damage <= 0:
        return 0
    return max(1, int(weapon.door_damage * sharpness_mult))


def strength_factor(strength: int) -> float:
    return barrier_k.DOOR_DAMAGE_STRENGTH_MULT[strength]


def weapon_hit(
    barrier: BarrierEntity, side: str, damage: int, strength: int, rng: random.Random
) -> Damage:
    """One hit with a weapon of `damage` door damage from `side`; a window smashes whatever hits it."""
    target = thumpable_for(barrier, side)
    if target is None:
        return Damage(None)
    if target.kind == BARRICADE:
        return _hurt(barrier, target, damage * barrier_k.BARRICADE_HIT_MULT)
    if barrier.kind == BarrierKind.WINDOW:
        return _hurt(barrier, target, barrier.health)
    factor = strength_factor(strength)
    amount = int(damage * barrier_k.DOOR_HIT_MULT * factor)
    if rng.randrange(barrier_k.DOOR_HIT_EXTRA_ONE_IN) == 0:
        amount += int(damage * barrier_k.DOOR_HIT_EXTRA_MULT * factor)
    return _hurt(barrier, target, amount)


def plank_health(condition: int, condition_max: int, carpentry: int) -> int:
    """The health of a plank nailed up at a Carpentry level."""
    base = int(condition / condition_max * barrier_k.PLANK_BASE_HEALTH)
    # The epsilon keeps float error from truncating 300 x 1.14 to 341 instead of 342.
    return int(base * barrier_k.BARRICADE_MOD_BY_CARPENTRY[carpentry] + 1e-9)


def plank_condition(health: int, condition_max: int) -> int:
    """The condition a pried-off plank comes back with, never below 1."""
    share = min(health / barrier_k.PLANK_BASE_HEALTH, 1)
    return int(max(condition_max * share, 1))


def hammer_mod(carpentry: int) -> float:
    return barrier_k.HAMMER_MOD_BY_CARPENTRY[carpentry]


def sound_stress(distance: float, radius: float, *, deaf: bool) -> float:
    """The stress one barrier sound adds over its life to a player `distance` tiles from it."""
    if deaf or distance >= radius:
        return 0.0
    return barrier_k.STRESS_PER_BARRIER_SOUND * (1 - distance / radius)


def d_b(world: World, player: PlayerEntity, barrier: BarrierEntity) -> float:
    """The player's distance to a barrier of their zone: 1 at that barrier, else half the zone."""
    if player.at_barrier == barrier.barrier_id:
        return barrier_k.PLAYER_AT_BARRIER_DISTANCE
    return world.locations[player.current_location_id].size_tiles / 2


def carried_entities(player: PlayerEntity) -> list[ItemEntity]:
    """Everything the player has on them: the pack and its bags, then what is in their hands."""
    held = [e for e in player.equipment.values() if e is not None]
    return [*carry.carried_items(player), *[e for i, e in enumerate(held) if e not in held[:i]]]
