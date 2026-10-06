# Time and Scheduling

> **Status: Planned.** Nothing but the player's own clock exists: see [the game clock](mechanics/01-game-clock.md) for the minute clock and what each action costs. The scheduling system below is not built. See [Implementation Status](00-status.md).

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
