# Data Model and Persistence

> **Status: Partial.** Exit requirements and NPC `goals`/`knowledge` — two gaps this document used to call out explicitly — now exist. See the *As Implemented* section at the end for the real schemas, and [Implementation Status](00-status.md).

## Data Model

### 1. Player State

```json
{
  "position": {
    "region": "pnw",
    "zone": "downtown",
    "location": "pharmacy",
    "room": "pharmacy_backroom"
  },
  "condition": {
    "hp": 85,
    "stamina": 40,
    "status_effects": ["exhausted"]
  },
  "inventory": [
    {"id": "bandage", "qty": 2},
    {"id": "9mm_ammo", "qty": 12}
  ]
}
```

### 2. Room Definition

Immutable or deterministically generated.

```json
{
  "id": "pharmacy_backroom",
  "name": "Pharmacy Back Storage",
  "zone": "downtown",
  "description": "A cramped, dust-filled storage room.",
  "tags": ["indoor", "dark"],
  "exits": {
    "south": {
      "destination": "pharmacy_front",
      "requirements": []
    },
    "basement": {
      "destination": "pharmacy_cellar",
      "requirements": ["manager_keycard"]
    }
  }
}
```

### 3. Mutable State

Only persist changes from the generated/default state.

```json
{
  "room_id": "pharmacy_backroom",
  "state": {
    "zombie_count": 0,
    "noise_level": 15,
    "barricades": {
      "south_door": {
        "health": 45
      }
    },
    "loot_scavenged": true
  }
}
```

---

## Event-Oriented Persistence

A useful conceptual model is:

```text
CURRENT STATE
=
BASE DEFINITION
+
DETERMINISTIC GENERATION
+
PERSISTED MUTATIONS / EVENTS
```

Example:

```json
{
  "room_id": "pharmacy_backroom",
  "mutations": [
    {
      "event": "container_looted",
      "target": "cabinet_3",
      "time": 10420
    },
    {
      "event": "door_damaged",
      "target": "south_door",
      "value": 45,
      "time": 10428
    }
  ]
}
```

This supports:

- reproducible bugs;
- event replay;
- debugging;
- rollback;
- analytics;
- save compression;
- world-history inspection.

A production implementation may use snapshots in addition to the event log for faster loading.

---

## Exits Are Structured Data

Navigation must never depend on prose.

```json
{
  "exits": {
    "south": {
      "destination": "pharmacy_front",
      "requirements": []
    },
    "basement": {
      "destination": "pharmacy_cellar",
      "requirements": ["manager_keycard"]
    }
  }
}
```

The narrator may describe an exit only after the engine has exposed it as an observable fact.

Locked, hidden, blocked, or destroyed exits should have explicit state.

---

## NPC Architecture

NPCs should be represented by deterministic state and goals rather than by LLM memory.

Example:

```json
{
  "id": "sarah",
  "location": "pharmacy_backroom",
  "condition": {
    "hp": 54,
    "status": ["injured"]
  },
  "relationships": {
    "player": 72
  },
  "goals": [
    "survive",
    "protect_pharmacy"
  ],
  "knowledge": [
    "barricade_is_weakening",
    "heard_gunshot"
  ]
}
```

The LLM can express Sarah's personality and dialogue, but the engine owns whether she is alive, where she is, what she knows, and what she can actually do.

---

## Factions and World Systems

Factions should likewise use state and events.

```text
FACTION STATE
  reputation
  resources
  territory
  relationships
  hostility
  military strength
  morale
  known information
```

World events update these systems.

Example:

```text
player kills militia leader
       ↓
leader_died event
       ↓
faction leadership changes
       ↓
faction stability decreases
       ↓
territory policy changes
       ↓
prices and travel risks change
       ↓
NPC reactions change
```

The LLM narrates the visible consequences; it does not create them.

---

## As Implemented

The real model is in `modules/`, the starting content in `data/`, and the save
format in `adapters/save/codec.py`. It is richer than the schemas above in
some places and absent in others.

