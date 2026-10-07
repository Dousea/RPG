# Zombie Survival Simulation

> **Status: Partial.** Noise, light and visibility are [`zombies`](../mechanics/zombies.md); the scavenging model below is not built. See [Implementation Status](../status.md).

## Spatial Threat and Noise

Implemented as radius-and-volume sounds in [`zombies`](../mechanics/zombies.md#noise).

---

## Light and Visibility

Implemented as spotting and perception in [`zombies`](../mechanics/zombies.md#spotting).

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

[Index](../README.md)
