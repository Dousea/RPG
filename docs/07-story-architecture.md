# Story and Narrative Architecture

> **Status: Partial.** Story state is two lists of goal strings, a flag dict, and a flat quest checklist (`modules/quest.py` `QuestState`, seeded from `data/quests.py`) that only the engine can complete. No arcs, conditions or director. The *As Implemented* section at the end records what exists and one decided-but-unbuilt change: story-significant flags and NPC statuses move from LLM-proposed to engine-produced. See [Implementation Status](00-status.md).

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

`discover:` and `npc_status:` do not. Both `DISCOVER_FLAG` and `NPC_STATUS`
are parser verbs, and the flag name or status string is whatever the parser
model invents from the player's phrasing. There is no set to check against,
so an objective keyed on a name the parser never produces is unwinnable, and
nothing anywhere says so — the quest simply sits in `[QUESTS]` with a box
that never checks. A near miss (`outbreak_cause` for `apocalypse_cause`)
fails exactly as silently as a nonsense one.

The current mitigation is to close the namespace by hand: `data/quests.py`
declares `STORY_FLAGS`/`NPC_STATUSES`, `adapters/llm.py` builds the parser's
vocabulary block from those declarations rather than restating them, and
tests assert both that the roster stays inside the vocabulary and that the
vocabulary reaches the prompt.

### Decided, not yet built: story-significant state is engine-produced

That mitigation is a stopgap, and it is the wrong shape. It makes the
parser's output *more likely* to match; it cannot make it match. Whether
`quest_understand_the_crisis` is completable comes down to whether a small
local model honors an instruction to spell a name exactly — which is a
prompt-engineering property, not an architectural one, and is not testable.

[Document 01](01-engine-authority.md) already decides this case. A flag that
gates quest progress is state, not interpretation, and the LLM never decides
state. `DISCOVER_FLAG apocalypse_cause` proposed by a parser reading player
phrasing is the same category error as `UPDATE_CONDITION health -10`: the
model naming an outcome the engine owns. That verb was retired for exactly
this reason; this one survived only because its consequences were invisible
until quests started depending on it.

The decision is that story-significant flags and statuses get **engine
producers** — conditions the engine already evaluates, mapped to the state
change they imply:

- `apocalypse_cause` is discovered by reaching the location, examining the
  object, or hearing the NPC that actually reveals it — a condition on world
  state, not a judgment call about what the player's sentence meant.
- `trusts_orton` is added when `RelationshipManager` crosses the trust band
  that *is* the definition of trusting someone, rather than when the parser
  decides a conversation sounded trusting. The banding mechanism
  ([document 22](22-relationships.md)) already exists and is already the
  engine's own answer to "does this NPC trust Orton"; the status should read
  from it instead of racing it.

The shape this takes is a condition-evaluation pass over world state after
`SimulationCore.resolve()`, emitting the implied state changes before the
narrator prompt is built. That is deliberately this document's own
`EVENT → CONDITION EVALUATION → OBJECTIVE ACTIVATED` step, at the smallest
scale that does anything — the seed of the Story Director rather than a
parallel mechanism to be reconciled with one later.

`DISCOVER_FLAG` and `NPC_STATUS` survive as parser verbs afterward. They stay
useful for incidental colour the engine has no opinion about; they stop being
load-bearing for anything a quest depends on, and `STORY_FLAGS` stops
needing to exist. What this does *not* address is everything above the
checklist: no arcs, no branches, no failure conditions, no dynamic
storylines, no emergent consequences, no director consuming faction state.
Those remain out of scope at the current size.

---

[← Simulation Level of Detail](06-simulation-lod.md) · [Index](README.md) · [Time and Scheduling →](08-time-and-scheduling.md)
