"""Zombies: rolling, population and the minute loop (spec 09)."""

import math
import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from data import skills as skill_k
from data import traits as trait_k
from data import zombie_lore as k
from data.clock import MINUTES_PER_DAY, MINUTES_PER_HOUR
from managers.body import kill, limp_factor
from managers.game import GameManager
from managers.locations import zone_path
from managers.melee import MeleeEngine
from managers.noise import Sound, footstep_emit_chance, footstep_sound, perk_level, sneak_spot_mod
from managers.skills import SkillEngine
from managers.zombie_attack import AttackOutcome, resolve_attack
from modules.entity.object import DoorEntity, UnlockableEntityLockState
from modules.entity.player import PlayerEntity
from modules.entity.zombie import AttackSide, ZombieEntity, ZombieState
from modules.item import ClothingItem
from modules.location import Location, World
from modules.pace import Pace
from modules.stats import CharacterStat
from modules.weather import WeatherSample


def per_chunk(zombie_intensity: int) -> float:
    """Zombies per 8x8-tile chunk for a 0-255 zone intensity."""
    return k.PER_CHUNK_BASE + k.PER_CHUNK_SCALE * (
        zombie_intensity * k.INTENSITY_HALF_FACTOR / k.INTENSITY_MAX
    )


def population_curve(days: float) -> float:
    """The population multiplier `days` after the outbreak: linear to the peak day, then flat."""
    span = k.POPULATION_PEAK_MULTIPLIER - k.POPULATION_START_MULTIPLIER
    progress = min(max(days, 0.0) / k.POPULATION_PEAK_DAY, 1.0)
    return k.POPULATION_START_MULTIPLIER + span * progress


def roll_zombie(rng: random.Random, zombie_id: str, zone_id: str) -> ZombieEntity:
    """One zombie as it is rolled at the outbreak: health, gait, sight and hearing."""
    health = rng.uniform(k.HEALTH_BASE_MIN, k.HEALTH_BASE_MAX) + rng.uniform(
        0.0, k.HEALTH_BONUS_MAX
    )
    fast = rng.random() < 0.5
    lunger = fast and rng.random() < k.FAST_SHAMBLER_LUNGER_CHANCE
    base = k.LUNGER_SPEED_MOD_BASE if lunger else k.SHAMBLER_SPEED_MOD_BASE
    speed_mod = base + rng.randrange(k.SPEED_MOD_STEPS) / k.SPEED_MOD_DIVISOR
    return ZombieEntity(
        zombie_id=zombie_id,
        zone_id=zone_id,
        health=health,
        speed_type=k.SPEED_TYPE_FAST_SHAMBLER if fast else k.SPEED_TYPE_SHAMBLER,
        speed_mod=speed_mod,
        lunger=lunger,
        strength=k.ZOMBIE_STRENGTH,
        memory=k.ZOMBIE_MEMORY_FRAMES,
        sight=rng.choice((k.SENSE_NORMAL, k.SENSE_POOR)),
        hearing=rng.choice((k.SENSE_NORMAL, k.SENSE_POOR)),
    )


def stochastic_round(value: float, rng: random.Random) -> int:
    """Round down, plus one with the fractional part as its chance."""
    whole = math.floor(value)
    return whole + (1 if rng.random() < value - whole else 0)


def zone_target(zone: Location, days: float) -> float:
    """The zombie count a zone aims for `days` after the outbreak, before rounding."""
    return (
        zone.chunks
        * per_chunk(zone.zombie_intensity)
        * k.POPULATION_MULTIPLIER
        * population_curve(days)
    )


def connection_blocked(world: World, zone_a: str, zone_b: str) -> bool:
    """Whether a closed door stands on the connection between two zones."""
    for here, there in ((zone_a, zone_b), (zone_b, zone_a)):
        for entity in world.locations[here].entities:
            if (
                isinstance(entity, DoorEntity)
                and entity.leads_to == there
                and entity.state == UnlockableEntityLockState.LOCKED
            ):
                return True
    return False


