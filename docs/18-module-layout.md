# Recommended Module Layout

> **Status: Superseded.** The real layout splits by purity (`modules/` → `data/` → `managers/` → `adapters/`), not by subsystem — see the layering table in the root `README.md`, and [Implementation Status](00-status.md).

A practical implementation can be organized approximately as:

```text
engine/
├── simulation/
│   ├── movement
│   ├── combat
│   ├── stealth
│   ├── inventory
│   ├── survival
│   ├── crafting
│   └── travel
│
├── world/
│   ├── topology
│   ├── generator
│   ├── zones
│   ├── locations
│   ├── rooms
│   └── environment
│
├── actors/
│   ├── player
│   ├── npc
│   ├── zombies
│   └── factions
│
├── events/
│   ├── bus
│   ├── definitions
│   ├── handlers
│   └── scheduler
│
├── story/
│   ├── arcs
│   ├── objectives
│   ├── conditions
│   └── director
│
├── knowledge/
│   ├── player
│   ├── npc
│   ├── faction
│   └── visibility
│
├── persistence/
│   ├── snapshots
│   ├── events
│   └── save_load
│
└── llm/
    ├── parser
    ├── entity_resolution
    ├── context_builder
    └── narrator
```

The exact implementation language and database are independent of the architecture.

---

[← Observability, Debugging, and the LLM Security Boundary](17-observability-and-security.md) · [Index](README.md) · [End-to-End Example →](19-end-to-end-example.md)
