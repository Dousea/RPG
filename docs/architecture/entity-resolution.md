# Entity Resolution

> **Status: Partial.** Each kind of target has its own lookup: NPCs (`resolve_npc`), zones (`resolve_location`), items (`naming.find_named`), corpse items (`find_content`, the item lookup then a contained name), rooms and containers (`resolve_room`, `resolve_container`), barriers, zombies (by id) and corpses (by id). All match names and ids case-insensitively. Containers, items, zones and bodies ask "which one?" when several match: the validator refuses with the choices, an item is told apart by its describing words (its condition and wetness, such as "broken Baseball Bat"), and the engine settles the question on a plan screen before the plan runs ([Which one](#which-one)). Zombies have no ambiguity path ("the zombie" is the nearest) and there is no description-based resolution. A player can also pin a zombie, corpse, NPC, barrier, room, container, zone, body part or item with `@` ([Mentions](#mentions)); the engine binds a pin itself, with no name matching. Items have instance ids ([Items have an instance id](#items-have-an-instance-id)): the `@` list names the ones in reach and the plan screen offers one by its id. See [Implementation Status](../status.md).

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

- **Listed:** the zombies the player sees (one only heard has no id and is left out), the bodies they perceive, the NPCs in the zone, the barriers on the zone's connections (so a neighbouring zone's window can be named from here), the zone's rooms and containers, every other zone `zone_path` reaches, the body parts first aid can act on (the hurt and bandaged ones), and the items in reach: carried (the pack and its bags), worn, held, on the floor, in the opened containers of the player's room and on the searched bodies the player perceives. An item is listed by its instance id. `managers/mentions.py` builds the list.
- **Not listed:** conversation topics (the list would show what an NPC knows before it is asked). A pick in this task needs an id or a closed name.
- **Descriptions** reuse the words the scene already uses (a zombie's distance and state, a barrier's state word and the zones it joins, a zone's direction or next zone on the way and the barrier that blocks it, a container's room and whether it is opened) and never carry a number, except an item's. An item's description gives its describing words, where it is (in your pack, in your bag, worn, held, on the floor, in a container, on a body named by its looks as the list names it) and, for a medical item or a stack, the uses left as the inventory screen shows them ("3 left"). It is for the player's screen only: the parser sees a pinned item by its name and never its description, and neither LLM prompt carries an id. Two zombies or bodies in the same outer garment get one more garment each, then their distance and state words tell them apart. Bare bones leave the sex out, as the scene does. Entries that still read the same (two identical bats) get a `#1`, `#2` in their label, in the list and on the chip alike, since the scene words nothing else that tells them apart.
- **Checked first:** before the parser runs, each pick is checked against what is in reach now. One that no longer is (the zombie moved off, the NPC left) refuses the turn in words, before any LLM call and without spending game time.
- **The parser** lists each seen zombie and body with its looks beside its id (`z1 (a man in a police jacket, close)`), so plain prose can name one without `@`. It sees the pick in the input as `[pinned: z32]` (a zombie or body by id, anything else, an item too, by the name the scene uses) and in a `[PINNED]` block. Nothing new reaches the narrator, the event log or the memory: they read the pick as its plain name.
- **Bound after parsing:** `modules.action.pins.bind` puts each pick into the matching target field of the parsed actions as a `Pinned` text, which reads as the scene's name and carries the id. A pick first takes the field that already writes it; one the parser dropped or swapped takes the first field of its kind that no pick has taken, in action order, and the pin wins over what the parser wrote there. The validator resolves a pinned target by id: `z32` is attacked, not the nearest zombie; a pinned container never gets the which-one question; a pinned zone or room is the move's destination without `resolve_location`'s phrase matching; a pinned part goes into the part field; a pinned item is the one `naming.find_named` returns from the list the verb reaches, by its instance id, and none when it is not in that list. Both parser forms (the JSON schema and the text lines) go through `bind`. The plan check asks about a pinned action like any other, wording a seen zombie or body by the looks the `@` list shows (`seen_by_looks`), so the question matches the input the player typed; a pin is not exempt, since the verb can still be wrong.
- **Across a zone change** the picks carry into the second parse, so "go to @Supermarket and smash @the supermarket window" binds the window in the second plan. A pick in reach at the start but not at the destination is refused there by the validator like any target out of reach, and the first pass's actions stay. Only the picks the first pass did not bind go into the second pass's binding, so a pick already spent on the move to the zone is not bound again to a target at the destination.
- **Typed text is prose:** the request marks each pick's place in the text with U+FFFC and sends the ids in order, so `@z32` typed without picking is plain prose.

Mentions live in one request. Nothing is saved.

## Which one

A name that fits several things is asked about, not guessed. Three lookups can give a list, and one check of the player's words:

- **Items** (`naming.find_named`) when the matches look different, as described under [Items have an instance id](#items-have-an-instance-id). Matches that look the same and have the same uses left still give the first, with no question; the `@` list is how the player picks one of them.
- **Containers** (`resolve_container`) when a bare kind word fits several containers of the player's room.
- **Zones** (`resolve_location`), in two places. A zone's **kind words** (`ZONE_KINDS` in `data/world/locations.py`: "apartment", "flat", "store", "shop"), kept apart from its aliases the way container kind words are, find every zone of the kind that `zone_path` reaches from where the player stands, the current zone included: "apartment" and "flat" are one kind that every home has (the player's apartment, Emma's, which the building answers to, and both flats), so "the apartment" and "the flat" give the same zones. A zone whose kind comes from a place inside it is named in the list by what made it fit (`ZONE_KIND_NAMES`: "Emma's apartment, in Your Building"). One reachable zone is that zone; several are a list. The kind check comes after exact names, directions and exit phrases ("leave the apartment" still walks out) and before the whole-word fallback. The fallback itself gives a list when two or more zones tie on the earliest position and the longest name; the current zone is one of the choices. The head of a phrase still decides: "the street outside my apartment" is the street.

  The player's own words are checked as well (`kind_choice` in `managers/world/locations.py`, called from `open_choices`), because the parser sometimes writes the zone it picked for a kind word. A move to one zone is an open choice over the kind's zones when the player's input (picks as their names) holds a kind word, nothing in it names that zone (its name, an alias, an exit phrase or a connection direction) and the kind word's reachable zones include it. "Go to the apartment" parsed as Your Apartment asks; "go to my apartment", "go home", "go to the supermarket" and a pinned zone move. The candidates are named as a kind-word list is (`ZONE_KIND_NAMES`), and Go binds the pick.

- **Bodies** are checked from the player's words, not by a lookup (`body_named` in `managers/mentions.py`, called from `open_choices`). A search, carry or take-from target that is the generic body or a body id the parser picked is an open choice over every perceived body when two or more are perceived, the action has no pinned body and nothing in the player's input names the chosen one: its `@` label, a looks word no other perceived body has (its sex or a garment), or, for the body in the player's arms, a phrase for carrying it. "Search the body" asks; "search the man in jeans" (jeans on one body only), one body, and a pinned body do not. The candidates are the bodies by id, named and described as the `@` list does (`#1`/`#2` for look-alikes), and Go binds the pick as a body pin. Zombies are not checked this way: "the zombie" stays the nearest, with its default shown on the plan screen. A group word is the same plain target: "them", "all of them", "the zombies" and "the ones" read as "the zombie", and the swing spreads by the usual rule. The floor words ("the ones on the floor" or "on the ground", "the ones down", "the crawlers", and a "stomp") pick the nearest down or crawling zombie; the parser may write a bare "zombie", so `aimed` (`managers/combat/aim.py`) reads them from the player's own input too and writes the plain target of an attack as a floor target. A shove is never rewritten: it can't hit a zombie on the floor, so "shove the zombie down" stays a shove at the nearest standing zombie. A stomp with no zombie down in reach is refused in words and never becomes a shove. A pinned zombie always wins over group words. A plan step whose swing would hit more than the target says so ("shove the nearest zombie and the ones beside it", never a count), worked out by `MeleeEngine.reach`, the rule the swing uses.

The validator turns a list into an `Asked` refusal: the words "Which one: ...?", the field of the action that was unclear and the candidates (`modules/action/choices.py`). A candidate is a zone, container, body or item by id (an item's is its instance id; one candidate per distinct look and uses left, the first such item), with a display name and a short description built from the same words the `@` list uses. Only an item's description can carry a number (the uses left).

**Before the plan runs**, `GameEngine.play` asks the validator about each action's targets in the scene as it stands, up to the plan's first zone change (`managers/plan.py`). It changes nothing. Any action that gives a list is an open choice. With none the plan runs as it always has. With any, nothing runs: no game time passes and the narrator is not called. The payload carries a `plan` in place of a story: each step in words in order (a zombie named by its looks, never by an id), a step that waits on an open choice with its candidates, and a step with a default target ("hit the nearest zombie") with the one it defaults to by its looks. A step after the plan's first zone change, or after a move that is itself an open choice, has no default: the destination parses it again, so it says its target is decided on arrival. The screen offers a picker per open choice, Go and Cancel. A default is not a choice: "the zombie" stays the nearest, and `@` picks another. Go sends one candidate id per open choice, in order; the engine binds each into the field it asks about (a pin for a zone, container or item; an item binds by its instance id, so Go gets exactly that item) and runs the kept plan through the validator and `SimulationCore` with one narrator call and no parser call for the kept plan.

**Late questions pause.** A choice that only appears while the plan runs (a target that depends on an earlier step, or one in the part parsed again after a zone change) ends the plan there, as a zone change does: the actions after it are not tried, and the narrator is told what is not done yet. The same plan screen comes back with the done steps ticked and the open choice as a picker; Go resumes from it without running the done steps again. Every other refusal still skips the action and goes on.

**Kept in memory.** One plan is kept per game, with the turn's text for the part parsed again and the ids of the picks already placed. It is never saved. Typing any other turn, Cancel, a new game or a loaded save drops it. A Go with no kept plan, an answer that is not among the candidates, or a candidate no longer in reach is refused in words, spends no time and drops the plan. A pick that sat in an action the plan check dropped as off-request counts as spent for the part parsed again, like the picks of the actions that were tried.

## Items have an instance id

An `ItemEntity` has its type id (`item.id`, such as `kitchen_knife`, shared by every knife) and its own `instance_id` (`i1`, `i2`, ...). The world keeps the counter (`World.next_item_number`), so ids are deterministic under a seeded world, unique, saved with the item and never reused. `managers/world/item_ids.py` gives an id to every item that has none: at the start of a game, on each turn's screen, when a which-one question is built and before a save is written, which covers the starting kit, a zombie's outfit and loot rolled on opening a container or bag. A change to saved state bumps `SCHEMA_VERSION`; old saves are discarded. `BaseEntity` has no id of its own.

The world is a tree (zone → room → container or bag → item → contents), and each item is in exactly one list (the ground, a container, a bag, a worn or held slot). The save codec writes that tree out and rebuilds it on load. Each action names its item, and `naming.find_named` looks the name up in the list the verb reaches, or the instance id of a pinned item.

An item's describing words are its condition word and its wetness word when it has one, never a number. A name may carry one or more of them before it ("broken Baseball Bat", "good wet Baseball Bat") or in brackets after it ("Baseball Bat (broken)"), and then only items with all those words match; of those, the ones with the fewest describing words are kept ("intact T-shirt" takes the dry shirt over a wet intact one). Several matches that look the same (same words) and have the same uses left give the first: a name cannot tell them apart, so the `@` list does, by instance id. Matches that look different, or look the same but differ in uses left, give the candidates, and the validator refuses with "Which one: broken Baseball Bat or good Baseball Bat?", each distinct look once, named by the one word no other look has, else by all its words; when every match looks the same and only the uses left differ, the question names the item once ("Which Alcohol Wipes?") so no number reaches the narrator. The plan screen offers each look and uses left as a candidate carrying the first such item's instance id and its words ("intact, 3 left"), and Go binds that exact item. The parser's scene choices offer a name held by differing items also in each of those labels, and its prompt shows the words beside such items.

Still open: a reference that outlasts a turn from outside the item's own list (an NPC who remembers the knife they gave the player, a quest to bring back a specific item, a memory entry) can now use the id, but nothing does yet ([Story](story.md)); and the parser's context shows no handle (`Baseball Bat [i12]`) after a name that collides, so its own text still names an item by name and describing words.

---

[Index](../README.md)
