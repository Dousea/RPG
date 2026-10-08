# Entity Resolution

> **Status: Partial.** Each kind of target has its own lookup: NPCs (`resolve_npc`), zones (`resolve_location`), items (`naming.find_named`), corpse items (`find_content`, the item lookup then a contained name), rooms and containers (`resolve_room`, `resolve_container`), barriers, zombies (by id) and corpses (by id). All match names and ids case-insensitively. Containers, items and zones ask "which one?" when several match: the validator refuses with the choices, an item is told apart by its describing words (its condition and wetness, such as "broken Baseball Bat"), and the engine settles the question on a plan screen before the plan runs ([Which one](#which-one)). Nothing else has an ambiguity path, there is no description-based resolution, and items still have no instance ids. A player can also pin a zombie, corpse, NPC, barrier, room, container, zone or body part with `@` ([Mentions](#mentions)); the engine binds a pin itself, with no name matching. See [Implementation Status](../status.md).

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

## Mentions

The player can say which one they mean. Typing `@` in the input opens a list of what is in reach (`/play` and `/state` carry it as `mentions`: kind, id, the name, a short description and the label the list and the chip show), and a pick goes into the turn as an id, not as prose. The player never sees an id: a zombie or body is named by its looks ("man in a police jacket", built by the helper that words a corpse's looks), and the other kinds by their display names. A pick is a reference the engine binds itself:

- **Listed:** the zombies the player sees (one only heard has no id and is left out), the bodies they perceive, the NPCs in the zone, the barriers on the zone's connections (so a neighbouring zone's window can be named from here), the zone's rooms and containers, every other zone `zone_path` reaches, and the body parts first aid can act on (the hurt and bandaged ones). `managers/mentions.py` builds the list.
- **Not listed:** conversation topics (the list would show what an NPC knows before it is asked) and items, which have no instance id yet (see the limitation below). A pick in this task needs an id or a closed name.
- **Descriptions** reuse the words the scene already uses (a zombie's distance and state, a barrier's state word and the zones it joins, a zone's direction or next zone on the way and the barrier that blocks it, a container's room and whether it is opened) and never carry a number. Two zombies or bodies in the same outer garment get one more garment each, then their distance and state words tell them apart. Bare bones leave the sex out, as the scene does. Entries that still read the same get a `#1`, `#2` in their label, in the list and on the chip alike, since the scene words nothing else that tells them apart.
- **Checked first:** before the parser runs, each pick is checked against what is in reach now. One that no longer is (the zombie moved off, the NPC left) refuses the turn in words, before any LLM call and without spending game time.
- **The parser** lists each seen zombie and body with its looks beside its id (`z1 (a man in a police jacket, close)`), so plain prose can name one without `@`. It sees the pick in the input as `[pinned: z32]` (a zombie or body by id, anything else by the name the scene uses) and in a `[PINNED]` block. Nothing new reaches the narrator, the event log or the memory: they read the pick as its plain name.
- **Bound after parsing:** `modules.action.pins.bind` puts each pick into the matching target field of the parsed actions as a `Pinned` text, which reads as the scene's name and carries the id. A pick first takes the field that already writes it; one the parser dropped or swapped takes the first field of its kind that no pick has taken, in action order, and the pin wins over what the parser wrote there. The validator resolves a pinned target by id: `z32` is attacked, not the nearest zombie; a pinned container never gets the which-one question; a pinned zone or room is the move's destination without `resolve_location`'s phrase matching; a pinned part goes into the part field. Both parser forms (the JSON schema and the text lines) go through `bind`.
- **Across a zone change** the picks carry into the second parse, so "go to @Supermarket and smash @the supermarket window" binds the window in the second plan. A pick in reach at the start but not at the destination is refused there by the validator like any target out of reach, and the first pass's actions stay. Only the picks the first pass did not bind go into the second pass's binding, so a pick already spent on the move to the zone is not bound again to a target at the destination.
- **Typed text is prose:** the request marks each pick's place in the text with U+FFFC and sends the ids in order, so `@z32` typed without picking is plain prose.

Mentions live in one request. Nothing is saved.

## Which one

A name that fits several things is asked about, not guessed. Three lookups can give a list:

- **Items** (`naming.find_named`) when the matches look different, as described under the limitation below.
- **Containers** (`resolve_container`) when a bare kind word fits several containers of the player's room.
- **Zones** (`resolve_location`), in two places. A zone's **kind words** (`ZONE_KINDS` in `data/world/locations.py`: "apartment", "flat", "store", "shop"), kept apart from its aliases the way container kind words are, find every zone of the kind that `zone_path` reaches from where the player stands, the current zone included: "apartment" and "flat" are one kind that every home has (the player's apartment, Emma's, which the building answers to, and both flats), so "the apartment" and "the flat" give the same zones. A zone whose kind comes from a place inside it is named in the list by what made it fit (`ZONE_KIND_NAMES`: "Emma's apartment, in Your Building"). One reachable zone is that zone; several are a list. The kind check comes after exact names, directions and exit phrases ("leave the apartment" still walks out) and before the whole-word fallback. The fallback itself gives a list when two or more zones tie on the earliest position and the longest name; the current zone is one of the choices. The head of a phrase still decides: "the street outside my apartment" is the street.

The validator turns a list into an `Asked` refusal: the words "Which one: ...?", the field of the action that was unclear and the candidates (`modules/action/choices.py`). A candidate is a zone or container by id, or an item by its qualified name, with a display name and a short description that never carry a number, built from the same words the `@` list uses.

**Before the plan runs**, `GameEngine.play` asks the validator about each action's targets in the scene as it stands, up to the plan's first zone change (`managers/plan.py`). It changes nothing. Any action that gives a list is an open choice. With none the plan runs as it always has. With any, nothing runs: no game time passes and the narrator is not called. The payload carries a `plan` in place of a story: each step in words in order (a zombie named by its looks, never by an id), a step that waits on an open choice with its candidates, and a step with a default target ("hit the nearest zombie") with the one it defaults to by its looks. A step after the plan's first zone change, or after a move that is itself an open choice, has no default: the destination parses it again, so it says its target is decided on arrival. The screen offers a picker per open choice, Go and Cancel. A default is not a choice: "the zombie" stays the nearest, and `@` picks another. Go sends one candidate id per open choice, in order; the engine binds each into the field it asks about (a pin for a zone or container, the qualified name for an item) and runs the kept plan through the validator and `SimulationCore` with one narrator call and no parser call for the kept plan.

**Late questions pause.** A choice that only appears while the plan runs (a target that depends on an earlier step, or one in the part parsed again after a zone change) ends the plan there, as a zone change does: the actions after it are not tried, and the narrator is told what is not done yet. The same plan screen comes back with the done steps ticked and the open choice as a picker; Go resumes from it without running the done steps again. Every other refusal still skips the action and goes on.

**Kept in memory.** One plan is kept per game, with the turn's text for the part parsed again and the ids of the picks already placed. It is never saved. Typing any other turn, Cancel, a new game or a loaded save drops it. A Go with no kept plan, an answer that is not among the candidates, or a candidate no longer in reach is refused in words, spends no time and drops the plan. A pick that sat in an action the plan check dropped as off-request counts as spent for the part parsed again, like the picks of the actions that were tried.

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
