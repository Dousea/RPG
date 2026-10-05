"""Save and load a GameManager as JSON.

Only *dynamic* state is persisted. Static definitions -- item stats, location
names and connections, trait and perk effects -- stay in `data/` and are looked
up by id on load. That keeps saves small and lets content be rebalanced without
invalidating them.

A v2 save (main's four rooms, not zones) is migrated to v3 by
`migrate_v2_to_v3`. Any other version mismatch is discarded and a new game is
started, rather than being loaded half-understood.
"""

import copy
import json
import logging
import os
from typing import Any

import config
from data.items import ITEMS
from data.locations import STARTING_ZONE_ID, build_starting_locations
from data.npcs import build_starting_npcs
from data.perks import PERKS
from data.quests import build_starting_quests
from data.traits import TRAITS
from managers.game import (
    DEATH_CAUSE_MAX_LENGTH,
    MAX_PLACE_LENGTH,
    GameManager,
    MemoryState,
    NarrativeState,
)
from managers.relationship import RelationshipManager
from modules.action import normalize_key
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

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 3

GAME_DATA_DIR = config.persistence.game_data_dir
SAVE_FILE = os.path.join(GAME_DATA_DIR, config.persistence.save_file_name)

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


def _as_list(value: Any) -> list[Any]:
    """As `_as_dict`, for fields that should be a list."""
    return value if isinstance(value, list) else []


