# Zombie Survival Simulation

> **Status: Planned.** No noise, light, visibility or scavenging model exists. See [Implementation Status](00-status.md).

## Spatial Threat and Noise

### 1. Spatial Threat and Noise

Sound should be represented as an event rather than simply a number attached to the room.

Example:

```json
{
  "source": "pharmacy_backroom",
  "sound_type": "gunshot",
  "intensity": 92,
  "timestamp": 18474
}
```

Propagation can depend on:

- distance;
- doors;
- walls;
- terrain;
- building structure;
- weather;
- sound type;
- intensity.

The system does not need physically accurate acoustics. It needs deterministic, understandable gameplay behavior.

---

## Light and Visibility

### 2. Light and Visibility

Treat light as a simulated property.

```text
room.light_level
player.light_source
weather.light_modifier
line_of_sight
cover
```

Light can affect:

- player visibility;
- zombie detection;
- NPC detection;
- ranged accuracy;
- stealth success;
- narration.

The engine computes the result; the narrator describes it.

---

## Time-Decay Scavenging

### 3. Time-Decay Scavenging

Procedural resource availability can depend on:

```text
location seed
+
game time
+
location history
+
looting events
+
regional scarcity
```

A room's base loot should remain deterministic, while mutable events record what has already been consumed or changed.

---

## Direct Action Validation

### 4. Direct Action Validation

Actions should have clear preconditions.

Example:

```text
SHOOT
  ammunition > 0
  weapon equipped
  target exists
  target visible/accessibly targetable
  weapon operational

BARRICADE
  required materials available
  stamina >= threshold
  valid door/window target

STEALTH MOVE
  movement possible
  encumbrance within allowed range
  movement mode available
```

These are only preconditions. The simulation still determines success, failure, damage, noise, and consequences.

---

[← Time and Scheduling](08-time-and-scheduling.md) · [Index](README.md) · [Combat and Stealth Resolution →](10-combat-and-stealth.md)