### Everything is a `BaseEntity` with hit points

`BaseEntity` gives every entity — player, NPC, item, door, container — a
`hit_points` property that self-clamps to `[0, max_hit_points]`, and an
abstract `max_hit_points` each subclass defines. For an `ItemEntity` this is
**durability**: a crowbar at 40/60 is a worn crowbar. The design documents
model item condition nowhere.

`BaseEntity.id` is `id(self)` — a memory address. It is never persisted and
never used as a key. Stable identity is `PlayerEntity.entity_id` (`"player"`)
and `NpcEntity.npc_id`.

### Player

Richer than the document's `position / condition / inventory`:

```text
name, entity_id, current_location_id
hit_points (0-100), stats (survival stats), asleep
experience_points, level
inventory: list[ItemEntity]          max_inventory_size = 20
appearance, occupation_id, job_title see mechanics/07-character-creation.md
skills, skill_boosts: {skill: int}   starting levels and boosts
equipment: {slot: ItemEntity | None} hands and the backpack slot
worn: {BodyLocation: ItemEntity}     clothing, see mechanics/05-clothing.md
traits: list[str]                    trait ids, chosen and granted
conditions: list[CharacterCondition] POISONED STUNNED BURNED FROZEN PANIC
```

There is **no stack count**. N copies of an item are N `ItemEntity` instances,
which is why `UPDATE_INVENTORY ... UPDATE_QUANTITY` adds or removes instances
to reach a target rather than setting a number.

Survival stats (hunger, thirst, fatigue and the rest) live in `PlayerEntity.stats`;
see [survival stats](mechanics/02-survival-stats.md).

### Location

Flatter than the document's region/zone/location/room hierarchy:

```python
Location(id, name, description, connections: dict[str, str], entities: list)
World(time, date, locations: dict[str, Location])
```

`connections` itself still maps a direction to a bare destination id with no
requirements field — but a requirement can now sit *alongside* it: a
`DoorEntity` placed in `Location.entities` (see `data/locations.py`'s
apartment door, on `zone_building` leading into `zone_home`) carries `leads_to`, `state`
(`UnlockableEntityLockState.LOCKED`/`UNLOCKED`) and `key_id`, and
`managers/validator.py`'s `ActionValidator` checks for one blocking a
`MOVE_TO` before accepting it. This is exits-as-structured-data for the one
case that exists (a locked door with a key), not the general
hidden/blocked/destroyed-exit model this document describes — there is still
no way to mark an exit merely hidden, or damaged rather than locked.

`World.time` and `World.date` are derived from the minute clock; see
[the game clock](mechanics/01-game-clock.md).

### NPC

```text
npc_id, name, description, current_location_id, age
faction: CharacterFaction            set in data, read by nothing
personality: list[str]               status: list[str]
notes: str                           free text, appended to by the game master
romance_eligible: bool
conditions: list[CharacterCondition] inventory: list[ItemEntity]
goals: list[str]                     knowledge: set[str]
base_max_hit_points = 100
```

Compared with this document's NPC: relationships live in
[`RelationshipManager`](22-relationships.md) rather than on the record.
`goals` and `knowledge` now exist as fields (previously entirely absent — an
NPC could not want or know anything), but `goals` is rendered to the narrator
as visible intent (see [document 11](11-knowledge-firewall.md)) rather than
driving any behavior of the NPC's own, and `knowledge` is written to and
persisted but read by nothing yet — there is no dialogue or query system that
consumes it. `personality`, `notes` and `romance_eligible` have no
counterpart in the design and exist to steer the narrator's characterisation.

### Persistence

Full snapshot of dynamic state, not base + mutations. There is no mutation log,
so none of this document's replay, rollback or world-history benefits are
available. What is saved, what is looked up by id, and the compatibility rules
are in [document 24](24-runtime-and-persistence.md).

---

[← Knowledge, Visibility, and Information Security](11-knowledge-firewall.md) · [Index](README.md) · [Context Construction and Memory Layers →](13-context-and-memory.md)