def place_in_zone(zombie: ZombieEntity, zone: Location, rng: random.Random) -> None:
    """Give a zombie that shares the player's zone a gap and a facing."""
    zombie.gap = float(rng.randint(1, zone.size_tiles))
    zombie.facing_cos = rng.uniform(-1.0, 1.0)


def _spawn(world: World, zone_id: str, player_zone_id: str, rng: random.Random) -> ZombieEntity:
    zombie_id = f"z{world.next_zombie_number}"
    world.next_zombie_number += 1
    zombie = roll_zombie(rng, zombie_id, zone_id)
    if zone_id == player_zone_id:
        place_in_zone(zombie, world.locations[zone_id], rng)
    world.zombies[zombie_id] = zombie
    return zombie


def start_outbreak(world: World, minute: int, player_zone_id: str, rng: random.Random) -> None:
    """The dead start walking: stamp the minute and fill every zone to its target."""
    world.outbreak_started_at = minute
    world.last_redistribution_minute = minute
    for zone in world.locations.values():
        if zone.id in k.SPAWN_CLEARED_ZONE_IDS:
            continue
        for _ in range(stochastic_round(zone_target(zone, 0), rng)):
            _spawn(world, zone.id, player_zone_id, rng)


def kill_zombie(world: World, zombie_id: str) -> None:
    """Remove a dead zombie for good; its zone does not repopulate over it."""
    zombie = world.zombies.pop(zombie_id)
    world.zombie_kills[zombie.zone_id] = world.zombie_kills.get(zombie.zone_id, 0) + 1


def _zone_counts(world: World) -> dict[str, int]:
    counts = {zone_id: 0 for zone_id in world.locations}
    for zombie in world.zombies.values():
        counts[zombie.zone_id] += 1
    return counts


def redistribute(world: World, minute: int, player_zone_id: str, rng: random.Random) -> None:
    """Move idle zombies one hop toward zones below target, then top up what is left.

    Zones go in map order and idle zombies in id order, so a seeded run replays.
    """
    if world.outbreak_started_at is None:
        return
    days = (minute - world.outbreak_started_at) / MINUTES_PER_DAY
    zones = list(world.locations.values())
    targets = {zone.id: stochastic_round(zone_target(zone, days), rng) for zone in zones}
    counts = _zone_counts(world)
    moved: set[str] = set()
    for zone in zones:
        idle = sorted(
            (
                z
                for z in world.zombies.values()
                if z.zone_id == zone.id and z.state == ZombieState.IDLE
            ),
            key=lambda z: int(z.zombie_id[1:]),
        )
        for zombie in idle:
            if counts[zone.id] <= targets[zone.id]:
                break
            if zombie.zombie_id in moved:
                continue
            destination = _neediest_neighbour(world, zone, targets, counts)
            if destination is None:
                continue
            counts[zone.id] -= 1
            counts[destination.id] += 1
            zombie.zone_id = destination.id
            moved.add(zombie.zombie_id)
            if destination.id == player_zone_id:
                place_in_zone(zombie, destination, rng)
    for zone in zones:
        if all(connection_blocked(world, zone.id, other) for other in zone.connections.values()):
            continue
        kills = world.zombie_kills.get(zone.id, 0)
        while counts[zone.id] + kills < targets[zone.id]:
            _spawn(world, zone.id, player_zone_id, rng)
            counts[zone.id] += 1


def _neediest_neighbour(
    world: World, zone: Location, targets: dict[str, int], counts: dict[str, int]
) -> Location | None:
    best: Location | None = None
    best_deficit = 0
    for other in world.locations.values():
        if other.id not in zone.connections.values() or connection_blocked(
            world, zone.id, other.id
        ):
            continue
        deficit = targets[other.id] - counts[other.id]
        if deficit > best_deficit:
            best, best_deficit = other, deficit
    return best


