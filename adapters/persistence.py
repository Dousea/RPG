"""Save and load a GameManager as JSON.

Only *dynamic* state is persisted. Static definitions -- item stats, location
names and connections, trait and perk effects -- stay in `data/` and are looked
up by id on load. That keeps saves small and lets content be rebalanced without
invalidating them.

A save whose `version` does not match SCHEMA_VERSION is discarded and a new game
is started, rather than being loaded half-understood.
"""

import json
import os
from typing import Any

from data.items import ITEMS
from data.locations import build_starting_locations
from data.npcs import build_starting_npcs
from data.perks import PERKS
from data.traits import TRAITS
from managers.game import GameManager, MemoryState, NarrativeState
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

SCHEMA_VERSION = 1

GAME_DATA_DIR = "gamedata"
SAVE_FILE = os.path.join(GAME_DATA_DIR, "engine_state.json")

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


def _item_entity_to_dict(entity: ItemEntity) -> dict[str, Any]:
    return {"item_id": entity.item.id, "hit_points": entity.hit_points}


def _item_entity_from_dict(data: dict[str, Any]) -> ItemEntity | None:
    item = ITEMS.get(data.get("item_id", ""))
    if item is None:
        print(f"[Persistence] Dropping unknown item id '{data.get('item_id')}'.")
        return None
    entity = ItemEntity(item=item)
    # __post_init__ sets full health; restore the saved condition over it.
    entity.hit_points = int(data.get("hit_points", entity.max_hit_points))
    return entity


# === Serialization ===


