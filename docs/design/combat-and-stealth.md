# Combat and Stealth Resolution

> **Status: Partial.** Built parts are mechanics: melee against zombies in [`melee`](../mechanics/melee.md), with clothing armour from [`zombie-lifecycle`](../mechanics/zombie-lifecycle.md); attacks on NPCs go through [the traits-and-modifiers chain](../architecture/traits-and-modifiers.md). Stealth and ranged combat are intent. See [Implementation Status](../status.md).

## Combat

### 1. Combat

A combat action may depend on:

```text
ammo
weapon state
weapon type
range
line of sight
lighting
player condition
stance
accuracy
target movement
target armor
randomness/seeded roll
```

The player can request an approach such as:

```text
"Aim for its head."
```

The engine interprets that as an attack parameter, but it determines whether the attack actually hits and what happens.

---

## Stealth

### 2. Stealth

Stealth can depend on:

```text
player movement speed
encumbrance
light level
player noise
terrain
cover
enemy perception
enemy alertness
distance
line of sight
```

The LLM may express intent:

```json
{
  "approach": "stealth"
}
```

The engine decides whether the approach succeeds.

---

[Index](../README.md)