def redistribution_due(world: World, minute: int) -> bool:
    """Whether 12 game hours have passed since the zombies were last redistributed."""
    if world.last_redistribution_minute is None:
        return False
    interval = k.REDISTRIBUTE_HOURS * MINUTES_PER_HOUR
    return minute - world.last_redistribution_minute >= interval


def sound_attract(
    zombie: ZombieEntity,
    sound: Sound,
    distance: float,
    other_zone: bool,
    indoor_mismatch: bool,
    sample: WeatherSample,
) -> float:
    """How strongly a sound draws a zombie `distance` tiles away; 0 when it is not heard."""
    radius = sound.radius
    if zombie.poor_hearing:
        radius *= k.HEARING_POOR_FACTOR
    radius *= (
        1
        - k.HEARING_RAIN_FACTOR * sample.precipitation_intensity
        - k.HEARING_FOG_FACTOR * sample.fog_intensity
    )
    if radius <= 0 or distance > radius:
        return 0.0
    delta = distance**2 / radius**2
    if other_zone:
        delta *= k.HEARING_OTHER_ZONE_FACTOR
    if indoor_mismatch:
        delta *= k.HEARING_INDOOR_MISMATCH_FACTOR
    return sound.volume * min(max(1 - delta, 0.0), 1.0)


def hears(
    zombie: ZombieEntity,
    sound: Sound,
    distance: float,
    other_zone: bool,
    indoor_mismatch: bool,
    sample: WeatherSample,
) -> bool:
    """Whether a zombie `distance` tiles from a sound hears it."""
    return sound_attract(zombie, sound, distance, other_zone, indoor_mismatch, sample) > 0


@dataclass(frozen=True)
class SpotChance:
    """A zombie's chance to see the player: the raw figure, per frame and per game minute."""

    raw: float
    per_frame: float
    per_minute: float


def light_level(indoors: bool, power_on: bool, daylight: float) -> float:
    """How well the player can be seen where they stand, 0 to 1."""
    if not indoors:
        return daylight
    return 1.0 if power_on else k.UNLIT_INDOOR_LIGHT * daylight


def vision_radius(zombie: ZombieEntity, light: float, sample: WeatherSample) -> float:
    """How far in tiles a zombie sees; the clamp comes after the sight factor."""
    lost = max(
        (1 - light) * k.VISION_DARK_TILES,
        sample.precipitation_intensity * k.VISION_RAIN_TILES
        + sample.fog_intensity * k.VISION_FOG_TILES,
    )
    radius = k.VISION_RADIUS - lost
    if zombie.poor_sight:
        radius *= k.VISION_POOR_FACTOR
    return min(max(radius, k.VISION_RADIUS_MIN), k.VISION_RADIUS_MAX)


def facing_factor(facing_cos: float) -> float:
    for limit, factor in k.FACING_BELOW:
        if facing_cos < limit:
            return factor
    for limit, factor in k.FACING_UP_TO:
        if facing_cos <= limit:
            return factor
    return k.FACING_ABOVE_FACTOR


def spot_chance(
    zombie: ZombieEntity,
    player: PlayerEntity,
    sample: WeatherSample,
    light: float,
    pace: Pace,
) -> SpotChance:
    """Whether a zombie notices the player this frame, and so this minute."""
    raw = 100 * light
    if zombie.gap > vision_radius(zombie, light, sample):
        raw = 0.0
    raw *= facing_factor(zombie.facing_cos)
    raw *= k.PACE_MOVEMENT_MOD[pace]
    if zombie.gap < k.SPOT_NEAR_TILES and not player.sneaking:
        raw *= k.SPOT_NEAR_FACTOR
    if player.sneaking:
        raw *= sneak_spot_mod(perk_level(player, skill_k.SNEAKING))
    if zombie.bonus_spot_time > 0:
        raw *= k.SPOT_BONUS_FACTOR
    if zombie.poor_sight:
        raw *= k.SPOT_POOR_SIGHT_FACTOR
    if trait_k.INCONSPICUOUS_ID in player.traits:
        raw *= k.INCONSPICUOUS_SPOT_FACTOR
    if trait_k.CONSPICUOUS_ID in player.traits:
        raw *= k.CONSPICUOUS_SPOT_FACTOR
    per_frame = min(math.floor(raw), k.SPOT_CAP) / k.SPOT_CAP
    return SpotChance(raw, per_frame, 1 - (1 - per_frame) ** k.FRAMES_PER_MINUTE)