def to_dict(manager: GameManager) -> dict[str, Any]:
    player = manager.player
    narrative = manager.narrative
    memory = manager.memory

    return {
        "version": SCHEMA_VERSION,
        "world": {
            "time": manager.world.time,
            "date": manager.world.date,
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
            "hit_points": player.hit_points,
            "experience_points": player.experience_points,
            "level": player.level,
            "max_inventory_size": player.max_inventory_size,
            "hunger": player.hunger,
            "thirst": player.thirst,
            "morale": player.morale,
            "attributes": {
                attribute.value: value
                for attribute, value in player.attributes.items()
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
                source.value: {
                    target.value: score for target, score in targets.items()
                }
                for source, targets in manager.relationship_manager.reputations.items()
            },
        },
        "narrative": {
            "day": narrative.day,
            "time_of_day": narrative.time_of_day,
            "apocalypse_stage": narrative.apocalypse_stage,
            "goals": {k: list(v) for k, v in narrative.goals.items()},
            "flags": dict(narrative.flags),
            "player_status": list(narrative.player_status),
            "conditions": dict(narrative.conditions),
        },
        "memory": {
            "recent_events": list(memory.recent_events),
            "full_event_log": list(memory.full_event_log),
            "summaries": list(memory.summaries),
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
            entity
            for entity in location.entities
            if not isinstance(entity, ItemEntity)
        ]
    for location_id, items in world_data.get("ground_items", {}).items():
        location = locations.get(location_id)
        if location is None:
            print(f"[Persistence] Dropping items for unknown location '{location_id}'.")
            continue
        for item_data in items:
            entity = _item_entity_from_dict(item_data)
            if entity is not None:
                location.entities.append(entity)

    world = World(
        time=world_data.get("time", "12:00 PM"),
        date=world_data.get("date", "2023-10-01"),
        locations=locations,
    )

    player = _player_from_dict(data.get("player", {}), locations)
    npcs = _npcs_from_dict(data.get("npcs", []))
    relationships = _relationships_from_dict(data.get("relationships", {}))

    narrative_data = data.get("narrative", {})
    default_goals = {"short_term": [], "long_term": []}
    narrative = NarrativeState(
        day=narrative_data.get("day", 1),
        time_of_day=narrative_data.get("time_of_day", "morning"),
        apocalypse_stage=narrative_data.get("apocalypse_stage", "Normal"),
        goals={**default_goals, **narrative_data.get("goals", {})},
        flags=narrative_data.get("flags", {}),
        player_status=narrative_data.get("player_status", []),
        conditions={
            "sleep": "Rested",
            "infection_risk": "No",
            **narrative_data.get("conditions", {}),
        },
    )

    memory_data = data.get("memory", {})
    memory = MemoryState(
        recent_events=memory_data.get("recent_events", []),
        full_event_log=memory_data.get("full_event_log", []),
        summaries=memory_data.get("summaries", []),
    )

    return GameManager(
        world=world,
        player=player,
        relationship_manager=relationships,
        npcs=npcs,
        narrative=narrative,
        memory=memory,
    )


def _player_from_dict(data: dict[str, Any], locations: dict[str, Any]) -> PlayerEntity:
    location_id = data.get("current_location_id", "location_id_hallway")
    if location_id not in locations:
        print(f"[Persistence] Unknown player location '{location_id}'; using hallway.")
        location_id = "location_id_hallway"

    attributes = {}
    for name, value in data.get("attributes", {}).items():
        try:
            attributes[PlayerAttribute(name)] = int(value)
        except ValueError:
            print(f"[Persistence] Dropping unknown attribute '{name}'.")

    equipment: dict[Any, ItemEntity | None] = {
        **{slot: None for slot in CharacterHoldableSlot},
        **{slot: None for slot in CharacterArmorSlot},
        **{slot: None for slot in CharacterAccessorySlot},
    }
    for slot_name, item_data in data.get("equipment", {}).items():
        slot = _slot_from_value(slot_name)
        if slot is None:
            print(f"[Persistence] Dropping unknown equipment slot '{slot_name}'.")
            continue
        equipment[slot] = _item_entity_from_dict(item_data) if item_data else None

    conditions = []
    for name in data.get("conditions", []):
        try:
            conditions.append(CharacterCondition(name))
        except ValueError:
            print(f"[Persistence] Dropping unknown condition '{name}'.")

    player = PlayerEntity(
        name=data.get("name", "Orton"),
        current_location_id=location_id,
        entity_id=data.get("entity_id", "player"),
        experience_points=data.get("experience_points", 0),
        level=data.get("level", 1),
        max_inventory_size=data.get("max_inventory_size", 20),
        inventory=[
            entity
            for entity in (
                _item_entity_from_dict(i) for i in data.get("inventory", [])
            )
            if entity is not None
        ],
        hunger=data.get("hunger", 100),
        thirst=data.get("thirst", 100),
        morale=data.get("morale", 100),
        traits=[
            TRAITS[trait_id] for trait_id in data.get("trait_ids", []) if trait_id in TRAITS
        ],
        perks=[
            PERKS[perk_id] for perk_id in data.get("perk_ids", []) if perk_id in PERKS
        ],
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
                print(f"[Persistence] Dropping unknown NPC condition '{name}'.")

        try:
            faction = CharacterFaction(entry.get("faction", "neutral"))
        except ValueError:
            faction = CharacterFaction.NEUTRAL

        npc = NpcEntity(
            npc_id=entry["npc_id"],
            name=entry.get("name", entry["npc_id"]),
            description=entry.get("description", ""),
            current_location_id=entry.get("current_location_id", "location_id_hallway"),
            age=entry.get("age"),
            faction=faction,
            personality=entry.get("personality", []),
            status=entry.get("status", []),
            notes=entry.get("notes", ""),
            romance_eligible=entry.get("romance_eligible", False),
            conditions=conditions,
            inventory=[
                e
                for e in (
                    _item_entity_from_dict(i) for i in entry.get("inventory", [])
                )
                if e is not None
            ],
            base_max_hit_points=entry.get("base_max_hit_points", 100),
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


# === File I/O ===


def save(manager: GameManager, path: str | None = None) -> None:
    # Resolved at call time, not bound as a default, so SAVE_FILE stays
    # overridable (tests, alternate save slots).
    path = path or SAVE_FILE
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    # Write to a temp file then replace, so a crash mid-write cannot leave a
    # truncated save behind.
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(to_dict(manager), handle, indent=2)
    os.replace(temp_path, path)


def load(path: str | None = None) -> GameManager | None:
    """Load a saved game, or return None if there is no usable save."""
    path = path or SAVE_FILE
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[Persistence] Could not read save at {path}: {exc}")
        return None

    version = data.get("version")
    if version != SCHEMA_VERSION:
        print(
            f"[Persistence] Save schema v{version} != v{SCHEMA_VERSION}; starting fresh."
        )
        return None

    try:
        return from_dict(data)
    except (KeyError, TypeError, ValueError) as exc:
        print(f"[Persistence] Corrupt save at {path}: {exc}. Starting fresh.")
        return None


def delete(path: str | None = None) -> None:
    path = path or SAVE_FILE
    if os.path.exists(path):
        os.remove(path)