def _ensure_dict(container: dict[str, Any], key: str) -> dict[str, Any]:
    """Like `dict.setdefault(key, {})`, but also replaces a present-but-wrong
    value (e.g. an explicit `null`) -- `setdefault` only fills in a *missing*
    key, so a save with `"player": null` would otherwise pass `None` through
    untouched."""
    value = container.get(key)
    if not isinstance(value, dict):
        value = {}
        container[key] = value
    return value


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
            "current_place": player.current_place,
            "hit_points": player.hit_points,
            "experience_points": player.experience_points,
            "level": player.level,
            "max_inventory_size": player.max_inventory_size,
            "hunger": player.hunger,
            "thirst": player.thirst,
            "morale": player.morale,
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
        "narrative": {
            "day": narrative.day,
            "time_of_day": narrative.time_of_day,
            "apocalypse_stage": narrative.apocalypse_stage,
            "goals": {k: list(v) for k, v in narrative.goals.items()},
            "flags": dict(narrative.flags),
            "discovered_flags": sorted(narrative.discovered_flags),
            "player_status": list(narrative.player_status),
            "conditions": dict(narrative.conditions),
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
        discovered_flags=set(narrative_data.get("discovered_flags", [])),
        player_status=narrative_data.get("player_status", []),
        conditions={
            "sleep": "Rested",
            "infection_risk": "No",
            **narrative_data.get("conditions", {}),
        },
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
        hunger=data.get("hunger", 100),
        thirst=data.get("thirst", 100),
        morale=data.get("morale", 100),
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


# === v2 -> v3 migration ===

# v2 saves name main's four rooms. All four were parts of one building, so
# they collapse onto one zone; the old room survives as the player's spot.
_V2_LOCATION_IDS = {
    "location_id_hallway": "zone_building",
    "location_id_office": "zone_building",
    "location_id_lobby": "zone_building",
    "location_id_storage": "zone_building",
}
_V2_ROOM_PLACES = {
    "location_id_hallway": "the hallway",
    "location_id_office": "the office",
    "location_id_lobby": "the lobby",
    "location_id_storage": "the storage room",
}

# A v2 quest that v3's roster does not include.
_V2_RETIRED_QUEST_ID = "quest_storage_room"

# The only location ids that survive from_dict's location lookup after
# migration. Used to decide whether a ground item (or, via the same remap,
# an NPC's position) will actually still exist once loading finishes --
# counting one that from_dict is about to drop anyway would only suppress a
# new zone's own starting copy of it for nothing.
#
# Derived from the world rather than a hard-coded literal, so adding,
# renaming, or removing a zone in data/locations.py can't silently desync
# this set from the actual map.
_V3_ZONE_IDS = frozenset(build_starting_locations().keys())


def _v2_remap_location(location_id: Any) -> Any:
    return _V2_LOCATION_IDS.get(location_id, location_id)


def _v2_items_present_anywhere(data: dict[str, Any]) -> set[str]:
    """Every item id the v2 save already accounts for -- but only counting
    an item where it will actually survive loading. An item under a ground
    location id that maps to nothing real, or in an equipment slot name
    `_slot_from_value` can't resolve, is dropped by `from_dict` regardless
    of what this function says; counting it here would suppress a new
    zone's starting copy of an item the save is about to lose anyway (see
    `_migrate_v2_ground_items`, `_migrate_v2_apartment_key`).
    """
    ids: set[str] = set()
    player = _as_dict(data.get("player"))
    for entry in _as_list(player.get("inventory")):
        if isinstance(entry, dict):
            ids.add(entry.get("item_id"))
    for slot_name, entry in _as_dict(player.get("equipment")).items():
        if isinstance(entry, dict) and _slot_from_value(slot_name) is not None:
            ids.add(entry.get("item_id"))
    for npc in _as_list(data.get("npcs")):
        for entry in _as_list(_as_dict(npc).get("inventory")):
            if isinstance(entry, dict):
                ids.add(entry.get("item_id"))
    ground_items = _as_dict(_as_dict(data.get("world")).get("ground_items"))
    for location_id, items in ground_items.items():
        if _v2_remap_location(location_id) not in _V3_ZONE_IDS:
            continue
        for entry in _as_list(items):
            if isinstance(entry, dict):
                ids.add(entry.get("item_id"))
    ids.discard(None)
    return ids


def _migrate_v2_player_location(data: dict[str, Any]) -> None:
    player = _ensure_dict(data, "player")
    old_id = player.get("current_location_id", STARTING_ZONE_ID)
    player["current_location_id"] = _v2_remap_location(old_id)
    # A v2 room id becomes the player's spot inside the zone it collapsed
    # into. Anything else -- no current_location_id at all, or (the
    # zones-branch v2 saves parked as out of scope, see task-5-fix-round-1.md
    # P2) an id that is already a zone -- is left as whatever current_place
    # the save already carried, not overwritten with "".
    if old_id in _V2_ROOM_PLACES:
        player["current_place"] = _V2_ROOM_PLACES[old_id]
    else:
        player["current_place"] = _as_text(player.get("current_place"), MAX_PLACE_LENGTH)


def _migrate_v2_npc_locations(data: dict[str, Any]) -> None:
    for npc in _as_list(data.get("npcs")):
        if isinstance(npc, dict):
            npc["current_location_id"] = _v2_remap_location(npc.get("current_location_id", ""))


def _migrate_v2_ground_items(data: dict[str, Any], items_elsewhere: set[str]) -> None:
    world = _ensure_dict(data, "world")
    old_ground = _as_dict(world.get("ground_items"))

    # v2's rooms were all parts of one building, so their items accumulate
    # onto zone_building rather than overwrite -- a plain remap would keep
    # only whichever room was written last.
    merged: dict[str, list[Any]] = {}
    for location_id, items in old_ground.items():
        merged.setdefault(_v2_remap_location(location_id), []).extend(_as_list(items))

    # The zones that did not exist in v2 (i.e. everything except
    # zone_building, per _V2_LOCATION_IDS) never had a ground_items entry --
    # give them their normal starting items, except whatever the save
    # already accounts for elsewhere (a room, the player, or an NPC);
    # otherwise e.g. the street's crowbar would duplicate one the player is
    # already carrying. zone_building is deliberately excluded from this
    # loop: it gets only the items accumulated above, not a fresh starting
    # First Aid Kit too -- the v2 building already had one, or the player
    # already took it, either way it's already accounted for by the
    # accumulation. Derived from _V3_ZONE_IDS minus the v2 rooms'
    # targets, rather than a hard-coded tuple of the three names.
    starting = build_starting_locations()
    new_zone_ids = [zone_id for zone_id in starting if zone_id not in _V2_LOCATION_IDS.values()]
    for zone_id in new_zone_ids:
        fresh = [
            _item_entity_to_dict(entity)
            for entity in starting[zone_id].entities
            if isinstance(entity, ItemEntity) and entity.item.id not in items_elsewhere
        ]
        merged.setdefault(zone_id, []).extend(fresh)

    world["ground_items"] = merged


def _migrate_v2_apartment_key(data: dict[str, Any], items_elsewhere: set[str]) -> None:
    if "item_apartment_key" in items_elsewhere:
        return
    player = _ensure_dict(data, "player")
    # Not setdefault: an explicit `"inventory": null` must still end up a
    # list, not be left as None for `.append` to crash on.
    inventory = player.get("inventory") or []
    player["inventory"] = inventory
    # Added even if the inventory is already at max_inventory_size: a key
    # must not be lost to a capacity rule, or a migrated player is locked out
    # of his own home forever (see data/locations.py's apartment_door).
    inventory.append(_item_entity_to_dict(ItemEntity(item=ITEMS["item_apartment_key"])))


def _migrate_v2_narrative(data: dict[str, Any]) -> None:
    narrative = _ensure_dict(data, "narrative")
    # v2 predates both fields.
    narrative.setdefault("game_over", False)
    narrative.setdefault("death_cause", "")

    # SET_FLAG/DISCOVER_FLAG normalize flag names; a v2 save's
    # "PowerGrid" would otherwise sit beside a new "powergrid". Coerced to
    # str first: a discovered_flags entry is player-writable content
    # (SET_FLAG/DISCOVER_FLAG arguments) that a hand-edited save could hold
    # as a non-string (e.g. a bare number), and normalize_key() calls
    # .strip() -- an AttributeError, not a clean "unknown flag".
    normalized_flags: dict[str, bool] = {}
    for key, value in _as_dict(narrative.get("flags")).items():
        normalized_flags[normalize_key(str(key))] = value  # later value wins on collision
    narrative["flags"] = normalized_flags
    narrative["discovered_flags"] = sorted(
        {normalize_key(str(flag)) for flag in _as_list(narrative.get("discovered_flags"))}
    )


def _v2_remap_reach_objective(key: Any) -> Any:
    if not isinstance(key, str):
        return key
    kind, sep, rest = key.partition(":")
    if kind == "reach" and sep:
        return f"reach:{_v2_remap_location(rest)}"
    return key


def _remap_objective_keys(values: Any) -> list[Any]:
    """Remap and dedupe an objectives/completed_objectives list, null-safe."""
    return list(dict.fromkeys(_v2_remap_reach_objective(v) for v in values or []))


def _migrate_v2_quests(data: dict[str, Any]) -> None:
    quests = data.get("quests")
    if not isinstance(quests, dict):
        return
    quests.pop(_V2_RETIRED_QUEST_ID, None)

    for quest in quests.values():
        if not isinstance(quest, dict):
            continue
        quest["objectives"] = _remap_objective_keys(quest.get("objectives"))
        quest["completed_objectives"] = _remap_objective_keys(quest.get("completed_objectives"))
        quest["objective_labels"] = {
            _v2_remap_reach_objective(key): label
            for key, label in _as_dict(quest.get("objective_labels")).items()
        }
        # Remapping can collapse two distinct reach objectives onto the same
        # zone (e.g. reach:location_id_hallway and reach:location_id_office
        # both -> reach:zone_building) where one was already completed --
        # without this the quest is done but stuck ACTIVE forever.
        if all(o in quest["completed_objectives"] for o in quest["objectives"]):
            quest["status"] = "completed"
    # Any roster quest still missing (quest_supply_run, at minimum -- v2
    # predates the current roster) is left out here on purpose: from_dict's
    # _quests_from_dict seeds and reconciles whatever roster quest a save
    # doesn't mention, the same as it would for an empty "quests" dict.


def migrate_v2_to_v3(data: dict[str, Any]) -> dict[str, Any]:
    """Rewrite a v2 (room-based) save onto the zone map.

    Without this the version gate would discard the save outright and the
    player would silently lose their game to what is really a content
    change. Does not mutate `data` -- `import_save` passes user-uploaded data
    the caller may still hold a reference to.
    """
    data = copy.deepcopy(data)

    items_elsewhere = _v2_items_present_anywhere(data)
    _migrate_v2_player_location(data)
    _migrate_v2_npc_locations(data)
    _migrate_v2_ground_items(data, items_elsewhere)
    _migrate_v2_apartment_key(data, items_elsewhere)
    _migrate_v2_narrative(data)
    _migrate_v2_quests(data)

    data["version"] = 3
    return data


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


def from_saved_data(data: dict[str, Any]) -> GameManager | None:
    """Validate parsed save JSON and build a GameManager from it, or None.

    Shared by `load` (reads the autosave off disk) and the `/save/import`
    route (reads a file the player uploaded) -- both need the same schema
    check and the same "don't half-load a corrupt save" guard.
    """
    # Migration runs inside the same guarded region as the rest of loading:
    # a malformed v2 save (a null where a list or dict was expected, an
    # unhashable id, ...) must degrade to "corrupt save -> None" the same
    # way a malformed v3 save already does, not crash GameEngine.__init__ or
    # the /save/import route out from under the caller. AttributeError is
    # caught alongside the pre-existing KeyError/TypeError/ValueError
    # because it's the shape a `None.strip()`/`None.partition()` failure
    # takes when a hand-edited field holds the wrong type.
    try:
        version = data.get("version")
        if version == 2:
            logger.info("Migrating save v2 -> v3 (rooms became zones).")
            data = migrate_v2_to_v3(data)
            version = data.get("version")
        if version != SCHEMA_VERSION:
            logger.warning(f"Save schema v{version} != v{SCHEMA_VERSION}; rejecting.")
            return None
        return from_dict(data)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        logger.warning(f"Corrupt save: {exc}.")
        return None


def load(path: str | None = None) -> GameManager | None:
    """Load a saved game, or return None if there is no usable save."""
    path = path or SAVE_FILE
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(f"Could not read save at {path}: {exc}")
        return None

    return from_saved_data(data)


def delete(path: str | None = None) -> None:
    path = path or SAVE_FILE
    if os.path.exists(path):
        os.remove(path)