def detection_range(player: PlayerEntity) -> float:
    """How far in tiles the player hears a zombie."""
    reach = k.HEARING_RANGE_DEAF if trait_k.DEAF_ID in player.traits else k.HEARING_RANGE_BASE
    if trait_k.KEEN_HEARING_ID in player.traits:
        reach += k.HEARING_RANGE_KEEN
    if trait_k.HARD_OF_HEARING_ID in player.traits:
        reach -= k.HEARING_RANGE_HARD
    muffling = 1.0
    for entity in player.worn.values():
        if isinstance(entity.item, ClothingItem) and entity.item.hearing_modifier > 0:
            muffling *= entity.item.hearing_modifier
    reach = k.HEARING_RANGE_FLOOR + (max(reach, k.HEARING_RANGE_FLOOR) - k.HEARING_RANGE_FLOOR) * (
        muffling
    )
    stats = player.stats
    return (
        reach
        - stats.get(CharacterStat.FATIGUE)
        - stats.get(CharacterStat.INTOXICATION) * k.HEARING_RANGE_INTOXICATION_PER_POINT
    )


@dataclass(frozen=True)
class Perception:
    """A zombie in the player's zone and how the player senses it."""

    zombie: ZombieEntity
    seen: bool
    heard: bool


def perceived_zombies(world: World, player: PlayerEntity, light: float) -> list[Perception]:
    """The zombies in the player's zone that the player can see or hear, in id order."""
    sight = k.SIGHT_RANGE * max(k.SIGHT_RANGE_MIN_LIGHT, light)
    hearing = detection_range(player)
    result: list[Perception] = []
    for zombie in _by_id(world.zombies.values()):
        if zombie.zone_id != player.current_location_id:
            continue
        seen = zombie.gap <= sight
        heard = zombie.gap <= hearing
        if seen or heard:
            result.append(Perception(zombie, seen, heard))
    return result


def perceived_now(manager: GameManager) -> list[Perception]:
    """The zombies the player perceives right now, from the game's own clock and light."""
    world = manager.world
    if world.outbreak_started_at is None:
        return []
    sample = manager.climate.sample(manager.narrative.minutes)
    light = light_level(manager.current_location.indoors, world.power_on, sample.daylight)
    return perceived_zombies(world, manager.player, light)


def _by_id(zombies: Iterable[ZombieEntity]) -> list[ZombieEntity]:
    return sorted(zombies, key=lambda z: int(z.zombie_id[1:]))


def chase_speed(zombie: ZombieEntity) -> float:
    """Tiles per game minute a zombie closes on its target."""
    distance_factor = min(
        max(zombie.gap / k.CHASE_GAP_DIVISOR, k.CHASE_GAP_FACTOR_MIN), k.CHASE_GAP_FACTOR_MAX
    )
    return k.CHASE_SPEED_TILES_PER_MIN * zombie.speed_mod * distance_factor


def approach_minutes(gap: float, speed_factor: float = 1.0) -> int:
    """Minutes the player needs to walk up to a zombie `gap` tiles away; a limp slows the walk."""
    walk = k.WALK_APPROACH_TILES_PER_MIN * speed_factor
    return max(0, math.ceil((gap - k.ATTACK_RANGE_TILES) / walk))


_HUNTING = (ZombieState.CHASING, ZombieState.ATTACKING)


