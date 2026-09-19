# Story and Narrative Architecture

> **Status: Planned.** Story state is two lists of goal strings and a flag dict on `NarrativeState`. No arcs, objectives, conditions or director. See [Implementation Status](00-status.md).

## Story State Is Engine State

### 1. Story State Is Engine State

Do not represent a story as one giant script.

Use:

```text
Story Arc
  ↓
Objectives
  ↓
Conditions
  ↓
Events
  ↓
State Transitions
  ↓
Consequences
```

Example:

```text
Objective: Protect caravan

Condition:
caravan.status == active

Event:
caravan_attacked

Possible transitions:
caravan.escaped
caravan.destroyed
caravan.abandoned
caravan.captured
```

The story engine reacts to whatever actually happened.

---

## Three Types of Story Content

### 2. Three Types of Story Content

#### Hand-authored story arcs

Used for:

- main quest;
- faction conflicts;
- companion arcs;
- major mysteries;
- important reveals.

The engine owns progression; the LLM provides variable dialogue and prose.

#### Dynamic storylines

The simulation produces the skeleton.

```text
NPC loses item
    ↓
NPC asks player for help
    ↓
Investigation
    ↓
NPC B is discovered
    ↓
NPC B offers a deal
```

#### Emergent consequences

The world changes without necessarily producing a conventional quest.

```text
merchant killed
    ↓
family hostility increases
    ↓
trade route fails
    ↓
market prices rise
    ↓
faction dissatisfaction increases
    ↓
new NPC rumors emerge
```

---

## Story Director

The Story Director is an orchestration layer, not a second simulation engine.

It consumes:

- world events;
- objective conditions;
- faction state;
- NPC relationships;
- world milestones;
- player knowledge;
- time conditions.

It can activate story content:

```text
EVENT
  ↓
CONDITION EVALUATION
  ↓
STORY DIRECTOR
  ↓
OBJECTIVE / BRANCH / EVENT ACTIVATED
```

The Simulation Core remains responsible for physical and mechanical truth.

---

[← Simulation Level of Detail](06-simulation-lod.md) · [Index](README.md) · [Time and Scheduling →](08-time-and-scheduling.md)
