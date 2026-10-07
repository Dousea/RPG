"""Zombies pounding on doors and windows: starting, the minute step and letting go (doors)."""

import random
from dataclasses import dataclass, field

from data.character import traits as trait_k
from data.items import ITEMS
from data.world import barriers as barrier_k
from data.zombies import lore as zombie_lore
from managers.world.barriers import barriers_between, blocks, d_b, sound_stress, thump
from managers.world.locations import zone_path
from managers.zombies.noise import BarrierSound, Sound
from modules.entity.barrier import BarrierEntity, BarrierKind
from modules.entity.item import ItemEntity
from modules.entity.player import PlayerEntity
from modules.entity.zombie import ZombieEntity, ZombieState
from modules.world.location import World

HUNTING = (ZombieState.CHASING, ZombieState.ATTACKING)


@dataclass
class ThumpReport:
    """What one minute of thumping did that the player or the zombies must hear of."""

    facts: list[str] = field(default_factory=list[str])
    sounds: list[BarrierSound] = field(default_factory=list[BarrierSound])
    stress: float = 0.0
    plank_broke: bool = False
    barrier_broke: bool = False


def zombie_number(zombie: ZombieEntity) -> int:
    return int(zombie.zombie_id[1:])


def thumpers_at(world: World, barrier_id: str) -> list[ZombieEntity]:
    """The zombies thumping a barrier, from either side, in id order."""
    return sorted(
        (
            z
            for z in world.zombies.values()
            if z.state == ZombieState.THUMPING and z.thump_barrier == barrier_id
        ),
        key=zombie_number,
    )


def first_blocker(world: World, start_id: str, target_id: str) -> tuple[BarrierEntity, str] | None:
    """The first blocking barrier on the way between two zones, and the side the walker is on."""
    path = zone_path(world.locations, start_id, target_id)
    if path is None:
        return None
    here = start_id
    for step in path:
        for barrier in barriers_between(world, here, step):
            if blocks(barrier):
                return barrier, here
        here = step
    return None


def stop_gap(world: World, player: PlayerEntity, barrier: BarrierEntity, side: str) -> float:
    """How close a walker on `side` gets: one tile beyond a barrier of the player's zone, else the hop boundary."""
    if of_player_zone(barrier, player):
        return d_b(world, player, barrier) + 1
    path = zone_path(world.locations, side, player.current_location_id) or []
    return len(path) * zombie_lore.HOP_TILES


def is_deaf(player: PlayerEntity) -> bool:
    return trait_k.DEAF_ID in player.traits


def of_player_zone(barrier: BarrierEntity, player: PlayerEntity) -> bool:
    return player.current_location_id in barrier.zones


def start(
    world: World,
    player: PlayerEntity,
    zombie: ZombieEntity,
    barrier: BarrierEntity,
    side: str,
    rng: random.Random,
) -> None:
    """The zombie stops at the barrier from `side` and starts pounding with a rolled animation."""
    zombie.was_chasing = zombie.state in HUNTING
    zombie.state = ZombieState.THUMPING
    zombie.thump_barrier = barrier.barrier_id
    zombie.zone_id = side
    zombie.thump_rate = barrier_k.THUMP_RATES_PER_MIN[
        rng.randrange(len(barrier_k.THUMP_RATES_PER_MIN))
    ]
    zombie.thump_carry = 0.0
    zombie.side = None
    if of_player_zone(barrier, player):
        zombie.gap = d_b(world, player, barrier) + 1


def _stop(zombie: ZombieEntity) -> None:
    zombie.thump_barrier = None
    zombie.thump_carry = 0.0
    zombie.thump_cooldown = barrier_k.THUMP_COOLDOWN_MIN


def release(world: World, player: PlayerEntity, barrier: BarrierEntity) -> frozenset[str]:
    """The way opened: every thumper lunges at a player at the barrier, or walks to where they were."""
    released = thumpers_at(world, barrier.barrier_id)
    at_it = of_player_zone(barrier, player) and player.at_barrier == barrier.barrier_id
    for zombie in released:
        _stop(zombie)
        if at_it:
            zombie.zone_id = player.current_location_id
            zombie.state = ZombieState.CHASING
            zombie.time_since_seen = 0.0
            zombie.has_chased = True
            zombie.facing_cos = 1.0
            zombie.gap = barrier_k.LUNGE_GAP
            continue
        zombie.state = ZombieState.ALERTED
        if of_player_zone(barrier, player):
            zombie.sound_gap = d_b(world, player, barrier) + 1
            continue
        path = zone_path(world.locations, zombie.zone_id, player.current_location_id)
        if path is None:
            zombie.state = ZombieState.IDLE
            zombie.sound_gap = 0.0
        else:
            zombie.sound_gap = len(path) * zombie_lore.HOP_TILES
    return frozenset(zombie.zombie_id for zombie in released)


