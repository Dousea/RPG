# Combat and Stealth Resolution

> **Status: Planned.** The damage events and modifiers exist (see [document 23](23-traits-perks-modifiers.md)); nothing constructs them, so combat is defined and unreachable. See [Implementation Status](00-status.md).

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

[← Zombie Survival Simulation](09-zombie-survival.md) · [Index](README.md) · [Knowledge, Visibility, and Information Security →](11-knowledge-firewall.md)
