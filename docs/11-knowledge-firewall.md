# Knowledge, Visibility, and Information Security

> **Status: Partial.** Two filters now exist, in `managers/context.py`: relationship scores are banded, never sent as integers, and world flags only reach the narrator once the engine has separately marked them discovered (a topic told, or a story beat). The knowledge *model* below — world truth split from per-actor knowledge — still does not exist as a general mechanism: `NpcEntity.knowledge` is a real field now (see [document 12](12-data-model.md)), but nothing reads it yet, since there is no dialogue system to gate against it. See the *As Implemented* section at the end for what is and is not filtered, and [Implementation Status](00-status.md).

Separate world truth from knowledge.

```text
WORLD TRUTH
     │
     ├── PLAYER KNOWLEDGE
     ├── NPC KNOWLEDGE
     ├── FACTION KNOWLEDGE
     └── HIDDEN INFORMATION
```

Example:

```json
{
  "world_truth": {
    "traveler_is_heir": true
  },
  "player_knowledge": {
    "traveler_is_heir": true
  },
  "crown_knowledge": {
    "traveler_is_heir": false
  },
  "guild_knowledge": {
    "traveler_is_heir": true
  }
}
```

The Context Builder must never expose hidden data merely because it exists in the world state.

This makes the Context Builder an **information firewall**.

---

## As Implemented

There is no general knowledge model, but there are now two real filters
instead of one, both in `managers/context.py`'s `ContextBuilder` (previously
inline on `GameManager`).

### What is filtered

**Relationship scores never leave as numbers.** Affinity goes out as a
[`CharacterDisposition`](22-relationships.md) and trust as a `CharacterTrust`,
both banded by `RelationshipManager`, in `ContextBuilder._npcs_present_section`:

```text
 - Emma (28): A friendly woman in her late twenties...
   Disposition: friendly (trust: solid)
```

not `affection +37, trust +42`. The reason is this document's reason: Orton can
tell that Emma has warmed to him, and cannot read an integer off her face. A
narrator handed the number narrates to the number — it starts describing a
score instead of a person, and it can spend a score the player was never told
about.

The bands are the same mechanism on both axes — `get_disposition_from_affinity`
and `get_trust_level_from_trust` — so the thresholds live in one file rather than
being re-invented by each consumer.

**World flags only leave once discovered.** `NarrativeState.flags` is the
engine's ground truth; `NarrativeState.discovered_flags` is a separate set,
and `ContextBuilder._discovered_flags_section` only renders a flag that is in
both. Setting a flag's value and marking it known to the player (a topic an NPC
tells, or a story beat) are two different steps, so the engine can hold a fact
that is simulation-true before the story has revealed it — the case this
document's example (`traveler_is_heir`) is actually about.

**NPC goals are shown as visible intent, not private knowledge.**
`NpcEntity.goals` renders as `Visible intent: ...` — the kind of thing Orton
could plausibly infer from someone's behavior, not a leak of private state.

### What is not filtered

- **`NpcEntity.status` and `.personality`** go out whole. These are read as
  observable — how someone is presenting — but there is no hidden counterpart,
  so a status the player should not know has nowhere else to live.
- **`NpcEntity.notes`** go out, labelled `Orton's impressions:`. They are
  written by `ADD_RELATIONSHIP_NOTE`, which records Orton's read on someone
  rather than the NPC's private thoughts, so they belong on the player's side of
  the firewall — the old `Notes:` label was what made them look like a leak.
- **`NpcEntity.knowledge`** exists as a real field (see
  [document 12](12-data-model.md)) but is deliberately never rendered into any
  prompt — there is no dialogue system yet that would need to gate what an NPC
  can truthfully say against it, so today it is written to and persisted but
  never read.

### What the real thing needs

The two filters above are still per-*field*, decided once by hand — flags and
relationship scores, specifically. The design asks for a split per-*fact*,
decided at runtime: one world truth, and a knowledge set per actor that the
context builder intersects with it, generalized past these two cases. That
needs `NpcEntity.knowledge` to actually be consumed by something (a dialogue
or query system that checks "does this NPC know X" before letting the
narrator have them reveal it) and a context builder that is selective about
more than flags and relationship scores (see
[document 13](13-context-and-memory.md)). Neither exists yet.

---

[← Combat and Stealth Resolution](10-combat-and-stealth.md) · [Index](README.md) · [Data Model and Persistence →](12-data-model.md)