def stop_for_sound(zombie: ZombieEntity, distance: float) -> None:
    """A thumper hears the player on its own side and turns toward the noise."""
    _stop(zombie)
    zombie.state = ZombieState.ALERTED
    zombie.sound_gap = distance


def drop_planks(world: World, side: str, rng: random.Random) -> None:
    """A broken door drops 1 or 2 planks on the side it was hit from."""
    count = rng.randint(barrier_k.BROKEN_DOOR_PLANKS_MIN, barrier_k.BROKEN_DOOR_PLANKS_MAX)
    zone = world.locations[side]
    for _ in range(count):
        zone.entities.append(ItemEntity(item=ITEMS[barrier_k.PLANK_ITEM_ID]))


def in_players_building(world: World, player: PlayerEntity, barrier: BarrierEntity) -> bool:
    """Whether a break of this barrier is the player's business: their building, or their zone outdoors."""
    here = world.locations[player.current_location_id]
    if here.building is None:
        return player.current_location_id in barrier.zones
    return any(world.locations[zone_id].building == here.building for zone_id in barrier.zones)


def break_fact(barrier: BarrierEntity) -> str:
    template = (
        barrier_k.DOOR_BREAKS_FACT
        if barrier.kind == BarrierKind.DOOR
        else barrier_k.WINDOW_BREAKS_FACT
    )
    return template.format(barrier=barrier.name)


def minute(world: World, player: PlayerEntity, rng: random.Random) -> ThumpReport:
    """Step 3a: each thumping zombie, in id order, deals its thumps for the minute."""
    report = ThumpReport()
    for zombie in sorted(world.zombies.values(), key=zombie_number):
        zombie.thump_cooldown = max(0, zombie.thump_cooldown - 1)
    for zombie in sorted(world.zombies.values(), key=zombie_number):
        if zombie.state != ZombieState.THUMPING:
            continue
        barrier = world.barriers.get(zombie.thump_barrier or "")
        if barrier is None:
            _stop(zombie)
            zombie.state = ZombieState.IDLE
            continue
        if not blocks(barrier):
            release(world, player, barrier)
            continue
        if of_player_zone(barrier, player):
            zombie.gap = d_b(world, player, barrier) + 1
        zombie.thump_carry += zombie.thump_rate
        thumps = int(zombie.thump_carry)
        zombie.thump_carry -= thumps
        for _ in range(thumps):
            _thump_once(world, player, rng, barrier, zombie, report)
            if zombie.state != ZombieState.THUMPING:
                break
    return report


def _thump_once(
    world: World,
    player: PlayerEntity,
    rng: random.Random,
    barrier: BarrierEntity,
    zombie: ZombieEntity,
    report: ThumpReport,
) -> None:
    deaf = is_deaf(player)
    ours = of_player_zone(barrier, player)
    distance = d_b(world, player, barrier)
    if ours:
        report.stress += sound_stress(distance, barrier_k.THUMP_SOUND_RADIUS, deaf=deaf)
    result = thump(barrier, zombie.zone_id, len(thumpers_at(world, barrier.barrier_id)))
    if result.plank_broke and ours:
        report.plank_broke = True
        report.facts.append(barrier_k.PLANK_BREAKS_FACT.format(barrier=barrier.name))
    if result.gave:
        _gave_way(world, player, rng, barrier, zombie.zone_id, report)
    elif not blocks(barrier):
        release(world, player, barrier)


def gave_way(
    world: World,
    player: PlayerEntity,
    rng: random.Random,
    barrier: BarrierEntity,
    side: str,
) -> ThumpReport:
    """A door broke or a window smashed from `side`: planks drop, thumpers are let go, the crash sounds."""
    report = ThumpReport()
    _gave_way(world, player, rng, barrier, side, report)
    return report


def _gave_way(
    world: World,
    player: PlayerEntity,
    rng: random.Random,
    barrier: BarrierEntity,
    side: str,
    report: ThumpReport,
) -> None:
    deaf = is_deaf(player)
    if barrier.kind == BarrierKind.DOOR:
        drop_planks(world, side, rng)
    released = release(world, player, barrier) if not blocks(barrier) else frozenset()
    report.sounds.append(
        BarrierSound(Sound(barrier_k.BREAK_SOUND_RADIUS, barrier_k.BREAK_SOUND_VOLUME), released)
    )
    if of_player_zone(barrier, player):
        report.stress += sound_stress(
            d_b(world, player, barrier), barrier_k.BREAK_SOUND_RADIUS, deaf=deaf
        )
    if in_players_building(world, player, barrier):
        report.barrier_broke = True
        report.facts.append(break_fact(barrier))
