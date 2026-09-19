# Knowledge, Visibility, and Information Security

> **Status: Partial.** The relationship scores are firewalled: `build_prompt` now sends banded labels, never the integers. The knowledge *model* below — world truth split from per-actor knowledge — does not exist. See the *As Implemented* section at the end for what is and is not filtered, and [Implementation Status](00-status.md).

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

There is no knowledge model. There is one filter, in one place.

`GameManager._get_npcs_present_section` is the only spot where the social model
is read out to the narrator, so it is where the firewall sits.

### What is filtered

**Relationship scores never leave as numbers.** Affinity goes out as a
[`CharacterDisposition`](22-relationships.md) and trust as a `CharacterTrust`,
both banded by `RelationshipManager`:

```text
 - Emma (28): A friendly woman in her late twenties...
   Disposition: friendly (trust: solid)
```

not `affection +37, trust +42`. The reason is this document's reason: Orton can
tell that Emma has warmed to him, and cannot read an integer off her face. A
game master handed the number narrates to the number — it starts describing a
score instead of a person, and it can spend a score the player was never told
about.

The bands are the same mechanism on both axes — `get_disposition_from_affinity`
and `get_trust_level_from_trust` — so the thresholds live in one file rather than
being re-invented by each consumer.

### What is not filtered

**Everything else in the prompt is sent whole.** `build_prompt` has no notion of
player knowledge, so:

- **World flags** (`NarrativeState.flags`) all go out every turn. In practice
  each one was set by `SET_FLAG` in response to something that happened in the
  story, so it is usually knowledge Orton has; nothing *enforces* that, and a
  flag set for an off-screen truth would leak.
- **`NpcEntity.status` and `.personality`** go out whole. These are read as
  observable — how someone is presenting — but there is no hidden counterpart,
  so a status the player should not know has nowhere else to live.
- **`NpcEntity.notes`** go out, labelled `Orton's impressions:`. They are
  written by `ADD_RELATIONSHIP_NOTE`, which records Orton's read on someone
  rather than the NPC's private thoughts, so they belong on the player's side of
  the firewall — the old `Notes:` label was what made them look like a leak.

### What the real thing needs

The split above is per-*field*, decided once by hand. The design asks for a
split per-*fact*, decided at runtime: one world truth, and a knowledge set per
actor that the context builder intersects with it. That needs a knowledge store
(NPCs have no `knowledge` field — see [document 12](12-data-model.md)) and a
context builder that is selective at all (see
[document 13](13-context-and-memory.md)). Neither exists.

---

[← Combat and Stealth Resolution](10-combat-and-stealth.md) · [Index](README.md) · [Data Model and Persistence →](12-data-model.md)
