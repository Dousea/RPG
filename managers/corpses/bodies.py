"""Corpses: the dead the outbreak leaves, what a kill leaves, and how bodies rot away (spec 14)."""

import logging
import math
import random
from collections.abc import Callable

from data.world.clock import MINUTES_PER_DAY, MINUTES_PER_HOUR
from data.zombies import lore as k
from managers.zombies.dress import dress
from modules.body.parts import LAYER_ORDER, BodyLocation, BodyPart
from modules.character.appearance import Gender
from modules.entity.corpse import CorpseEntity
from modules.entity.item import ItemEntity
from modules.entity.player import PlayerEntity
from modules.entity.zombie import ZombieEntity, ZombieState
from modules.item import ClothingItem, MeleeWeaponItem
from modules.world.location import Location, World

logger = logging.getLogger(__name__)

_PARTS = list(BodyPart)


def chunk_chance(per_chunk: float) -> float:
    """The chance a chunk holds a corpse when the outbreak starts."""
    return k.CORPSE_CHUNK_CHANCE_FACTOR * per_chunk


def _lerp(start: float, end: float, delta: float) -> float:
    return start + (end - start) * min(max(delta, 0.0), 1.0)


def rot_stage_at_death(days: float, rng: random.Random) -> int:
    """The rot stage of a body made `days` after the outbreak: always 1 for the first 20 days."""
    days_survived = max(int(days), 0)
    if days_survived <= k.ROT_FRESH_DAYS:
        return 1
    late = days_survived >= k.ROT_LATE_DAYS
    stage1_end = k.ROT_STAGE1_LATE if late else k.ROT_STAGE1_MID
    stage2_end = k.ROT_STAGE2_LATE if late else k.ROT_STAGE2_MID
    delta = (days_survived - k.ROT_FRESH_DAYS) / (k.ROT_MID_DAYS - k.ROT_FRESH_DAYS)
    chance1 = _lerp(k.ROT_STAGE1_START, stage1_end, delta)
    chance2 = _lerp(k.ROT_STAGE2_START, stage2_end, delta)
    roll = rng.randrange(100)
    if roll < chance1:
        return 1
    return 2 if roll < chance1 + chance2 else 3


def _new_id(world: World) -> str:
    corpse_id = f"c{world.next_corpse_number}"
    world.next_corpse_number += 1
    return corpse_id


def _days_since_outbreak(world: World, minute: int) -> float:
    started = world.outbreak_started_at if world.outbreak_started_at is not None else minute
    return (minute - started) / MINUTES_PER_DAY


def kill_corpse(
    world: World, zombie: ZombieEntity, minute: int, rng: random.Random
) -> CorpseEntity:
    """The body a killed zombie leaves where it fell, in its clothes and with its weapon."""
    contents = [*zombie.worn.values(), *zombie.carried]
    if zombie.attached is not None:
        contents.insert(len(zombie.worn), zombie.attached)
    body = CorpseEntity(
        corpse_id=_new_id(world),
        zone_id=zombie.zone_id,
        gap=zombie.gap,
        female=zombie.female,
        outfit=zombie.outfit,
        died_at=minute,
        rot_at_death=rot_stage_at_death(_days_since_outbreak(world, minute), rng),
        contents=contents,
        attached=zombie.attached,
        searched=zombie.risen_from_player,
        risen_from_player=zombie.risen_from_player,
    )
    world.corpses[body.corpse_id] = body
    return body


def add_random_holes(worn: dict[BodyLocation, ItemEntity], rng: random.Random, count: int) -> None:
    """`count` holes, each at a random part on the outermost layer covering it that has none there."""
    outer_first = sorted(worn.items(), key=lambda pair: LAYER_ORDER[pair[0]], reverse=True)
    for _ in range(count):
        part = _PARTS[rng.randrange(k.BODY_PART_COUNT)]
        for _, entity in outer_first:
            item = entity.item
            if isinstance(item, ClothingItem) and part in item.covers and part not in entity.holes:
                entity.holes.add(part)
                break


def _shell() -> ZombieEntity:
    return ZombieEntity(
        zombie_id="",
        zone_id="",
        health=0.0,
        speed_type=k.SPEED_TYPE_SHAMBLER,
        speed_mod=0.0,
        lunger=False,
        strength=k.ZOMBIE_STRENGTH,
        memory=k.ZOMBIE_MEMORY_FRAMES,
        sight=k.SENSE_NORMAL,
        hearing=k.SENSE_NORMAL,
    )