def enter_zone(world: World, zone_id: str, previous_zone_id: str, rng: random.Random) -> None:
    """The player arrives in a zone: zombies there that are not hunting get a gap and a facing.

    Chasers belong to the new zone while they are within its size, otherwise to the zone just left.
    A zombie alerted in the zone just left walks to the sound and idles there.
    """
    zone = world.locations[zone_id]
    for zombie in _by_id(world.zombies.values()):
        if zombie.state in _HUNTING:
            if zombie.gap <= zone.size_tiles:
                zombie.zone_id = zone_id
            elif zombie.zone_id == zone_id:
                zombie.zone_id = previous_zone_id
        elif zombie.zone_id == zone_id:
            place_in_zone(zombie, zone, rng)
        elif zombie.state == ZombieState.ALERTED and zombie.zone_id == previous_zone_id:
            zombie.state = ZombieState.IDLE
            zombie.sound_gap = 0.0


def path_blocked(world: World, start_id: str, target_id: str) -> bool:
    """Whether a closed door stands anywhere on the way between two zones."""
    path = zone_path(world.locations, start_id, target_id)
    if path is None:
        return True
    here = start_id
    for step in path:
        if connection_blocked(world, here, step):
            return True
        here = step
    return False


@dataclass
class PlayerMinute:
    """What the player is doing for one minute of the loop."""

    pace: Pace = Pace.STILL
    asleep: bool = False
    approach_target: str | None = None
    swing_target: str | None = None
    shove: bool = False


@dataclass
class MinuteReport:
    """What one minute of the loop did: facts, newly visible zombies and what stops the action."""

    facts: list[str] = field(default_factory=list[str])
    interrupted: bool = False
    interruption_fact: str = ""
    new_seen: int = 0
    attacked: bool = False
    death_fact: str = ""


