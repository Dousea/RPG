"""A GameManager as a JSON-ready dict, and back.

Only *dynamic* state is saved. Static definitions -- item stats, location
names and connections, trait and perk effects -- stay in `data/` and are looked
up by id on load. That keeps saves small and lets content be rebalanced without
invalidating them.
"""

import dataclasses
import logging
from typing import Any

from data.climate import STAGE_PHRASES
from data.clock import WORLD_START_MINUTE_OF_DAY
from data.items import ITEMS
from data.locations import STARTING_ZONE_ID, build_starting_locations
from data.npcs import build_starting_npcs
from data.perks import PERKS
from data.quests import build_starting_quests
from data.traits import TRAITS
from managers.climate import ClimateEngine
from managers.game import (
    DEATH_CAUSE_MAX_LENGTH,
    MAX_PLACE_LENGTH,
    WORLD_START_DATE,
    GameManager,
    MemoryState,
    NarrativeState,
)
from managers.relationship import RelationshipManager
from modules.character.equipment import (
    CharacterAccessorySlot,
    CharacterArmorSlot,
    CharacterHoldableSlot,
)
from modules.character.faction import CharacterFaction
from modules.character.player import PlayerAttribute
from modules.character.state import CharacterCondition
from modules.entity.item import ItemEntity
from modules.entity.npc import NpcEntity
from modules.entity.player import PlayerEntity
from modules.location import World
from modules.quest import QuestState, QuestStatus
from modules.stats import Stats
from modules.weather import AirFront, PeriodStage, WeatherPeriod

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 7  # spec 04


# Equipment slots are three separate enums; this resolves a saved slot name back
# to the right one.
_SLOT_ENUMS = (CharacterHoldableSlot, CharacterArmorSlot, CharacterAccessorySlot)


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


def _item_entity_to_dict(entity: ItemEntity) -> dict[str, Any]:
    return {"item_id": entity.item.id, "hit_points": entity.hit_points}


def _item_entity_from_dict(data: dict[str, Any]) -> ItemEntity | None:
    item = ITEMS.get(data.get("item_id", ""))
    if item is None:
        logger.warning(f"Dropping unknown item id '{data.get('item_id')}'.")
        return None
    entity = ItemEntity(item=item)
    # __post_init__ sets full health; restore the saved condition over it.
    entity.hit_points = int(data.get("hit_points", entity.max_hit_points))
    return entity


