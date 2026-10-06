# Story and Narrative Architecture

> **Status: Partial.** Story state is two lists of goal strings, a flag dict, and a flat quest checklist (`modules/quest.py` `QuestState`, seeded from `data/quests.py`) that only the engine can complete. No arcs, conditions or director. The *As Implemented* section at the end records what exists. Story-significant flags and NPC statuses are engine-produced (see [the LLM contract](mechanics/10-llm-contract.md)). See [Implementation Status](00-status.md).

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

## As Implemented

There is no director and no arc graph. There is a flat quest checklist that
satisfies this document's *first* principle — story state is engine state —
while satisfying none of the structure around it.

### What exists

`QuestState` (`modules/quest.py`) is a quest id, a status, a list of
objective key strings, and the subset of them completed. `data/quests.py`
seeds three of them on a new game. Completion is engine-decided: there is no
LLM verb that can advance a quest, and no narrator output is consulted.
`SimulationCore._advance_quests` is the only writer, called from inside the
`_resolve_*` methods *after* a state change has actually landed — a validator
rejection never reaches those lines, so a refused action cannot tick an
objective.

An objective key names the transition that completes it:

```text
take:<item_id>              reach:<location_id>        defeat:<npc_id>
discover:<flag_name>        npc_status:<npc_id>:<status>
```

`ContextBuilder._quests_section` renders active quests to the narrator as a
`[QUESTS]` checklist so prose can reference what Orton is working toward.
The narrator is told it may use this for motivation and may not declare an
objective complete; completion reaches it as an already-decided fact in
`[OUTCOMES]`, like every other outcome.

### The namespace split, and why it matters

Those five key kinds are not equivalent, and the difference is the live
constraint on writing quest content.

`take:`, `reach:` and `defeat:` reference ids the engine owns and
enumerates. The engine emits the key itself, from the entity it just acted
on, so the key and the world cannot disagree; a typo is caught by a test that
checks membership in `ITEMS`, `world.locations` or `npcs`.

`discover:` and `npc_status:` used to be producible by the parser model, which
named the flag or status from the player's phrasing. That is gone: the engine
alone produces both. A topic an NPC tells reveals the flag, and `trusts_player`
is derived from the trust band. Story beats are the engine's own producers for
time-driven change. See [the LLM contract](mechanics/10-llm-contract.md#story-beats),
[topics](mechanics/10-llm-contract.md#topics) and
[derived statuses](mechanics/10-llm-contract.md#derived-statuses). A test checks
that every `discover:` and `npc_status:` objective in the roster has such a producer.

What this does *not* address is everything above the checklist: no arcs, no
branches, no failure conditions, no dynamic storylines, no emergent consequences,
no director consuming faction state. Those remain out of scope at the current size.

---

[← Simulation Level of Detail](06-simulation-lod.md) · [Index](README.md) · [Time and Scheduling →](08-time-and-scheduling.md)
