# Simulation Level of Detail

> **Status: Planned.** Every location and NPC is always live in memory. There are nine of them. See [Implementation Status](00-status.md).

A large world needs different simulation resolutions.

## 1. Regional Level

Far away from the player, simulate aggregates:

```text
Downtown
  infected population = 1,820
  survivor population = 340
  faction control = militia
```

## 2. Group Level

Near relevant locations, simulate groups:

```text
Downtown
├── Horde A: 117 infected
├── Horde B: 83 infected
├── Horde C: 42 infected
└── dispersed: 138 infected
```

## 3. Individual Level

In the player's local vicinity, materialize individual actors:

```text
zombie_17
zombie_18
zombie_19
bandit_04
sarah
```

This allows the game to represent a large population without simulating every entity at full detail.

The same LOD idea can be applied to:

- NPC populations;
- faction activity;
- settlements;
- economy;
- zombie groups;
- wildlife.

---

[← World Generation, Topology and Travel](05-world-generation.md) · [Index](README.md) · [Story and Narrative Architecture →](07-story-architecture.md)
