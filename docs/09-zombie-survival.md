# Zombie Survival Simulation

> **Status: Partial.** Noise, light and visibility are [mechanics 09](mechanics/09-zombies.md); the scavenging model below is not built. See [Implementation Status](00-status.md).

## Spatial Threat and Noise

Implemented as radius-and-volume sounds in [mechanics 09](mechanics/09-zombies.md#noise).

---

## Light and Visibility

Implemented as spotting and perception in [mechanics 09](mechanics/09-zombies.md#spotting).

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
