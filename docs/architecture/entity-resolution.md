# Entity Resolution

> **Status: Partial.** Each kind of target has its own lookup: NPCs (`resolve_npc`), zones (`resolve_location`), items (`naming.find_named`), corpse items (`find_content`, the item lookup then a contained name), rooms and containers (`resolve_room`, `resolve_container`), barriers, zombies (by id) and corpses (by id). All match names and ids case-insensitively. Containers and items ask "which one?" when several match: the validator refuses with the choices, and an item is told apart by its describing words (its condition and wetness, such as "broken Baseball Bat"). Nothing else has an ambiguity path, there is no description-based resolution, and items still have no instance ids. See [Implementation Status](../status.md).

A local LLM can identify language references, but the engine should resolve them to real entities.

Player input:

> "Shoot the big one near the door."

The parser may output:

```json
{
  "action": "shoot",
  "target_description": "big one near the door"
}
```

The Entity Resolution layer then searches currently valid entities and may resolve:

```text
"big one near the door"
        ↓
zombie_17
```

If multiple entities match:

```json
{
  "status": "ambiguous",
  "candidates": [
    "zombie_17",
    "zombie_21",
    "bandit_04"
  ],
  "needs_clarification": true
}
```

The system should prefer asking rather than silently making a consequential guess.

This is especially important for pronouns, objects with duplicate names, and spatial descriptions.

## Limitation: items have no instance identity

An `ItemEntity` knows only its type id (`item.id`, such as `kitchen_knife`), and
two knives share it. The data model has no stable per-item id (see
[Data Model](data-model.md#everything-is-a-baseentity-with-hit-points)). Items are
told apart by where they sit: the world is a tree (zone → room → container or bag
→ item → contents), and each item is in exactly one list (the ground, a container,
a bag, a worn or held slot). The save codec writes that tree out and rebuilds it
on load. Each action names its item, and `naming.find_named` looks the name up
in the list the verb reaches.

An item's describing words are its condition word and its wetness word when it
has one, never a number. A name may carry one or more of them before it ("broken
Baseball Bat", "good wet Baseball Bat") or in brackets after it ("Baseball Bat
(broken)"), and then only items with all those words match; of those, the ones
with the fewest describing words are kept ("intact T-shirt" takes the dry shirt
over a wet intact one). Several matches that look the same (same words)
give the first, since nothing the player could say tells them apart. Matches
that look different give the candidates, and the validator refuses with "Which
one: broken Baseball Bat or good Baseball Bat?", each distinct look once, named
by the one word no other look has, else by all its words. The
parser's scene choices offer a name held by differing items also in each
of those labels, and its prompt shows the words beside such items.

This holds up while nothing outside an item's own list needs to point at that
item. It breaks in two places, and a third is only softened:

1. **Duplicates that look the same.** Two knives with the same words cannot be
   told apart, and neither can "the other one" be said. Duplicates that differ
   in condition or wetness are told apart by their words (above).
2. **References that outlast a turn.** Nothing can name one particular item
   across turns or a reload: an NPC who remembers the knife they gave the player,
   a quest to bring back a specific item, a memory entry or event that mentions
   it. The planned per-NPC stories and simulation-driven quests
   ([Story](story.md)) need this.
3. **Address reuse.** `id(self)` is never saved and changes on every load.
   Python reuses an address once its object is freed, so a log line or event
   that records it can later point at a different item.

### Fix

- **Stable instance id.** Give `ItemEntity` an `instance_id` from a counter kept
  in world state (`i1`, `i2`, …). A counter, unlike `uuid4`, stays deterministic
  under a seeded world and seeded tests. Assign it at creation, wherever items
  are created: starting items, zombie outfits, and loot rolled when a container
  or bag is opened.
- **Persist it.** Save the id and the counter. This changes saved state, so bump
  `SCHEMA_VERSION`; old saves are discarded.
- **Show handles only where names collide.** In the parser's context, add a
  short handle after any name that appears more than once in a list
  (`Baseball Bat [i12]`), next to the describing words it already shows. Unique
  names stay bare to save tokens.
- **Resolve handle first, then name.** `find_named` tries a handle before the
  name. If the model garbles or drops the handle, it falls back to name matching
  with the describing words, as it does today.
- **Retire `BaseEntity.id`.** Point it at the stable id, or delete it and fix the
  one log line in `managers/events/pipeline.py` that reads it.

---

[Index](../README.md)
