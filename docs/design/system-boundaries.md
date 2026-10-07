# System Boundaries

> **Status: Planned.** There is no event bus. `SimulationCore` (`managers/simulation.py`) resolves every accepted action, but not as the separate core this document describes; `GameManager.event_queue` exists and nothing fills or drains it. See [Implementation Status](../status.md).

## Simulation Core

### 1. Simulation Core

The Simulation Core is the deterministic heart of the game.

It handles:

- movement;
- combat;
- weapons;
- inventory;
- health and injuries;
- stamina;
- stealth;
- visibility;
- sound;
- environmental interaction;
- crafting;
- resource consumption;
- survival needs;
- travel;
- time advancement;
- local NPC behavior;
- zombie behavior;
- environmental state changes.

The Simulation Core consumes validated actions and produces factual results.

Example:

```json
{
  "action": "shoot",
  "actor": "player",
  "target": "zombie_17",
  "weapon": "pistol_1"
}
```

Possible result:

```json
{
  "result": "hit",
  "damage": 24,
  "ammo_spent": 1,
  "noise": 92,
  "target_hp": 6,
  "events": [
    "weapon_fired",
    "zombie_damaged",
    "noise_propagated"
  ]
}
```

The narrator never changes these values.

---

## Event Bus

### 2. Event Bus

The Event Bus is the connective layer between otherwise independent systems.

A system should preferably report an event instead of directly manipulating unrelated systems.

Example:

```json
{
  "event_id": "evt_18472_004",
  "type": "merchant_killed",
  "timestamp": 18472,
  "location": "downtown_market",
  "actor": "player",
  "target": "merchant_04",
  "tags": ["violence", "civilian_death"]
}
```

Systems can subscribe to the event:

```text
merchant_killed
    │
    ├── Family system
    │     → increase hostility
    │
    ├── Economy system
    │     → deactivate trade route
    │
    ├── Faction system
    │     → reputation change
    │
    ├── Story system
    │     → unlock consequence branch
    │
    └── NPC system
          → update rumors / relationships
```

This avoids hard-coding every system-to-system dependency.

#### Event types

Useful categories include:

```text
PLAYER
  moved
  damaged
  healed
  item_acquired
  item_used
  item_lost

COMBAT
  attacked
  hit
  missed
  killed
  weapon_fired

WORLD
  door_opened
  door_destroyed
  container_looted
  fire_started
  power_changed
  weather_changed

NPC
  npc_died
  npc_moved
  npc_fled
  npc_joined_faction
  npc_betrayed_faction

FACTION
  reputation_changed
  territory_changed
  faction_attacked
  faction_defeated

STORY
  objective_completed
  objective_failed
  clue_discovered
  story_branch_unlocked

TRAVEL
  route_started
  route_interrupted
  route_completed
```

---

[Index](../README.md)
