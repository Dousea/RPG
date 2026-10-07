# Entity Resolution

> **Status: Partial.** `resolve_npc`, `resolve_location` and `_find_item_entity` match names and ids case-insensitively. There is no description-based resolution and no ambiguity path. See [Implementation Status](../status.md).

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
on load. Each action names its item, and `carry.find_named` returns the first
entity in the list whose name or type id matches.

This holds up while nothing outside an item's own list needs to point at that
item. It breaks in three places:

1. **Duplicates.** With a broken bat and a good bat in the inventory, "hold the
   bat" always takes the first in list order. Neither the parser nor the player
   can say "the other one".
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
  (`Baseball Bat [i12]`) and a word for what sets the items apart (broken,
  wet). Unique names stay bare to save tokens.
- **Resolve handle first, then name.** `find_named` tries a handle before the
  name. If the model garbles or drops the handle, it falls back to name matching
  as it does today. When several items still match and the choice matters, it
  returns the ambiguity state described above instead of guessing.
- **Retire `BaseEntity.id`.** Point it at the stable id, or delete it and fix the
  one log line in `managers/events/pipeline.py` that reads it.

---

[Index](../README.md)