# === Serialization ===


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

    return {
        "version": SCHEMA_VERSION,
        "world": {
            "time": manager.world.time,
            "date": manager.world.date,
            "seed": manager.world.seed,
            # Locations themselves are static; only ground items move.
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
            "hit_points": player.hit_points,
            "experience_points": player.experience_points,
            "level": player.level,
            "max_inventory_size": player.max_inventory_size,
            "stats": player.stats.to_dict(),
            "asleep": player.asleep,
            "fractional_hp_loss": player.fractional_hp_loss,
            "food_eaten_timer": player.food_eaten_timer,
            "attributes": {
                attribute.value: value for attribute, value in player.attributes.items()
            },
            "inventory": [_item_entity_to_dict(e) for e in player.inventory],
            "equipment": {
                slot.value: (_item_entity_to_dict(entity) if entity else None)
                for slot, entity in player.equipment.items()
            },
            "trait_ids": [trait.id for trait in player.traits],
            "perk_ids": [perk.id for perk in player.perks],
            "conditions": [condition.value for condition in player.conditions],
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
            "apocalypse_stage": narrative.apocalypse_stage,
            "goals": {k: list(v) for k, v in narrative.goals.items()},
            "flags": dict(narrative.flags),
            "discovered_flags": sorted(narrative.discovered_flags),
            "player_status": list(narrative.player_status),
            "pending_corrections": list(narrative.pending_corrections),
            "game_over": narrative.game_over,
            "death_cause": narrative.death_cause,
        },
        "memory": {
            "recent_events": list(memory.recent_events),
            "full_event_log": list(memory.full_event_log),
            "summaries": list(memory.summaries),
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

    # World.time/date are derived from the narrative clock, which GameManager
    # re-renders on construction. The saved values are carried over so a save is
    # still readable on its own, but they are not trusted.
    world = World(
        time=world_data.get("time", "12:00 PM"),
        date=world_data.get("date", "2023-10-01"),
        seed=int(world_data.get("seed", 0)),
        locations=locations,
    )

    player = _player_from_dict(data.get("player", {}), locations)
    npcs = _npcs_from_dict(data.get("npcs", []))
    relationships = _relationships_from_dict(data.get("relationships", {}))

    narrative_data = data.get("narrative", {})
    default_goals = {"short_term": [], "long_term": []}
    narrative = NarrativeState(
        minutes=narrative_data.get("minutes", 0),
        apocalypse_stage=narrative_data.get("apocalypse_stage", "Normal"),
        goals={**default_goals, **narrative_data.get("goals", {})},
        flags=narrative_data.get("flags", {}),
        discovered_flags=set(narrative_data.get("discovered_flags", [])),
        player_status=narrative_data.get("player_status", []),
        pending_corrections=narrative_data.get("pending_corrections", []),
        game_over=_as_bool(narrative_data.get("game_over", False)),
        death_cause=_as_text(narrative_data.get("death_cause", ""), DEATH_CAUSE_MAX_LENGTH),
    )

    memory_data = data.get("memory", {})
    memory = MemoryState(
        recent_events=memory_data.get("recent_events", []),
        full_event_log=memory_data.get("full_event_log", []),
        summaries=memory_data.get("summaries", []),
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
    held = {
        entity.item.id
        for entity in [*player.inventory, *player.equipment.values()]
        if entity is not None
    }

    def is_satisfied(objective: str) -> bool:
        kind, _, rest = objective.partition(":")
        if kind == "take":
            return rest in held
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

    attributes = {}
    for name, value in data.get("attributes", {}).items():
        try:
            attributes[PlayerAttribute(name)] = int(value)
        except ValueError:
            logger.warning(f"Dropping unknown attribute '{name}'.")

    equipment: dict[Any, ItemEntity | None] = {
        **{slot: None for slot in CharacterHoldableSlot},
        **{slot: None for slot in CharacterArmorSlot},
        **{slot: None for slot in CharacterAccessorySlot},
    }
    for slot_name, item_data in data.get("equipment", {}).items():
        slot = _slot_from_value(slot_name)
        if slot is None:
            logger.warning(f"Dropping unknown equipment slot '{slot_name}'.")
            continue
        equipment[slot] = _item_entity_from_dict(item_data) if item_data else None

    conditions = []
    for name in data.get("conditions", []):
        try:
            conditions.append(CharacterCondition(name))
        except ValueError:
            logger.warning(f"Dropping unknown condition '{name}'.")

    player = PlayerEntity(
        name=data.get("name", "Orton"),
        current_location_id=location_id,
        current_place=_as_text(data.get("current_place", ""), MAX_PLACE_LENGTH),
        entity_id=data.get("entity_id", "player"),
        experience_points=data.get("experience_points", 0),
        level=data.get("level", 1),
        max_inventory_size=data.get("max_inventory_size", 20),
        inventory=[
            entity
            for entity in (_item_entity_from_dict(i) for i in data.get("inventory", []))
            if entity is not None
        ],
        stats=Stats.from_dict(data.get("stats", {})),
        asleep=_as_bool(data.get("asleep", False)),
        fractional_hp_loss=float(data.get("fractional_hp_loss", 0.0)),
        food_eaten_timer=float(data.get("food_eaten_timer", 0.0)),
        traits=[TRAITS[trait_id] for trait_id in data.get("trait_ids", []) if trait_id in TRAITS],
        perks=[PERKS[perk_id] for perk_id in data.get("perk_ids", []) if perk_id in PERKS],
        conditions=conditions,
    )
    if attributes:
        player.attributes = attributes
    player.equipment = equipment
    # Set last: __post_init__ filled hit_points to max.
    player.hit_points = int(data.get("hit_points", player.max_hit_points))
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
