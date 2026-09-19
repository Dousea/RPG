# Time and Scheduling

> **Status: Planned.** Time advances only when the game master emits `TIME_ADVANCE`. Nothing is driven by a clock. See [Implementation Status](00-status.md).

Time should be a first-class simulation subsystem.

```text
GAME CLOCK
    │
    ├── hunger
    ├── stamina recovery
    ├── healing
    ├── infection progression
    ├── zombie migration
    ├── weather
    ├── NPC schedules
    ├── faction activity
    ├── economy
    ├── resource decay
    └── story timers
```

Use different update frequencies.

```text
Immediate:
combat, inventory, movement

Per minute:
stealth, local AI, noise

Per hour:
NPC schedules, zombie migration, weather

Per day:
economy, resource decay, regional changes

Event-driven:
major story consequences
```

Avoid ticking every system every turn.

---

[← Story and Narrative Architecture](07-story-architecture.md) · [Index](README.md) · [Zombie Survival Simulation →](09-zombie-survival.md)