class ZombieLoop:
    """Runs the zombie minute loop for a game (spec 09, The minute loop)."""

    def __init__(self, manager: GameManager, rng: random.Random, skills: SkillEngine) -> None:
        self._manager = manager
        self._rng = rng
        self._skills = skills
        self._melee = MeleeEngine(rng, skills)
        self._visible: set[str] | None = None

    def forget_visible(self) -> None:
        """Count every zombie now in view as newly seen at the next minute."""
        self._visible = set()

    def active(self) -> bool:
        return self._manager.world.outbreak_started_at is not None

    def run_minute(
        self, now: int, minute: PlayerMinute, extra_sounds: Sequence[Sound] = ()
    ) -> MinuteReport:
        """One game minute starting at clock minute `now`, steps 1 to 7 in order."""
        report = MinuteReport()
        if not self.active():
            return report
        manager = self._manager
        world = manager.world
        zone = manager.current_location
        sample = manager.climate.sample(now)
        light = light_level(zone.indoors, world.power_on, sample.daylight)
        if self._visible is None:
            self._visible = self._visible_ids(light)
        self._redistribute_if_due(now)
        swing_sounds = self._swing(now, minute, report)
        self._hear(minute, [*extra_sounds, *swing_sounds], sample)
        self._move(now, minute)
        spotted = self._spot(minute, sample, light, report)
        self._remember()
        reached = self._report_reach(minute)
        self._attack(now, minute, report)
        self._clear_staggered()
        if spotted:
            report.interrupted = True
            report.interruption_fact = k.SPOTTED_FACT
        if reached:
            report.interrupted = True
            report.interruption_fact = k.REACHED_FACT
        self._visible, new = self._diff_visible(light)
        report.new_seen = new
        return report

    def _swing(self, now: int, minute: PlayerMinute, report: MinuteReport) -> list[Sound]:
        """Step 0: the player's swing connects; returns the sounds its hits make."""
        manager = self._manager
        world = manager.world
        if minute.swing_target not in world.zombies:
            return []
        result = self._melee.swing(
            manager.player, world, now, minute.swing_target, shove=minute.shove
        )
        for zombie_id in result.killed:
            kill_zombie(world, zombie_id)
        report.facts.extend(result.facts)
        return result.sounds

    def _visible_ids(self, light: float) -> set[str]:
        manager = self._manager
        return {p.zombie.zombie_id for p in perceived_zombies(manager.world, manager.player, light)}

    def _diff_visible(self, light: float) -> tuple[set[str], int]:
        now_visible = self._visible_ids(light)
        return now_visible, len(now_visible - (self._visible or set()))

    def _redistribute_if_due(self, now: int) -> None:
        world = self._manager.world
        while redistribution_due(world, now):
            assert world.last_redistribution_minute is not None
            world.last_redistribution_minute += k.REDISTRIBUTE_HOURS * MINUTES_PER_HOUR
            redistribute(
                world,
                world.last_redistribution_minute,
                self._manager.player.current_location_id,
                self._rng,
            )

    def _distance_to_player(self, zombie: ZombieEntity) -> float | None:
        manager = self._manager
        if zombie.zone_id == manager.player.current_location_id:
            return zombie.gap
        path = zone_path(
            manager.world.locations, zombie.zone_id, manager.player.current_location_id
        )
        return None if path is None else len(path) * k.HOP_TILES

    def _hear(self, minute: PlayerMinute, extra: Sequence[Sound], sample: WeatherSample) -> None:
        manager = self._manager
        player, world = manager.player, manager.world
        zone = manager.current_location
        sounds = list(extra)
        walking = minute.pace != Pace.STILL and not minute.asleep
        if walking and self._rng.random() < footstep_emit_chance(player, minute.pace):
            sounds.append(footstep_sound(player, minute.pace, indoors=zone.indoors))
        if not sounds:
            return
        for zombie in _by_id(world.zombies.values()):
            if zombie.state not in (ZombieState.IDLE, ZombieState.ALERTED):
                continue
            distance = self._distance_to_player(zombie)
            if distance is None:
                continue
            other_zone = zombie.zone_id != player.current_location_id
            mismatch = world.locations[zombie.zone_id].indoors != zone.indoors
            loudest = max(
                (
                    sound_attract(zombie, sound, distance, other_zone, mismatch, sample)
                    for sound in sounds
                ),
                default=0.0,
            )
            if loudest > 0:
                zombie.state = ZombieState.ALERTED
                zombie.sound_gap = distance

    def _move(self, now: int, minute: PlayerMinute) -> None:
        manager = self._manager
        world, player = manager.world, manager.player
        player_zone = player.current_location_id
        size = world.locations[player_zone].size_tiles
        limp = limp_factor(player)
        opens = (
            k.PACE_SPEED_TILES_PER_MIN[minute.pace] * limp if minute.approach_target is None else 0
        )
        for zombie in _by_id(world.zombies.values()):
            if zombie.is_down(now):
                continue
            if zombie.state in _HUNTING:
                self._chase(zombie, opens, size)
            elif zombie.state == ZombieState.ALERTED:
                self._follow_sound(zombie, size)
            if zombie.zombie_id == minute.approach_target:
                zombie.gap = max(
                    float(k.ATTACK_RANGE_TILES), zombie.gap - k.WALK_APPROACH_TILES_PER_MIN * limp
                )

    def _chase(self, zombie: ZombieEntity, opens: float, size: int) -> None:
        manager = self._manager
        world = manager.world
        player_zone = manager.player.current_location_id
        if zombie.zone_id != player_zone and path_blocked(world, zombie.zone_id, player_zone):
            zombie.state = ZombieState.IDLE
            return
        gap = zombie.gap - chase_speed(zombie) + opens
        zombie.gap = max(float(k.ATTACK_RANGE_TILES), gap)
        if zombie.gap <= size:
            zombie.zone_id = player_zone

    def _follow_sound(self, zombie: ZombieEntity, size: int) -> None:
        manager = self._manager
        world = manager.world
        player_zone = manager.player.current_location_id
        step = chase_speed(zombie)
        if zombie.zone_id == player_zone:
            zombie.gap = max(float(k.ATTACK_RANGE_TILES), zombie.gap - step)
            zombie.sound_gap -= step
            if zombie.gap <= k.ATTACK_RANGE_TILES:
                zombie.state = ZombieState.CHASING
                zombie.time_since_seen = 0.0
                zombie.has_chased = True
            elif zombie.sound_gap <= 0:
                zombie.state = ZombieState.IDLE
            return
        if path_blocked(world, zombie.zone_id, player_zone):
            zombie.state = ZombieState.IDLE
            return
        zombie.sound_gap -= step
        if zombie.sound_gap <= size:
            zombie.zone_id = player_zone
            zombie.gap = max(float(k.ATTACK_RANGE_TILES), zombie.sound_gap)

    def _spot(
        self, minute: PlayerMinute, sample: WeatherSample, light: float, report: MinuteReport
    ) -> bool:
        """Step 4; returns whether a zombie newly noticed the player."""
        manager = self._manager
        world, player = manager.world, manager.player
        player_zone = player.current_location_id
        newly = False
        rolled = spotted_any = close_call = False
        engaged = (minute.approach_target, minute.swing_target)
        for zombie in _by_id(world.zombies.values()):
            hunting = zombie.state in _HUNTING
            if not hunting and zombie.zone_id != player_zone:
                continue
            if zombie.state == ZombieState.IDLE:
                zombie.facing_cos = self._rng.uniform(-1.0, 1.0)
            else:
                zombie.facing_cos = 1.0
            result = spot_chance(zombie, player, sample, light, minute.pace)
            rolled = True
            if result.raw > k.SNEAK_XP_CLOSE_CHANCE and zombie.gap <= k.SNEAK_XP_CLOSE_TILES:
                close_call = True
            if self._rng.random() < result.per_minute:
                spotted_any = True
                zombie.time_since_seen = 0.0
                zombie.has_chased = True
                zombie.bonus_spot_time = float(k.SPOT_BONUS_FRAMES)
                zombie.facing_cos = 1.0
                if not hunting:
                    zombie.state = ZombieState.CHASING
                    newly = newly or zombie.zombie_id not in engaged
        if rolled and not spotted_any and not close_call and minute.pace == Pace.SNEAK:
            self._sneak_xp(report)
        return newly

    def _sneak_xp(self, report: MinuteReport) -> None:
        chance = 1 - (1 - k.SNEAK_XP_PER_FRAME_CHANCE) ** k.FRAMES_PER_MINUTE
        for skill_id in (skill_k.SNEAKING, skill_k.LIGHTFOOTED):
            if self._rng.random() < chance:
                report.facts.extend(
                    self._skills.add_xp(self._manager.player, skill_id, k.SNEAK_XP_AMOUNT)
                )

    def _remember(self) -> None:
        for zombie in _by_id(self._manager.world.zombies.values()):
            zombie.time_since_seen += k.FRAMES_PER_MINUTE
            zombie.bonus_spot_time = max(0.0, zombie.bonus_spot_time - k.FRAMES_PER_MINUTE)
            if zombie.state in _HUNTING and zombie.time_since_seen > zombie.memory:
                zombie.state = ZombieState.IDLE
                zombie.side = None

    def _report_reach(self, minute: PlayerMinute) -> bool:
        """Mark zombies within reach as attacking; whether one has just got there."""
        manager = self._manager
        player_zone = manager.player.current_location_id
        reached = False
        for zombie in _by_id(manager.world.zombies.values()):
            if zombie.state not in _HUNTING:
                continue
            within = zombie.zone_id == player_zone and zombie.gap <= k.ATTACK_RANGE_TILES
            if within and zombie.state != ZombieState.ATTACKING:
                zombie.state = ZombieState.ATTACKING
                zombie.has_chased = True
                reached = reached or zombie.zombie_id not in (
                    minute.approach_target,
                    minute.swing_target,
                )
            elif not within and zombie.state == ZombieState.ATTACKING:
                zombie.state = ZombieState.CHASING
                zombie.side = None
        return reached

    def _clear_staggered(self) -> None:
        for zombie in self._manager.world.zombies.values():
            zombie.staggered = False

    def _attack(self, now: int, minute: PlayerMinute, report: MinuteReport) -> None:
        """Step 6: every zombie in reach attacks once, unless it is down or staggered."""
        manager = self._manager
        player = manager.player
        attackers = [
            z
            for z in _by_id(manager.world.zombies.values())
            if z.state == ZombieState.ATTACKING and not z.is_down(now) and not z.staggered
        ]
        if not attackers:
            return
        taken = {z.side for z in attackers if z.side is not None}
        for zombie in attackers:
            if zombie.side is None:
                zombie.side = self._pick_side(first=not taken)
                taken.add(zombie.side)
        report.attacked = True
        if player.asleep:
            player.asleep = False
        name = player.appearance.forename
        fighting = minute.swing_target is not None or (
            minute.approach_target is not None
            and all(z.zombie_id == minute.approach_target for z in attackers)
        )
        hurt = False
        for zombie in attackers:
            assert zombie.side is not None
            outcome = resolve_attack(player, zombie.side, len(attackers), self._rng)
            if outcome.dragged_down:
                kill(player)
                report.death_fact = k.DRAGGED_FACT.format(name=name)
                report.interrupted = True
                return
            report.facts.append(self._attack_fact(outcome, name))
            hurt = hurt or outcome.wound is not None
            if player.hit_points <= 0:
                report.death_fact = report.facts.pop()
                report.interrupted = True
                return
        if hurt or not fighting:
            report.interrupted = True

    def _pick_side(self, *, first: bool) -> AttackSide:
        if first:
            return AttackSide.FRONT
        return self._rng.choice(list(AttackSide))

    @staticmethod
    def _attack_fact(outcome: AttackOutcome, name: str) -> str:
        if outcome.defended:
            return k.DEFENDED_FACT.format(name=name)
        if outcome.blocked:
            return k.BLOCKED_FACT.format(name=name)
        if outcome.wound is None:
            return k.THUMP_FACT.format(name=name)
        wound = outcome.wound
        return k.WOUND_FACT.format(
            verb=k.WOUND_VERBS[wound.kind], name=name, part=k.BODY_PART_WORDS[wound.part]
        )


