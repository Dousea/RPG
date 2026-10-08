"""A GameManager as a JSON-ready dict, and back.

Only *dynamic* state is saved. Static definitions -- item stats, location
names and connections, trait definitions -- stay in `data/` and are looked
up by id on load. That keeps saves small and lets content be rebalanced without
invalidating them.
"""

import dataclasses
import logging
from typing import Any

from data.character import creation as creation_k
from data.character.exercises import EXERCISES, REGION_PARTS
from data.character.skills import MAX_LEVEL, SKILLS, total_xp_for_level
from data.character.traits import TRAITS
from data.items import ITEMS, WETNESS_MAX
from data.story.memory import LAST_STORY_MAX_LENGTH
from data.story.npcs import build_starting_npcs
from data.story.quests import TAKE_ANY_WEAPON, build_starting_quests
from data.world.barriers import MAX_PLANKS_PER_SIDE, build_starting_barriers
from data.world.climate import STAGE_PHRASES
from data.world.clock import WORLD_START_MINUTE_OF_DAY
from data.world.locations import STARTING_ZONE_ID, build_starting_locations
from managers.game import (
    DEATH_CAUSE_MAX_LENGTH,
    MAX_PLACE_LENGTH,
    WORLD_START_DATE,
    GameManager,
    MemoryState,
    NarrativeState,
)
from managers.story.relationship import RelationshipManager
from managers.world import item_ids
from managers.world.climate import ClimateEngine
from modules.body.parts import BodyLocation, BodyPart, PartState, new_body
from modules.body.stats import Stats
from modules.body.thermal import ThermalState
from modules.character.appearance import Appearance, Gender
from modules.character.equipment import CharacterArmorSlot, CharacterHoldableSlot
from modules.character.exercise import ExerciseState
from modules.character.faction import CharacterFaction
from modules.character.skills import SkillState
from modules.character.state import CharacterCondition
from modules.entity.barrier import BarrierEntity
from modules.entity.corpse import CorpseEntity
from modules.entity.item import ItemEntity
from modules.entity.npc import NpcEntity
from modules.entity.player import PlayerEntity
from modules.entity.zombie import (
    TIME_SINCE_SEEN_START,
    AttackSide,
    ZombieEntity,
    ZombieState,
)
from modules.item import ClothingItem, ContainerItem, MedicalItem, MeleeWeaponItem, StackItem
from modules.story.quest import QuestState, QuestStatus
from modules.story.social import SocialLog
from modules.world.location import World
from modules.world.room import ContainerEntity, RoomEntity
from modules.world.weather import AirFront, PeriodStage, WeatherPeriod

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 27  # world-lore: the clinic filing cabinet

MAX_ID_LENGTH = 40


# Equipment slots are two separate enums; this resolves a saved slot name back
# to the right one.
_SLOT_ENUMS = (CharacterHoldableSlot, CharacterArmorSlot)


def _slot_from_value(value: str):
    for slot_enum in _SLOT_ENUMS:
        try:
            return slot_enum(value)
        except ValueError:
            continue
    return None


