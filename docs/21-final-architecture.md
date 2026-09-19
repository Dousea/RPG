# Final Architecture

> **Status: Planned.** The summary diagram of the design target. For what runs today, see [Implementation Status](00-status.md).

## Final Architecture

```text
                         WORLD SEED
                             │
                             ▼
                    ┌─────────────────┐
                    │ WORLD GENERATOR │
                    └────────┬────────┘
                             │
               ┌─────────────┼─────────────┐
               ▼             ▼             ▼
           Regions         Zones      Settlements
               │             │             │
               └─────────────┼─────────────┘
                             ▼
                    PROCEDURAL LOCATIONS
                             │
                             ▼
                         ROOM GRAPH
                             │
                 ┌───────────┴───────────┐
                 ▼                       ▼
          BASE DEFINITIONS          PERSISTED MUTATIONS
                 │                       │
                 └───────────┬───────────┘
                             ▼
                       STATE STORE
                             │
             ┌───────────────┼───────────────┐
             ▼               ▼               ▼
        Simulation         NPC/AI         Factions
             │               │               │
             └───────────────┼───────────────┘
                             ▼
                         EVENT BUS
                             │
             ┌───────────────┼───────────────┐
             ▼               ▼               ▼
       Story Director    World Rules     Scheduler
             │               │               │
             └───────────────┼───────────────┘
                             ▼
                       UPDATED STATE
                             │
PLAYER INPUT                 │
     │                       │
     ▼                       │
┌───────────────┐            │
│ LOCAL LLM     │            │
│ PARSER        │            │
└───────┬───────┘            │
        ▼                    │
 ACTION PLAN                 │
        │                    │
        ▼                    │
 ENTITY RESOLUTION           │
        │                    │
        ▼                    │
 ACTION VALIDATION ──────────┘
                             │
                             ▼
                    KNOWLEDGE FIREWALL
                             │
                             ▼
                     CONTEXT BUILDER
                             │
                             ▼
                      LOCAL LLM
                       NARRATOR
                             │
                             ▼
                       PLAYER OUTPUT
```

---

## Conclusion

The architecture is built around a strict division of responsibility:

```text
LOCAL LLM
  = understand language + present language

GAME ENGINE
  = truth + rules + simulation + persistence

PROCEDURAL SYSTEMS
  = scalable world structure

EVENT SYSTEM
  = communication between systems

STORY DIRECTOR
  = narrative orchestration from actual world events

KNOWLEDGE FIREWALL
  = information control

CONTEXT BUILDER
  = selective information delivery
```

The goal is not to make the LLM simulate the world.

The goal is to make the LLM **live inside a deterministic simulation and make that simulation feel alive through language**.

A 50,000+ location world is therefore treated as a large addressable state space rather than a gigantic always-active simulation. Locations, NPCs, zombie groups, factions, and story systems are materialized or simulated at the level of detail required by their relevance to the player and current world state.

This preserves consistency while allowing local models to provide flexible natural-language interaction, dialogue, atmosphere, and emergent storytelling.

---

[← Architectural Principles](20-principles.md) · [Index](README.md) · [Relationships →](22-relationships.md)