@dataclass(frozen=True)
class ThreatView:
    """A perceived zombie in words; `zombie_id` is None for one that is only heard."""

    zombie_id: str | None
    distance_word: str
    state_word: str


def _distance_word(gap: float) -> str:
    for limit, word in k.DISTANCE_WORDS:
        if gap <= limit:
            return word
    return k.DISTANCE_WORD_FAR


def _state_word(zombie: ZombieEntity, now: int) -> str:
    if zombie.is_down(now):
        return k.STATE_WORD_DOWN
    if zombie.state == ZombieState.ATTACKING and zombie.side == AttackSide.BEHIND:
        return k.STATE_WORD_BEHIND
    if zombie.lunger and zombie.has_chased:
        return k.STATE_WORD_FAST
    return k.STATE_WORDS[zombie.state]


def threat_views(manager: GameManager) -> list[ThreatView]:
    """The zombies the player perceives, in words that never show a number."""
    views: list[ThreatView] = []
    for seen in perceived_now(manager):
        zombie = seen.zombie
        if seen.seen:
            views.append(
                ThreatView(
                    zombie.zombie_id,
                    _distance_word(zombie.gap),
                    _state_word(zombie, manager.narrative.minutes),
                )
            )
        else:
            hunting = zombie.state in _HUNTING
            word = k.HEARD_WORD_HUNTING if hunting else k.HEARD_WORD_OTHER
            views.append(ThreatView(None, "", word))
    return views
