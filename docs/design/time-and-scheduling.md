# Time and Scheduling

> **Status: Planned.** Nothing but the player's own clock exists: see [the game clock](../mechanics/clock.md) for the minute clock and what each action costs. The scheduling system below is not built. See [Implementation Status](../status.md).

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

[Index](../README.md)