def outbreak_corpse(world: World, zone: Location, minute: int, rng: random.Random) -> CorpseEntity:
    """One body lying in `zone` when the outbreak starts: bones, or dressed with holes in its clothes."""
    body = CorpseEntity(
        corpse_id=_new_id(world),
        zone_id=zone.id,
        gap=float(rng.randint(1, zone.size_tiles)),
        female=False,
        outfit="",
        died_at=minute,
        rot_at_death=1,
    )
    if rng.randrange(k.CORPSE_SKELETON_ONE_IN) == 0:
        body.skeleton = True
    else:
        shell = _shell()
        dress(shell, rng, 0.0)
        add_random_holes(shell.worn, rng, k.CORPSE_RANDOM_HOLES)
        body.female, body.outfit = shell.female, shell.outfit
        body.contents = [
            *shell.worn.values(),
            *shell.carried,
            *([shell.attached] if shell.attached else []),
        ]
        body.attached = shell.attached
        if rng.randrange(k.CORPSE_FAKE_DEAD_ONE_IN) == 0:
            body.fake_dead = True
            body.crawling = rng.randrange(k.CORPSE_FAKE_DEAD_CRAWLER_ONE_IN) == 0
    world.corpses[body.corpse_id] = body
    return body


def scatter(
    world: World, minute: int, rng: random.Random, per_chunk: Callable[[int], float]
) -> None:
    """The bodies already lying around at the outbreak: at most one per chunk, none where the player starts."""
    for zone in world.locations.values():
        if zone.id in k.SPAWN_CLEARED_ZONE_IDS:
            continue
        chance = chunk_chance(per_chunk(zone.zombie_intensity))
        for _ in range(zone.chunks):
            if rng.random() < chance:
                outbreak_corpse(world, zone, minute, rng)


def reanimate_delay_minutes(rng: random.Random) -> float:
    """How long the player's body lies before it gets up: uniform from 0 up to a minute."""
    return rng.uniform(0.0, k.REANIMATE_DELAY_MAX_MIN) % k.REANIMATE_DELAY_MAX_MIN


def dress_as_player(
    zombie: ZombieEntity, player: PlayerEntity, now: int, rng: random.Random
) -> None:
    """Make a freshly rolled zombie the player's own body: their sex, clothes and carried things.

    It lies where the player fell until its delay is up.
    """
    zombie.risen_from_player = True
    zombie.female = player.appearance.gender == Gender.FEMALE
    zombie.outfit = ""
    zombie.worn = dict(player.worn)
    zombie.attached = None
    zombie.carried = list(player.inventory)
    zombie.gap = float(k.ATTACK_RANGE_TILES)
    zombie.state = ZombieState.IDLE
    zombie.down_until = now + math.ceil(reanimate_delay_minutes(rng))


def should_rise(corpse: CorpseEntity, gap_before: float, gap_after: float, now: int) -> bool:
    """Whether a fake-dead body gets up this minute: the player's gap to it touched 2 to 4 tiles."""
    if not corpse.fake_dead or corpse.skeleton or now - corpse.died_at < k.FAKE_DEAD_WAKEUP_MIN:
        return False
    near, far = k.FAKE_DEAD_RING_TILES
    return min(gap_before, gap_after) <= far and max(gap_before, gap_after) >= near


def dress_from_corpse(zombie: ZombieEntity, corpse: CorpseEntity) -> None:
    """The zombie that gets up wears what the body wore, keeps its weapon and holds the rest."""
    zombie.female = corpse.female
    zombie.outfit = corpse.outfit
    zombie.worn = {}
    zombie.attached = None
    zombie.carried = []
    for entity in corpse.contents:
        item = entity.item
        if isinstance(item, ClothingItem) and item.body_location not in zombie.worn:
            zombie.worn[item.body_location] = entity
        elif entity is corpse.attached and isinstance(item, MeleeWeaponItem):
            zombie.attached = entity
        else:
            zombie.carried.append(entity)
    zombie.was_fake_dead = corpse.fake_dead
    zombie.risen_from_player = corpse.risen_from_player


def age_hours(corpse: CorpseEntity, now: int) -> float:
    return (now - corpse.died_at) / MINUTES_PER_HOUR


def rot_stage(corpse: CorpseEntity, now: int) -> int:
    """The rot stage 1 to 3: it climbs a stage every 72 hours."""
    return min(
        k.ROT_STAGE_MAX, corpse.rot_at_death + int(age_hours(corpse, now) // k.ROT_STAGE_HOURS)
    )


def update(world: World, now: int, rng: random.Random) -> None:
    """One minute of rot for every body, in id order: past removal age a body goes, or turns to bones."""
    for corpse in list(world.corpses.values()):
        age = age_hours(corpse, now)
        if age < k.HOURS_FOR_CORPSE_REMOVAL:
            continue
        if corpse.skeleton:
            if age >= k.HOURS_FOR_CORPSE_REMOVAL + k.SKELETON_REMOVAL_EXTRA_HOURS:
                del world.corpses[corpse.corpse_id]
        elif rng.randrange(k.SKELETON_ROT_ONE_IN) == 0:
            corpse.skeleton = True
            corpse.contents = []
        else:
            del world.corpses[corpse.corpse_id]
