# Context Construction and Memory Layers

> **Status: Partial.** The context builder is now its own module (`managers/context.py`'s `ContextBuilder`), and the parser and narrator get two genuinely different, purpose-built prompts rather than variations on one. It is still not selective within the narrator's prompt — the whole local world goes out every turn, filtered only for relationship scores and discovered world flags, not the spatial memory layers below. See the *As Implemented* section at the end for the memory model that was actually built, and [Implementation Status](00-status.md).

## Context Construction

Never send the entire world to the LLM.

The Context Builder should assemble a localized snapshot.

```json
{
  "current_room": {
    "id": "pharmacy_backroom",
    "name": "Pharmacy Back Storage",
    "exits": ["south", "basement"]
  },
  "visible_npcs": [
    {
      "id": "sarah",
      "name": "Sarah",
      "condition": "injured"
    }
  ],
  "visible_objects": [
    {
      "id": "metal_shelves",
      "name": "metal shelving units"
    }
  ],
  "recent_events": [
    "Player lit a match.",
    "Sarah reported that the barricade is weakening."
  ]
}
```

The Context Builder can combine:

```text
GLOBAL MEMORY
+
ZONE MEMORY
+
ROOM STATE
+
CURRENT SCENE
+
PLAYER KNOWLEDGE
+
RELEVANT NPC KNOWLEDGE
+
RECENT EVENTS
+
CURRENT ACTION RESULTS
```

Only include information required for the current response.

---

## Memory Layers

Use explicit boundaries.

### Global Memory

World-scale truths:

```text
power grid is down
military abandoned city
winter is approaching
```

### Region/Zone Memory

Large-scale local conditions:

```text
downtown is overrun
militia controls western district
```

### Location Memory

Persistent local knowledge:

```text
pharmacy was previously looted
back entrance is barricaded
```

### Scene Memory

Immediate context:

```text
Sarah is injured
player is holding a pistol
a noise was just heard
```

### Event Memory

Recent events relevant to continuity:

```text
player fired a shot
zombie detected movement
Sarah spoke
```

Memory should be **retrieval-based**, not an ever-growing transcript.

---

## As Implemented

`GameManager.build_prompt` is the context builder; `adapters/memory.py` is the
retrieval layer. The memory model that was built is **compressive** — sorted by
age and detail — where the layers above are **spatial**, sorted by scope. The
two are orthogonal; only the compressive one exists.

### Three tiers

```text
RECENT EVENTS     the last 5, verbatim, newest first
                  MemoryState.recent_events, config game.max_recent_events

DEEP MEMORY       the top 2 semantic matches for this turn's player input,
                  drawn from the entire event log
                  SemanticMemory.search, config memory.default_recall

SUMMARIES         every 10 events, folded by the LLM into one narrative
                  paragraph; all summaries are included, always
                  config game.summary_threshold
```

`MemoryState.full_event_log` holds every event ever recorded and is never
truncated — it is the corpus the vector index is built from, not prompt
material. Only the three tiers above reach the model.

A fourth and fifth section round out the narrator prompt, both assembled by
`managers/context.py`'s `ContextBuilder`: `[OUTCOMES]`, what the Action
Validator and Simulation Core already decided *this* turn (movement, combat,
item use, refusals) — the normal path now, described in
[document 01](01-engine-authority.md) — and `[CONTINUITY]`
(`NarrativeState.pending_corrections`), which used to carry a refusal into
the *next* turn's prompt because prose was written before deltas were
applied. That is no longer the normal case: outcomes are decided before
narration, so `[CONTINUITY]` is now a defensive fallback for the rare case
Simulation Core itself throws, not the primary correction mechanism. See
[document 15](15-turn-loop.md).

Together they bound prompt growth against an unbounded game: recent events are
capped, deep memory is capped, and only the summary list grows — one paragraph
per ten turns.

### Semantic recall

The document says memory should be *retrieval-based, not an ever-growing
transcript*, and stops there. The concrete answer:

- `all-MiniLM-L6-v2` via `sentence-transformers`, 384 dimensions;
- `faiss.IndexFlatIP` over L2-normalized vectors, i.e. exact cosine similarity;
- the index is **rebuilt from scratch** after every turn, not appended to.

A full rebuild each turn is O(n) in events and wasteful in principle. At the
scale this game runs at it costs less than the LLM call by orders of magnitude,
and it removes an entire class of index-drift bug. Revisit it when the event
log reaches thousands of entries, not before.

The model is loaded lazily on first use, so importing `adapters.memory` stays
cheap for tooling and tests that never embed anything.

### Summarization

Once the log reaches 10 unsummarized events, the oldest 10 are sent to a second
LLM call (`SUMMARIZER_SYSTEM_PROMPT`, a lower temperature) and the resulting
paragraph is appended to `MemoryState.summaries`. The events are not deleted —
`full_event_log` keeps them, so they remain reachable by semantic recall even
after being summarized.

Summarization is **best-effort**. If the LLM call fails, `GameEngine` logs it
and the turn still stands; the same events are retried next turn.

### Where it diverges

**The context builder is not selective.** The document's central instruction is
to include only what the current response requires. `build_prompt` sends a
fixed set of sections every turn — full character sheet with attributes,
equipment, traits and perks; the location; every item on the ground; every
exit; every NPC present with their complete record; all summaries; recent
events; deep memory. Nothing is chosen based on the player's input except the
two deep memories.

**The firewall is one filter, not a model.** Relationship scores are banded
before they reach the prompt; nothing else is filtered by what the player could
know. See [document 11](11-knowledge-firewall.md).

**Global, zone and location memory do not exist.** World-scale truths live in
`NarrativeState.apocalypse_stage` (one string) and `flags` (booleans). There is
no per-zone or per-location memory of any kind.

---

[← Data Model and Persistence](12-data-model.md) · [Index](README.md) · [Local LLM Roles and Narrator Constraints →](14-llm-roles.md)