def _as_bool(value: Any) -> bool:
    """Coerce a hand-editable value to bool, without Python's `bool("false")`
    footgun -- a JSON string "false" (or any other truthy junk) must not
    read as a permanent death. A real bool passes through; "true"/"false"
    (case-insensitive, whitespace-stripped) map accordingly; anything else
    is False, same as a value that was never set.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        folded = value.strip().casefold()
        if folded == "true":
            return True
        if folded == "false":
            return False
    return False


def _as_text(value: Any, cap: int) -> str:
    """Coerce a hand-editable value to capped text. `None` -> "", not the
    literal string "None" that a bare `str(None)` would produce.
    """
    if value is None:
        return ""
    return str(value)[:cap]


def _as_dict(value: Any) -> dict[str, Any]:
    """A save can be hand-edited to hold the wrong container type for any
    field; treat anything that isn't actually a dict as empty rather than
    crashing on the first `.items()`/`.get()` call."""
    return value if isinstance(value, dict) else {}


def _appearance_from_dict(data: dict[str, Any]) -> Appearance:
    try:
        gender = Gender(data.get("gender", Gender.MALE.value))
    except ValueError:
        logger.warning(f"Unknown gender '{data.get('gender')}'; using male.")
        gender = Gender.MALE
    name_cap = creation_k.NAME_MAX_CHARS
    return Appearance(
        forename=_as_text(data.get("forename", ""), name_cap),
        surname=_as_text(data.get("surname", ""), name_cap),
        gender=gender,
        skin_tone=int(data.get("skin_tone", creation_k.SKIN_TONE_MIN)),
        hair_style=_as_text(data.get("hair_style", ""), MAX_ID_LENGTH),
        hair_colour=_as_text(data.get("hair_colour", ""), MAX_ID_LENGTH),
        beard_style=_as_text(data.get("beard_style", ""), MAX_ID_LENGTH),
        backstory=_as_text(data.get("backstory", ""), creation_k.BACKSTORY_MAX_CHARS),
    )


def _known_trait_ids(values: Any) -> list[str]:
    ids = [str(v) for v in values] if isinstance(values, list) else []
    for trait_id in ids:
        if trait_id not in TRAITS:
            logger.warning(f"Dropping unknown trait '{trait_id}'.")
    return [trait_id for trait_id in ids if trait_id in TRAITS]


def _int_map(value: Any) -> dict[str, int]:
    return {str(key): int(amount) for key, amount in _as_dict(value).items()}


def _social_log_to_dict(log: SocialLog) -> dict[str, Any]:
    return {
        "day": log.day,
        "counts": dict(log.counts),
        "refusals": dict(log.refusals),
        "told_topics": sorted(log.told_topics),
    }


def _social_log_from_dict(value: Any) -> SocialLog:
    data = _as_dict(value)
    topics = data.get("told_topics")
    return SocialLog(
        day=int(data.get("day", 1)),
        counts=_int_map(data.get("counts")),
        refusals=_int_map(data.get("refusals")),
        told_topics={str(topic) for topic in topics} if isinstance(topics, list) else set(),
    )


def _float_map(value: Any, allowed: Any) -> dict[str, float]:
    return {str(key): float(amount) for key, amount in _as_dict(value).items() if key in allowed}


def _skills_from_dict(value: Any) -> dict[str, SkillState]:
    skills: dict[str, SkillState] = {}
    for skill_id, entry in _as_dict(value).items():
        if skill_id not in SKILLS:
            logger.warning(f"Dropping unknown skill '{skill_id}'.")
            continue
        entry = _as_dict(entry)
        level = max(0, min(MAX_LEVEL, int(entry.get("level", 0))))
        cap = total_xp_for_level(skill_id, MAX_LEVEL)
        skills[skill_id] = SkillState(level, max(0.0, min(float(cap), float(entry.get("xp", 0)))))
    return skills


def _exercise_to_dict(state: ExerciseState) -> dict[str, Any]:
    return {
        "regularity": dict(state.regularity),
        "last_done_minute": dict(state.last_done_minute),
        "future_stiffness": dict(state.future_stiffness),
        "region_timers": dict(state.region_timers),
    }


def _exercise_from_dict(data: dict[str, Any]) -> ExerciseState:
    return ExerciseState(
        regularity=_float_map(data.get("regularity"), EXERCISES),
        last_done_minute={
            key: int(minute)
            for key, minute in _as_dict(data.get("last_done_minute")).items()
            if key in EXERCISES
        },
        future_stiffness=_float_map(data.get("future_stiffness"), REGION_PARTS),
        region_timers={
            key: int(ticks)
            for key, ticks in _as_dict(data.get("region_timers")).items()
            if key in REGION_PARTS
        },
    )


def _part_state_to_dict(state: PartState) -> dict[str, Any]:
    return dataclasses.asdict(state)


def _part_state_from_dict(data: dict[str, Any]) -> PartState:
    defaults = PartState()
    values: dict[str, Any] = {}
    for field in dataclasses.fields(PartState):
        default = getattr(defaults, field.name)
        raw = data.get(field.name, default)
        if isinstance(default, bool):
            values[field.name] = _as_bool(raw)
        elif isinstance(default, float):
            values[field.name] = float(raw)
        else:
            values[field.name] = None if raw is None else _as_text(raw, MAX_ID_LENGTH)
    return PartState(**values)


def _body_to_dict(body: dict[BodyPart, PartState]) -> dict[str, Any]:
    return {part.value: _part_state_to_dict(state) for part, state in body.items()}


def _body_from_dict(value: Any) -> dict[BodyPart, PartState]:
    body = new_body()
    for name, entry in _as_dict(value).items():
        try:
            part = BodyPart(name)
        except ValueError:
            logger.warning(f"Dropping unknown body part '{name}'.")
            continue
        body[part] = _part_state_from_dict(_as_dict(entry))
    return body


def _item_entity_to_dict(entity: ItemEntity) -> dict[str, Any]:
    return {
        "item_id": entity.item.id,
        "hit_points": entity.hit_points,
        "instance_id": entity.instance_id,
        "wetness": entity.wetness,
        "holes": sorted(part.value for part in entity.holes),
        "condition": entity.condition,
        "uses": entity.uses,
        "contents": [_item_entity_to_dict(inner) for inner in entity.contents],
        "loot_pending": entity.loot_pending,
    }


def _item_entity_from_dict(data: dict[str, Any]) -> ItemEntity | None:
    item = ITEMS.get(data.get("item_id", ""))
    if item is None:
        logger.warning(f"Dropping unknown item id '{data.get('item_id')}'.")
        return None
    entity = ItemEntity(item=item, instance_id=_as_text(data.get("instance_id", ""), MAX_ID_LENGTH))
    # __post_init__ sets full health; restore the saved condition over it.
    entity.hit_points = int(data.get("hit_points", entity.max_hit_points))
    entity.wetness = min(max(float(data.get("wetness", 0.0)), 0.0), WETNESS_MAX)
    if isinstance(entity.item, MeleeWeaponItem):
        entity.condition = min(
            max(int(data.get("condition", entity.item.condition_max)), 0),
            entity.item.condition_max,
        )
    if isinstance(entity.item, MedicalItem | StackItem):
        entity.uses = min(max(int(data.get("uses", entity.item.uses)), 0), entity.item.uses)
    for name in data.get("holes", []):
        try:
            entity.holes.add(BodyPart(name))
        except ValueError:
            logger.warning(f"Dropping unknown body part '{name}' from a hole.")
    if isinstance(entity.item, ContainerItem):
        entity.loot_pending = bool(data.get("loot_pending", False))
        entity.contents = [
            inner
            for inner in (_item_entity_from_dict(_as_dict(c)) for c in data.get("contents", []))
            if inner is not None
        ]
    return entity


def _container_to_dict(container: ContainerEntity) -> dict[str, Any]:
    return {
        "container_id": container.container_id,
        "name": container.name,
        "kind": container.kind,
        "capacity": container.capacity,
        "aliases": list(container.aliases),
        "source": list(container.source) if container.source else None,
        "opened": container.opened,
        "fixed": container.fixed,
        "contents": [_item_entity_to_dict(entity) for entity in container.contents],
    }


def _container_from_dict(data: dict[str, Any]) -> ContainerEntity | None:
    container_id = _as_text(data.get("container_id", ""), MAX_ID_LENGTH)
    if not container_id:
        return None
    source = data.get("source")
    contents = (_item_entity_from_dict(_as_dict(entry)) for entry in data.get("contents", []))
    return ContainerEntity(
        container_id=container_id,
        name=_as_text(data.get("name", ""), MAX_ID_LENGTH),
        kind=_as_text(data.get("kind", ""), MAX_ID_LENGTH),
        capacity=float(data.get("capacity", 0)),
        aliases=[_as_text(alias, MAX_ID_LENGTH) for alias in data.get("aliases", [])],
        source=(str(source[0]), str(source[1]))
        if isinstance(source, list) and len(source) == 2
        else None,
        contents=[entity for entity in contents if entity is not None],
        opened=_as_bool(data.get("opened", False)),
        fixed=_as_bool(data.get("fixed", False)),
    )


def _room_to_dict(room: RoomEntity) -> dict[str, Any]:
    return {
        "room_id": room.room_id,
        "name": room.name,
        "kind": room.kind,
        "aliases": list(room.aliases),
        "proc_spawned": dict(room.proc_spawned),
        "containers": [_container_to_dict(container) for container in room.containers],
    }


def _room_from_dict(data: dict[str, Any]) -> RoomEntity | None:
    room_id = _as_text(data.get("room_id", ""), MAX_ID_LENGTH)
    if not room_id:
        return None
    containers = (_container_from_dict(_as_dict(entry)) for entry in data.get("containers", []))
    return RoomEntity(
        room_id=room_id,
        name=_as_text(data.get("name", ""), MAX_ID_LENGTH),
        kind=_as_text(data.get("kind", ""), MAX_ID_LENGTH),
        aliases=[_as_text(alias, MAX_ID_LENGTH) for alias in data.get("aliases", [])],
        containers=[container for container in containers if container is not None],
        proc_spawned=_int_map(data.get("proc_spawned")),
    )


# === Serialization ===


def _worn_to_dict(worn: dict[BodyLocation, ItemEntity]) -> dict[str, Any]:
    return {location.value: _item_entity_to_dict(entity) for location, entity in worn.items()}


def _worn_from_dict(value: Any) -> dict[BodyLocation, ItemEntity]:
    """Saved worn items back to their locations; an item that does not fit its location is dropped."""
    worn: dict[BodyLocation, ItemEntity] = {}
    for location_name, item_data in _as_dict(value).items():
        entity = _item_entity_from_dict(item_data) if item_data else None
        try:
            location = BodyLocation(location_name)
        except ValueError:
            logger.warning(f"Dropping unknown worn location '{location_name}'.")
            continue
        if entity is None:
            continue
        if (
            not isinstance(entity.item, ClothingItem | ContainerItem)
            or entity.item.body_location != location
        ):
            logger.warning(f"Dropping '{entity.item.id}' worn at '{location_name}'.")
            continue
        worn[location] = entity
    return worn


_ZOMBIE_ITEM_FIELDS = ("worn", "attached", "carried")


def _zombie_to_dict(zombie: ZombieEntity) -> dict[str, Any]:
    data = {
        f.name: getattr(zombie, f.name)
        for f in dataclasses.fields(zombie)
        if f.name not in _ZOMBIE_ITEM_FIELDS
    }
    data["state"] = zombie.state.value
    data["side"] = zombie.side.value if zombie.side is not None else None
    data["worn"] = _worn_to_dict(zombie.worn)
    data["attached"] = _item_entity_to_dict(zombie.attached) if zombie.attached else None
    data["carried"] = [_item_entity_to_dict(entity) for entity in zombie.carried]
    return data


def _corpse_to_dict(corpse: CorpseEntity) -> dict[str, Any]:
    data = {f.name: getattr(corpse, f.name) for f in dataclasses.fields(corpse)}
    data["contents"] = [_item_entity_to_dict(entity) for entity in corpse.contents]
    data["attached"] = next(
        (i for i, entity in enumerate(corpse.contents) if entity is corpse.attached), None
    )
    return data


def _corpse_from_dict(data: dict[str, Any], zone_ids: Any) -> CorpseEntity | None:
    zone_id = str(data.get("zone_id", ""))
    if zone_id not in zone_ids:
        logger.warning(f"Dropping corpse in unknown zone '{zone_id}'.")
        return None
    try:
        contents = [_item_entity_from_dict(_as_dict(entry)) for entry in data.get("contents", [])]
        kept = [entity for entity in contents if entity is not None]
        attached_at = data.get("attached")
        attached = None
        if isinstance(attached_at, int) and 0 <= attached_at < len(contents):
            attached = contents[attached_at]
        return CorpseEntity(
            corpse_id=_as_text(data["corpse_id"], MAX_ID_LENGTH),
            zone_id=zone_id,
            gap=float(data.get("gap", 1.0)),
            female=_as_bool(data.get("female", False)),
            outfit=_as_text(data.get("outfit", ""), MAX_ID_LENGTH),
            died_at=int(data["died_at"]),
            rot_at_death=min(max(int(data.get("rot_at_death", 1)), 1), 3),
            skeleton=_as_bool(data.get("skeleton", False)),
            contents=kept,
            attached=attached,
            searched=_as_bool(data.get("searched", False)),
            fake_dead=_as_bool(data.get("fake_dead", False)),
            crawling=_as_bool(data.get("crawling", False)),
            risen_from_player=_as_bool(data.get("risen_from_player", False)),
        )
    except (KeyError, TypeError, ValueError):
        logger.warning("Dropping a corpse with unreadable fields.")
        return None


def _zombie_from_dict(data: dict[str, Any], zone_ids: Any) -> ZombieEntity | None:
    zone_id = str(data.get("zone_id", ""))
    if zone_id not in zone_ids:
        logger.warning(f"Dropping zombie in unknown zone '{zone_id}'.")
        return None
    try:
        state = ZombieState(data.get("state", ZombieState.IDLE.value))
        raw_side = data.get("side")
        side = AttackSide(raw_side) if raw_side is not None else None
        return ZombieEntity(
            zombie_id=_as_text(data["zombie_id"], MAX_ID_LENGTH),
            zone_id=zone_id,
            health=float(data["health"]),
            speed_type=int(data["speed_type"]),
            speed_mod=float(data["speed_mod"]),
            lunger=_as_bool(data.get("lunger", False)),
            strength=int(data["strength"]),
            memory=int(data["memory"]),
            sight=int(data["sight"]),
            hearing=int(data["hearing"]),
            state=state,
            gap=float(data.get("gap", 0.0)),
            facing_cos=float(data.get("facing_cos", 0.0)),
            time_since_seen=float(data.get("time_since_seen", TIME_SINCE_SEEN_START)),
            has_chased=_as_bool(data.get("has_chased", False)),
            bonus_spot_time=float(data.get("bonus_spot_time", 0.0)),
            side=side,
            sound_gap=float(data.get("sound_gap", 0.0)),
            hits_taken=int(data.get("hits_taken", 0)),
            down_until=int(data.get("down_until", 0)),
            staggered=_as_bool(data.get("staggered", False)),
            thump_barrier=_optional_text(data.get("thump_barrier")),
            thump_rate=float(data.get("thump_rate", 0.0)),
            thump_carry=float(data.get("thump_carry", 0.0)),
            thump_cooldown=int(data.get("thump_cooldown", 0)),
            was_chasing=_as_bool(data.get("was_chasing", False)),
            female=_as_bool(data.get("female", False)),
            outfit=_as_text(data.get("outfit", ""), MAX_ID_LENGTH),
            worn=_worn_from_dict(data.get("worn")),
            attached=(
                _item_entity_from_dict(_as_dict(data["attached"])) if data.get("attached") else None
            ),
            carried=[
                entity
                for entity in (_item_entity_from_dict(_as_dict(e)) for e in data.get("carried", []))
                if entity is not None
            ],
            crawling=_as_bool(data.get("crawling", False)),
            become_crawler=_as_bool(data.get("become_crawler", False)),
            was_fake_dead=_as_bool(data.get("was_fake_dead", False)),
            risen_from_player=_as_bool(data.get("risen_from_player", False)),
        )
    except (KeyError, TypeError, ValueError):
        logger.warning("Dropping a zombie with unreadable fields.")
        return None


def _barrier_to_dict(barrier: BarrierEntity) -> dict[str, Any]:
    return {
        "open": barrier.open,
        "broken": barrier.broken,
        "locked": barrier.locked,
        "health": barrier.health,
        "barricades": {side: list(planks) for side, planks in barrier.barricades.items()},
    }


def _barriers_from_dict(value: Any) -> dict[str, BarrierEntity]:
    """The shipped barriers with their saved state laid over them."""
    barriers = build_starting_barriers()
    for barrier_id, data in _as_dict(value).items():
        barrier = barriers.get(barrier_id)
        if barrier is None:
            logger.warning(f"Dropping unknown barrier '{barrier_id}'.")
            continue
        saved = _as_dict(data)
        barrier.open = _as_bool(saved.get("open", barrier.open))
        barrier.broken = _as_bool(saved.get("broken", barrier.broken))
        barrier.locked = _as_bool(saved.get("locked", barrier.locked))
        barrier.health = min(max(int(saved.get("health", barrier.health)), 0), barrier.max_health)
        for side, planks in _as_dict(saved.get("barricades")).items():
            if side in barrier.zones and isinstance(planks, list):
                barrier.barricades[side] = [
                    max(1, int(plank)) for plank in planks[:MAX_PLANKS_PER_SIDE]
                ]
    return barriers


def _optional_text(value: Any) -> str | None:
    return _as_text(value, MAX_ID_LENGTH) if isinstance(value, str) and value else None


def _optional_float(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _optional_minute(value: Any) -> int | None:
    return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _weather_to_dict(climate: ClimateEngine) -> dict[str, Any]:
    period = climate.period
    front = climate.front
    return {
        "front": {
            "positive": front.positive,
            "strength": front.strength,
            "start_hour": front.start_hour,
        },
        "period": None
        if period is None
        else {
            "start_hour": period.start_hour,
            "stages": [dataclasses.asdict(stage) for stage in period.stages],
        },
    }


def _stage_from_dict(data: dict[str, Any]) -> PeriodStage:
    name = str(data["name"])
    if name not in STAGE_PHRASES:
        raise ValueError(f"unknown weather stage {name!r}")
    return PeriodStage(
        name=name,
        hours=float(data["hours"]),
        precipitation=float(data["precipitation"]),
        wind=float(data["wind"]),
        cloud=float(data["cloud"]),
        thunder=_as_bool(data["thunder"]),
    )


def _climate_from_dict(seed: int, minutes: int, data: dict[str, Any]) -> ClimateEngine:
    """Rebuild the climate: noise from the seed, front and period from the save."""
    climate = ClimateEngine(seed, WORLD_START_DATE, WORLD_START_MINUTE_OF_DAY)
    front_data = _as_dict(data.get("front"))
    front = None
    if front_data:
        try:
            front = AirFront(
                positive=_as_bool(front_data.get("positive", False)),
                strength=float(front_data.get("strength", 0.0)),
                start_hour=int(front_data.get("start_hour", 0)),
            )
        except (TypeError, ValueError):
            logger.warning("Dropping an unreadable weather front from the save.")
    period = None
    period_data = data.get("period")
    if isinstance(period_data, dict):
        try:
            period = WeatherPeriod(
                start_hour=float(period_data["start_hour"]),
                stages=tuple(_stage_from_dict(stage) for stage in period_data["stages"]),
            )
        except (KeyError, TypeError, ValueError):
            logger.warning("Dropping an unreadable weather period from the save.")
    climate.restore(minutes, front, period)
    return climate


def to_dict(manager: GameManager) -> dict[str, Any]:
    player = manager.player
    narrative = manager.narrative
    memory = manager.memory
    item_ids.stamp_world(manager.world, player, manager.npcs.values())

    return {
        "version": SCHEMA_VERSION,
        "world": {
            "time": manager.world.time,
            "date": manager.world.date,
            "seed": manager.world.seed,
            "power_on": manager.world.power_on,
            "outbreak_started_at": manager.world.outbreak_started_at,
            "last_redistribution_minute": manager.world.last_redistribution_minute,
            "next_zombie_number": manager.world.next_zombie_number,
            "zombie_kills": dict(manager.world.zombie_kills),
            "fired_beats": dict(manager.world.fired_beats),
            "zombies": [_zombie_to_dict(zombie) for zombie in manager.world.zombies.values()],
            "corpses": [_corpse_to_dict(corpse) for corpse in manager.world.corpses.values()],
            "next_corpse_number": manager.world.next_corpse_number,
            "next_item_number": manager.world.next_item_number,
            "smell_zone_id": manager.world.smell_zone_id,
            "barriers": {
                barrier_id: _barrier_to_dict(barrier)
                for barrier_id, barrier in manager.world.barriers.items()
            },
            # Locations themselves are static; only ground items move.
            "rooms": {
                location_id: {
                    "entry_room": location.entry_room,
                    "rooms": [_room_to_dict(room) for room in location.rooms.values()],
                }
                for location_id, location in manager.world.locations.items()
                if location.rooms
            },
            "ground_items": {
                location_id: [
                    _item_entity_to_dict(entity)
                    for entity in location.entities
                    if isinstance(entity, ItemEntity)
                ]
                for location_id, location in manager.world.locations.items()
            },
        },
        "player": {
            "entity_id": player.entity_id,
            "name": player.name,
            "current_location_id": player.current_location_id,
            "current_place": player.current_place,
            "current_room": player.current_room,
            "stats": player.stats.to_dict(),
            "thermal": player.thermal.to_dict(),
            "asleep": player.asleep,
            "sneaking": player.sneaking,
            "body": _body_to_dict(player.body),
            "zombie_infection_since": player.zombie_infection_since,
            "zombie_infection_hours": player.zombie_infection_hours,
            "pain_effect_minutes": player.pain_effect_minutes,
            "reduce_infection_power": player.reduce_infection_power,
            "food_eaten_timer": player.food_eaten_timer,
            "appearance": {
                "forename": player.appearance.forename,
                "surname": player.appearance.surname,
                "gender": player.appearance.gender.value,
                "skin_tone": player.appearance.skin_tone,
                "hair_style": player.appearance.hair_style,
                "hair_colour": player.appearance.hair_colour,
                "beard_style": player.appearance.beard_style,
                "backstory": player.appearance.backstory,
            },
            "occupation_id": player.occupation_id,
            "job_title": player.job_title,
            "trait_ids": list(player.traits),
            "skills": {
                skill_id: {"level": state.level, "xp": state.xp}
                for skill_id, state in player.skills.items()
            },
            "skill_boosts": dict(player.skill_boosts),
            "loss_timers": dict(player.loss_timers),
            "loss_timer_steps": dict(player.loss_timer_steps),
            "exercise": _exercise_to_dict(player.exercise),
            "inventory": [_item_entity_to_dict(e) for e in player.inventory],
            "equipment": {
                slot.value: (_item_entity_to_dict(entity) if entity else None)
                for slot, entity in player.equipment.items()
            },
            "worn": _worn_to_dict(player.worn),
            "conditions": [condition.value for condition in player.conditions],
            "zombie_kills": player.zombie_kills,
            "at_barrier": player.at_barrier,
            "carrying_corpse": player.carrying_corpse,
            "carrying_skeleton": player.carrying_skeleton,
        },
        "npcs": [
            {
                "npc_id": npc.npc_id,
                "name": npc.name,
                "description": npc.description,
                "current_location_id": npc.current_location_id,
                "hit_points": npc.hit_points,
                "age": npc.age,
                "faction": npc.faction.value,
                "personality": list(npc.personality),
                "status": list(npc.status),
                "notes": npc.notes,
                "romance_eligible": npc.romance_eligible,
                "conditions": [condition.value for condition in npc.conditions],
                "inventory": [_item_entity_to_dict(e) for e in npc.inventory],
                "base_max_hit_points": npc.base_max_hit_points,
                "goals": list(npc.goals),
                "knowledge": sorted(npc.knowledge),
                "following": npc.following,
            }
            for npc in manager.npcs.values()
        ],
        "relationships": {
            "affinities": {
                source: dict(targets)
                for source, targets in manager.relationship_manager.affinities.items()
            },
            "trusts": {
                source: dict(targets)
                for source, targets in manager.relationship_manager.trusts.items()
            },
            "reputations": {
                source.value: {target.value: score for target, score in targets.items()}
                for source, targets in manager.relationship_manager.reputations.items()
            },
        },
        "weather": _weather_to_dict(manager.climate),
        "narrative": {
            "minutes": narrative.minutes,
            "goals": {k: list(v) for k, v in narrative.goals.items()},
            "flags": dict(narrative.flags),
            "discovered_flags": sorted(narrative.discovered_flags),
            "pending_corrections": list(narrative.pending_corrections),
            "game_over": narrative.game_over,
            "death_cause": narrative.death_cause,
            "social_log": _social_log_to_dict(narrative.social_log),
        },
        "memory": {
            "recent_events": list(memory.recent_events),
            "full_event_log": list(memory.full_event_log),
            "summaries": list(memory.summaries),
            "last_story": memory.last_story,
        },
        "quests": {
            quest_id: {
                "title": quest.title,
                "status": quest.status.value,
                "objectives": list(quest.objectives),
                "objective_labels": dict(quest.objective_labels),
                "completed_objectives": list(quest.completed_objectives),
            }
            for quest_id, quest in manager.quests.items()
        },
    }


# === Deserialization ===


def from_dict(data: dict[str, Any]) -> GameManager:
    world_data = data.get("world", {})
    locations = build_starting_locations()

    # Ground items are fully replaced by the save; a location missing from the
    # save simply keeps nothing, not its starting items.
    for location in locations.values():
        location.entities = [
            entity for entity in location.entities if not isinstance(entity, ItemEntity)
        ]
    for location_id, items in world_data.get("ground_items", {}).items():
        location = locations.get(location_id)
        if location is None:
            logger.warning(f"Dropping items for unknown location '{location_id}'.")
            continue
        for item_data in items:
            entity = _item_entity_from_dict(item_data)
            if entity is not None:
                location.entities.append(entity)

    for location_id, entry in _as_dict(world_data.get("rooms")).items():
        location = locations.get(location_id)
        if location is None:
            logger.warning(f"Dropping rooms for unknown location '{location_id}'.")
            continue
        rooms = (_room_from_dict(_as_dict(r)) for r in _as_dict(entry).get("rooms", []))
        location.rooms = {room.room_id: room for room in rooms if room is not None}
        entry_room = _optional_text(_as_dict(entry).get("entry_room"))
        location.entry_room = entry_room if entry_room in location.rooms else None

    # World.time/date are derived from the narrative clock, which GameManager
    # re-renders on construction. The saved values are carried over so a save is
    # still readable on its own, but they are not trusted.
    world = World(
        time=world_data.get("time", "12:00 PM"),
        date=world_data.get("date", "2023-10-01"),
        seed=int(world_data.get("seed", 0)),
        power_on=_as_bool(world_data.get("power_on", True)) if "power_on" in world_data else True,
        locations=locations,
        barriers=_barriers_from_dict(world_data.get("barriers")),
        outbreak_started_at=_optional_minute(world_data.get("outbreak_started_at")),
        last_redistribution_minute=_optional_minute(world_data.get("last_redistribution_minute")),
        next_zombie_number=int(world_data.get("next_zombie_number", 1)),
        next_corpse_number=int(world_data.get("next_corpse_number", 1)),
        next_item_number=int(world_data.get("next_item_number", 1)),
        smell_zone_id=(
            world_data["smell_zone_id"] if world_data.get("smell_zone_id") in locations else None
        ),
        fired_beats=_int_map(world_data.get("fired_beats")),
        zombie_kills={
            zone_id: int(count)
            for zone_id, count in _as_dict(world_data.get("zombie_kills")).items()
            if zone_id in locations
        },
    )
    for zombie_data in world_data.get("zombies", []):
        zombie = _zombie_from_dict(_as_dict(zombie_data), locations)
        if zombie is not None:
            world.zombies[zombie.zombie_id] = zombie
    for corpse_data in world_data.get("corpses", []):
        corpse = _corpse_from_dict(_as_dict(corpse_data), locations)
        if corpse is not None:
            world.corpses[corpse.corpse_id] = corpse

    player = _player_from_dict(data.get("player", {}), locations)
    npcs = _npcs_from_dict(data.get("npcs", []))
    relationships = _relationships_from_dict(data.get("relationships", {}))

    narrative_data = data.get("narrative", {})
    default_goals = {"short_term": [], "long_term": []}
    narrative = NarrativeState(
        minutes=narrative_data.get("minutes", 0),
        goals={**default_goals, **narrative_data.get("goals", {})},
        flags=narrative_data.get("flags", {}),
        discovered_flags=set(narrative_data.get("discovered_flags", [])),
        pending_corrections=narrative_data.get("pending_corrections", []),
        game_over=_as_bool(narrative_data.get("game_over", False)),
        death_cause=_as_text(narrative_data.get("death_cause", ""), DEATH_CAUSE_MAX_LENGTH),
        social_log=_social_log_from_dict(narrative_data.get("social_log")),
    )

    memory_data = data.get("memory", {})
    memory = MemoryState(
        recent_events=memory_data.get("recent_events", []),
        full_event_log=memory_data.get("full_event_log", []),
        summaries=memory_data.get("summaries", []),
        last_story=_as_text(memory_data.get("last_story", ""), LAST_STORY_MAX_LENGTH),
    )

    quests = _quests_from_dict(data.get("quests", {}), player, narrative, npcs)

    return GameManager(
        world=world,
        player=player,
        relationship_manager=relationships,
        npcs=npcs,
        narrative=narrative,
        memory=memory,
        quests=quests,
        climate=_climate_from_dict(world.seed, narrative.minutes, _as_dict(data.get("weather"))),
    )


def _reconcile_seeded_quests(
    quests: dict[str, QuestState],
    player: PlayerEntity,
    narrative: NarrativeState,
    npcs: dict[str, Any],
) -> None:
    """Mark objectives a freshly seeded roster has already satisfied.

    Only for quests seeded into an existing save (see from_dict). Objective
    keys fire on the transition, not the condition, so state reached before
    the quest existed would otherwise never tick. This mirrors the checks in
    SimulationCore -- keep the two in step when adding an objective type.
    """
    carried = [
        entity
        for entity in [*player.inventory, *player.equipment.values(), *player.worn.values()]
        if entity is not None
    ]
    held = {entity.item.id for entity in carried}
    holds_weapon = any(isinstance(entity.item, MeleeWeaponItem) for entity in carried)

    def is_satisfied(objective: str) -> bool:
        kind, _, rest = objective.partition(":")
        if kind == "take":
            return holds_weapon if objective == TAKE_ANY_WEAPON else rest in held
        if kind == "reach":
            return rest == player.current_location_id
        if kind == "discover":
            return rest in narrative.discovered_flags
        if kind == "defeat":
            npc = npcs.get(rest)
            return npc is not None and npc.hit_points <= 0
        if kind == "npc_status":
            npc_id, _, status = rest.partition(":")
            npc = npcs.get(npc_id)
            return npc is not None and status in npc.status
        return False

    for quest in quests.values():
        for objective in quest.objectives:
            if objective not in quest.completed_objectives and is_satisfied(objective):
                quest.completed_objectives.append(objective)
        if quest.is_complete():
            quest.status = QuestStatus.COMPLETED


def _quests_from_dict(
    quest_entries: Any,
    player: PlayerEntity,
    narrative: NarrativeState,
    npcs: dict[str, Any],
) -> dict[str, QuestState]:
    """Build the quest roster from a save, seeding any roster quest missing.

    A save with no "quests" key at all -- a brand-new game, or one written
    before quest content existed -- is the extreme case of this: every
    roster quest is "missing" and all of them get seeded, same fallback
    build_starting_npcs() uses for an empty "npcs" list. A v2->v3 migration,
    or a save hand-edited to drop a quest, only has some missing; either way
    quests already present are kept exactly as saved -- only the newly
    seeded ones are reconciled against loaded state (see
    _reconcile_seeded_quests), never one the save already has its own
    completed_objectives for.

    `quest_entries` is `Any`, not `dict`, on purpose: a hand-edited save can
    hold `"quests": null` or `"quests": []`, which must seed the whole
    roster exactly like a missing key, not crash on `.items()`.
    """
    quests: dict[str, QuestState] = {}
    for quest_id, raw in _as_dict(quest_entries).items():
        quest_data = _as_dict(raw)
        quests[quest_id] = QuestState(
            quest_id=quest_id,
            title=quest_data.get("title", ""),
            status=QuestStatus(quest_data.get("status", "active")),
            objectives=list(quest_data.get("objectives") or []),
            objective_labels=_as_dict(quest_data.get("objective_labels")),
            completed_objectives=list(quest_data.get("completed_objectives") or []),
        )
    missing = {
        quest_id: quest
        for quest_id, quest in build_starting_quests().items()
        if quest_id not in quests
    }
    if missing:
        quests.update(missing)
        _reconcile_seeded_quests(missing, player, narrative, npcs)
    return quests


def _player_from_dict(data: dict[str, Any], locations: dict[str, Any]) -> PlayerEntity:
    location_id = data.get("current_location_id", STARTING_ZONE_ID)
    if location_id not in locations:
        logger.warning(f"Unknown player location '{location_id}'; using {STARTING_ZONE_ID}.")
        location_id = STARTING_ZONE_ID

    equipment: dict[Any, ItemEntity | None] = {
        **{slot: None for slot in CharacterHoldableSlot},
        **{slot: None for slot in CharacterArmorSlot},
    }
    for slot_name, item_data in data.get("equipment", {}).items():
        slot = _slot_from_value(slot_name)
        if slot is None:
            logger.warning(f"Dropping unknown equipment slot '{slot_name}'.")
            continue
        equipment[slot] = _item_entity_from_dict(item_data) if item_data else None

    worn = _worn_from_dict(data.get("worn"))

    conditions = []
    for name in data.get("conditions", []):
        try:
            conditions.append(CharacterCondition(name))
        except ValueError:
            logger.warning(f"Dropping unknown condition '{name}'.")

    player = PlayerEntity(
        name=data.get("name", ""),
        current_location_id=location_id,
        current_place=_as_text(data.get("current_place", ""), MAX_PLACE_LENGTH),
        current_room=_optional_text(data.get("current_room")),
        entity_id=data.get("entity_id", "player"),
        inventory=[
            entity
            for entity in (_item_entity_from_dict(i) for i in data.get("inventory", []))
            if entity is not None
        ],
        stats=Stats.from_dict(data.get("stats", {})),
        thermal=ThermalState.from_dict(_as_dict(data.get("thermal"))),
        asleep=_as_bool(data.get("asleep", False)),
        sneaking=_as_bool(data.get("sneaking", False)),
        body=_body_from_dict(data.get("body")),
        zombie_infection_since=_optional_float(data.get("zombie_infection_since")),
        zombie_infection_hours=float(data.get("zombie_infection_hours", 0.0)),
        pain_effect_minutes=float(data.get("pain_effect_minutes", 0.0)),
        reduce_infection_power=float(data.get("reduce_infection_power", 0.0)),
        food_eaten_timer=float(data.get("food_eaten_timer", 0.0)),
        appearance=_appearance_from_dict(_as_dict(data.get("appearance"))),
        occupation_id=_as_text(data.get("occupation_id", ""), MAX_ID_LENGTH),
        job_title=_as_text(data.get("job_title", ""), creation_k.JOB_TITLE_MAX_CHARS),
        traits=_known_trait_ids(data.get("trait_ids", [])),
        skills=_skills_from_dict(data.get("skills")),
        skill_boosts=_int_map(data.get("skill_boosts")),
        loss_timers=_float_map(data.get("loss_timers"), SKILLS),
        loss_timer_steps={
            skill_id: int(step)
            for skill_id, step in _as_dict(data.get("loss_timer_steps")).items()
            if skill_id in SKILLS
        },
        exercise=_exercise_from_dict(_as_dict(data.get("exercise"))),
        conditions=conditions,
        zombie_kills=max(0, int(data.get("zombie_kills", 0))),
        at_barrier=_optional_text(data.get("at_barrier")),
        carrying_corpse=_optional_text(data.get("carrying_corpse")),
        carrying_skeleton=_as_bool(data.get("carrying_skeleton", False)),
    )
    player.equipment = equipment
    player.worn = worn
    return player


def _npcs_from_dict(entries: list[dict[str, Any]]) -> dict[str, NpcEntity]:
    if not entries:
        return build_starting_npcs()

    npcs: dict[str, NpcEntity] = {}
    for entry in entries:
        conditions = []
        for name in entry.get("conditions", []):
            try:
                conditions.append(CharacterCondition(name))
            except ValueError:
                logger.warning(f"Dropping unknown NPC condition '{name}'.")

        try:
            faction = CharacterFaction(entry.get("faction", "neutral"))
        except ValueError:
            faction = CharacterFaction.NEUTRAL

        npc = NpcEntity(
            npc_id=entry["npc_id"],
            name=entry.get("name", entry["npc_id"]),
            description=entry.get("description", ""),
            current_location_id=entry.get("current_location_id", "zone_building"),
            age=entry.get("age"),
            faction=faction,
            personality=entry.get("personality", []),
            status=entry.get("status", []),
            notes=entry.get("notes", ""),
            romance_eligible=entry.get("romance_eligible", False),
            conditions=conditions,
            inventory=[
                e
                for e in (_item_entity_from_dict(i) for i in entry.get("inventory", []))
                if e is not None
            ],
            base_max_hit_points=entry.get("base_max_hit_points", 100),
            goals=entry.get("goals", []),
            knowledge=set(entry.get("knowledge", [])),
            following=_as_bool(entry.get("following", False)),
        )
        npc.hit_points = int(entry.get("hit_points", npc.max_hit_points))
        npcs[npc.npc_id] = npc
    return npcs


def _relationships_from_dict(data: dict[str, Any]) -> RelationshipManager:
    reputations: dict[CharacterFaction, dict[CharacterFaction, int]] = {}
    for source, targets in data.get("reputations", {}).items():
        try:
            source_faction = CharacterFaction(source)
        except ValueError:
            continue
        resolved: dict[CharacterFaction, int] = {}
        for target, score in targets.items():
            try:
                resolved[CharacterFaction(target)] = int(score)
            except ValueError:
                continue
        reputations[source_faction] = resolved

    return RelationshipManager(
        affinities={k: dict(v) for k, v in data.get("affinities", {}).items()},
        reputations=reputations,
        trusts={k: dict(v) for k, v in data.get("trusts", {}).items()},
    )
