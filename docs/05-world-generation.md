# World Generation, Topology and Travel

> **Status: Planned.** Three hand-written rooms in `data/locations.py`. No seed, no generator, no tiers, no hierarchy. See [Implementation Status](00-status.md).

## Location Hierarchy

### 1. Location Hierarchy

Use a flexible hierarchy:

```text
Region
  ↓
Zone
  ↓
Location
  ↓
Room
```

Example:

```text
Pacific Northwest
└── Downtown
    └── Pharmacy
        ├── Front Store
        ├── Back Storage
        └── Cellar
```

A hierarchy should only exist when it provides gameplay or context value. It is not necessary to force every project into all four levels.

---

## Rooms Are Graph Nodes

### 2. Rooms Are Graph Nodes

A room is a navigable graph node rather than a prose paragraph.

```text
pharmacy_front
      │
      ├── pharmacy_back
      │
      ├── street
      │
      └── cellar
```

The engine decides whether movement is possible.

The LLM can say:

> "I head south."

It may not invent that south is a valid exit.

---

## Deterministic World Generation

### 3. Deterministic World Generation

Generate procedural locations from immutable inputs:

```text
WORLD SEED
     +
REGION RULES
     +
ZONE RULES
     +
LOCATION COORDINATES
     +
GENERATION VERSION
     ↓
DETERMINISTIC GENERATOR
     ↓
LOCATION DEFINITION
```

The generator must be versioned. Changing generation algorithms should not silently alter previously established locations.

Example:

```text
seed = 183729
zone = quarantine_suburbs
coordinate = (143, 91)
generator_version = 4
```

The same inputs reproduce the same base definition.

---

## Tiered Content

### 4. Tiered Content

#### Tier 1 — Hand-authored

Major narrative and gameplay content:

- main story locations;
- major faction bases;
- companion characters;
- legendary locations;
- important mysteries;
- bespoke encounters.

#### Tier 2 — Template-generated

Structured locations with controlled variation:

- pharmacies;
- supermarkets;
- clinics;
- police stations;
- survivor camps;
- bandit camps;
- houses;
- warehouses.

#### Tier 3 — Fully procedural

Large-scale filler and traversal content:

- road segments;
- wilderness;
- forest clearings;
- minor ruins;
- generic structures;
- remote encounters.

---

## Separate Topology from Content

### 5. Separate Topology from Content

The world generator should be modular.

```text
WORLD GENERATOR
    │
    ├── Topology Generator
    ├── Terrain Generator
    ├── Location Generator
    ├── Population Generator
    ├── Resource Generator
    ├── Encounter Generator
    └── Narrative Seed Generator
```

This makes deterministic reproduction, testing, and regeneration easier.

---

## On-Demand Materialization

### 6. On-Demand Materialization

A 50,000+ location world does not require 50,000 active objects in memory.

Treat locations as **addressable definitions** that become runtime objects only when needed.

```text
50,000+ addressable locations
        ↓
10,000 visited/known
        ↓
1,000 persisted mutations
        ↓
100 actively simulated locations
        ↓
10 high-resolution locations
        ↓
1 current player scene
```

This distinction is central to scalability.

---

## Travel Nodes

### 7. Travel Nodes

Do not create a room for every meter of wilderness.

```text
Suburbs
   │
   └── 3-hour travel route
          ↓
   Highway Overpass
          │
          └── 2-hour route
                 ↓
             Forest Camp
```

The travel system resolves:

- time elapsed;
- food/water consumption;
- stamina;
- weather;
- encounters;
- route hazards;
- zombie migration;
- arrival conditions.

---

[← Entity Resolution](04-entity-resolution.md) · [Index](README.md) · [Simulation Level of Detail →](06-simulation-lod.md)
