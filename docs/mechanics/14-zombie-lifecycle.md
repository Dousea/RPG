# The Zombie Lifecycle

> **Status: Implemented.**

Zombies now have a life around their death. Each one wears clothes and may carry
a weapon. A hit can turn one into a crawler. A kill leaves a corpse that rots,
holds loot and, if it was only pretending, gets up. A pile of bodies makes the
player sick. A player who dies infected becomes a zombie.

Four facts shape the rest:

- **Dead zombies stay dead.** Only a player who dies infected rises. The corpses
  that get up are the fake-dead ones, which were never dead.
- **Crawlers are made by hits.** Each hit that does not kill has a small chance
  to flag the zombie, and a flagged zombie that goes to the ground crawls from
  then on.
- **Zombie armour is the player's armour.** A zombie's clothes have the same
  scratch and bite defence as the player's, doubled. A zombie in a leather
  jacket is much harder to hurt than one in a T-shirt.
- **A zombie's loot is mostly what it wore.** The pocket table is almost all
  junk with tiny chances.

## What we port

| Piece | File |
| --- | --- |
| The outfit pool and each outfit's item references | `data/zombie_outfits.py` |
| The clothing items the outfits can produce | `data/zombie_clothing.py` |
| Pocket tables, attached weapon definitions, loot multipliers | `data/zombie_loot.py` |
| Every number below | `data/zombie_lore.py` |
| Sex, outfit, worn items, attached weapon, the crawler flags | `modules/entity/zombie.py` |
| `CorpseEntity` | `modules/entity/corpse.py` |
| Dressing a zombie, crawler speed | `managers/zombie_dress.py` |
| Zombie defence, the hit part, the crawler roll, crawler posture | `managers/melee.py` |
| The crawler attack branch | `managers/zombie_attack.py` |
| Step 3b, crawlers in the minute loop, the corpse on a kill | `managers/zombies.py` |
| Outbreak corpses, rot, removal, fake-dead rising, the rising player | `managers/corpses.py` |
| `SEARCH`, `TAKE ... from`, pocket rolls, perceived bodies | `managers/loot.py` |
| Corpse count, defence and the smell fact | `managers/corpse_sickness.py` |

Every corpse timer is in game hours. The two rates that began as per-frame values
(corpse sickness and the unhappiness from stripping a corpse) are stated here per
game hour and per game minute.

## What a zombie gains

Every `ZombieEntity` carries these fields. All are saved.

| Field | Meaning |
| --- | --- |
| `female` | the sex that picks the outfit; 50% are female |
| `outfit` | the outfit name, such as `generic01` |
| `worn` | the clothing worn, by body location, at full condition |
| `attached` | the weapon stuck in it, or none |
| `crawling` | it is a crawler |
| `become_crawler` | a hit flagged it and it has not been to the ground yet |
| `was_fake_dead` | it rose from a corpse and keeps that corpse's clothes |
| `risen_from_player` | it is the player's own body |
| `carried` | what it carries; only the player's body has any |

Every zombie is dressed when it is made: the population at the outbreak, at each
12-hour redistribution, and any zombie a test builds. A zombie that rose from a
corpse keeps the corpse's clothes.

### Outfits

Every zombie picks from one pool of 27 outfits, whatever the zone.

| Outfit | Chance | Sex |
| --- | --- | --- |
| `generic01` to `generic05` | 20 each | any |
| `generic_skirt` | 20 | female |
| `dress_long`, `dress_normal`, `dress_short` | 3 each | female |
| `office_worker` | 2 | male |
| `office_worker_skirt` | 2 | female |
| `young` | 2 | any |
| `retiree`, `student` | 1 each | any |
| `cyclist`, `farmer`, `varsity` | 0.5 each | any |
| `construction_worker`, `foreman` | 0.5 each | male |
| `biker` | 0.3 | any |
| `police`, `ranger`, `evacuee` | 0.25 each | any |
| `golfer` | 0.2 | any |
| `police_state`, `sanitation` | 0.1 each | any |
| `exterminator_suited` | 0.01 | any |

One roll over the chances open to the zombie's sex picks the outfit. The
`generic` outfits are about 91% of male and 87% of female zombies.

An outfit is a list of references per sex. Each has a probability (1 when not
stated) and a list of choices: its own item and the alternatives. For each
reference, in order, the zombie wears it when a roll of 0 to 1 is at most the
probability, and the item is one of the choices, uniformly. A choice that is not
in the catalogue (a bag, a watch) leaves nothing. An item whose body location is
already taken is skipped.

The catalogue gained every item the outfits can produce, 289 clothing items
with their own stats. Some share a display name, so names are unique only among
the hand-written catalogue items.

### Attached weapons

After the outfit, a zombie may carry a weapon:

1. A zombie in an outfit with its own weapon entry (`police`, `police_state`)
   rolls that entry first: its chance, then up to its item count, each further
   one needing another roll of the same chance.
2. Otherwise 6% of zombies roll one (a roll of 1 to 100 above 6 means none).
3. A definition is picked by its `chance` among those that qualify. One that has
   a day gate qualifies when more days than that have passed since the outbreak.
   One without a day gate qualifies when it has no outfit list or the zombie's
   outfit is on it.
4. The weapon is a uniform pick from the definition's list. Its condition is a
   whole number from `max(2, condition_max - 5)` up to, not including,
   `condition_max`.
5. A weapon that is not in the catalogue is not attached, and its holes are not
   made.
6. Each of the definition's body parts gets a hole on every worn layer that
   covers it.

With today's catalogue, on days 0 to 9 about 0.097% of zombies carry a hand
axe, from day 10 about 0.43% carry a kitchen knife and about 0.064% a hand axe.
The baseball bat appears only in outfit definitions, and the frying pan in none.
The pool's chance total is 155 on days 0 to 10 and 233 after day 10.

### Armour against melee

**Which part is hit.** A weapon hit or shove on a standing zombie lands on one of
ten parts, uniformly: both hands, forearms and upper arms, the upper and lower
torso, the head and the neck. A floor attack or stomp lands on the head or the
neck, uniformly.

**The defence of a part:**

```
scratch = min(100, sum of scratch_defense of worn items covering the part, with no hole there)
bite    = min(100, sum of bite_defense      of worn items covering the part, with no hole there)
defence = min(85, (scratch x 0.5 + bite) x 2)
```

On the neck an item's value is multiplied by its neck protection when that is
below 1. A hole on a part removes the item's share there.

**In the damage chain.** After `split x= 3` for a head hit and before the
`hits_taken` ramp:

```
split x= 1 - defence / 100
```

A shove deals no damage and ignores defence. About 66% of zombies have no
defence on any of the ten standing-hit parts.

## Crawlers

A crawler is a zombie on the ground that drags itself toward the player. It is
slow, cannot be defended against and bites legs.

### Becoming a crawler

Every hit that does not kill the zombie rolls once:

| Hit | Chance |
| --- | --- |
| a weapon hit on a standing zombie, or a weapon floor attack | 1 in 30 |
| a bare-handed stomp | 1 in 15 |
| a shove, a knife close kill, or a hit that kills | never |

A zombie that is already a crawler is not rolled again. A success sets
`become_crawler`. The flag takes effect on the ground: when a crit or a hit on a
zombie that is already down knocks it down, it becomes a crawler instead of
getting up, with no knockdown timer. A flagged zombie that is never knocked down
dies standing. The fact: "z3 drops to the ground and starts to crawl."

### What changes

A crawler keeps its id, health, hit count, memory, sight and hearing.

| Change | Rule |
| --- | --- |
| Speed | `speed_mod` re-rolled as 0.30 plus a whole number below 1500 over 10,000, so 0.30 to 0.45; never a lunger |
| Thumping | none. At a closed barrier it stops and does nothing |
| Posture | it counts as down for the player's swings: a weapon makes a floor attack, bare hands a stomp. `SHOVE` is refused ("It's already down.") |
| Staggering | a hit crawler skips its attack that minute |
| Reach | within 1 tile, like any zombie |
| Spotting, hearing, memory | as for any zombie |

### Crawler attacks

A crawler's attack each minute:

1. Half the time it does nothing, and nothing is said.
2. There is no defence roll.
3. It is not counted in `attackers`; a lone crawler counts as 1. Crawlers never
   count toward a drag-down.
4. The part: one time in ten uniform from the groin down to the right foot,
   otherwise uniform from the left thigh down to the right foot.
5. Damage, kind, clothing blocking and the wound are as for any zombie.

A crawler bite is still a bite and carries the infection.

## Corpses

`CorpseEntity` is kept in `World.corpses`, numbered `c1`, `c2`, ... in order of
creation.

| Field | Meaning |
| --- | --- |
| `corpse_id` | `c1`, `c2`, ... |
| `zone_id` | where it lies |
| `gap` | tiles from the player while the player is in its zone; rolled uniform from 1 to the zone's size when the corpse is made and again every time the player enters its zone |
| `female`, `outfit` | what it was |
| `died_at` | the game minute it was made |
| `rot_at_death` | 1, 2 or 3 |
| `skeleton` | bones only: it wears and holds nothing |
| `contents` | the worn items, the attached weapon, a stuck knife, and the pockets once searched |
| `attached` | which of those items is the weapon that was stuck in the body; a risen body wields only that one, and a weapon in the pockets stays in them |
| `searched` | the pockets have been rolled |
| `fake_dead`, `crawling` | a fake-dead body, and whether it rises as a crawler. Never shown |
| `risen_from_player` | it is the player's body |

### Where corpses come from

1. **A zombie the player kills.** The corpse takes the zombie's gap, outfit,
   worn items and attached weapon, and a stuck knife. Its rot stage is rolled on
   whole days since the outbreak: always 1 up to day 20, then the chances move
   linearly to day 90 (stage 1 from 100% to 20%, stage 2 from 10% to 30%) and
   stay there. From day 180 stage 1 is gone and stage 2 is 10%. A killed zombie
   is never fake-dead and never rises.
2. **At the outbreak,** once per zone chunk:

   ```
   P(a corpse in this chunk) = 2/3 x 0.1 x zombies_per_chunk
   ```

   A chunk holds at most one. Expected corpses: 0.16 in the building, 0.92 in
   the street, 1.66 in the neighbourhood, none in the apartment. Each body is a
   skeleton with chance 1 in 14. Otherwise it is dressed like a zombie, with 10
   random holes (each on the outermost layer covering a random part that has no
   hole there) and rot stage 1. One in 15 of the dressed bodies is fake-dead, and
   one in five of those crawls. Its `died_at` is the outbreak minute.
3. **The player's body,** if they die infected.

No corpses exist before the outbreak.

### Rot and removal

Each minute, for every corpse in id order, with `age` in hours since `died_at`:

- `rot_stage = min(3, rot_at_death + floor(age / 72))` while `age < 216`;
- on the first minute `age` is 216 or more, a body that is not a skeleton rolls
  once. One time in seven it turns to bones (worn items and contents cleared) and
  is removed 72 hours later; otherwise it is removed that minute;
- a skeleton made at the outbreak is removed at 288 hours;
- removal deletes the corpse and everything in it.

A corpse in a zone the player is not in rots the same way. Rot words: 1 "fresh",
2 "decaying", 3 "rotten", a skeleton "bare bones".

### Fake-dead corpses

In the minute loop, step 3b comes after thumping. For each corpse in the
player's zone, with `gap_start` and `gap_end` the gap before and after this
minute's walk, a fake-dead body rises when:

- it is not a skeleton;
- 30 minutes have passed since it died;
- the closed interval between the two gaps touches 2 to 4 tiles.

The gap changes only for the body the player is walking up to. A body at gap 1
the whole time does not rise.

**Rising.** The corpse is removed and a zombie takes its place: rolled afresh,
with the corpse's sex, outfit, worn items and weapon, and its gap. It is a
crawler if the corpse was `crawling`. It starts chasing, facing the player. It
counts as newly spotting the player, so the minute ends and Panic rises. The
fact: "A body on the ground lurches to its feet." or "A body on the ground
twitches and starts to drag itself across the floor." A sleeping player is woken.
Pocket items a corpse holds go with it: the zombie carries them.

## Searching and looting

### `SEARCH <corpse>`

Goes through a corpse's pockets and clothes. It costs **1 minute**. The target
is a corpse id from `[CORPSES]`, or `corpse` for the nearest.

- If the gap is more than 1, the player first walks up to it at walking pace.
  Those minutes face every interruption, and a fake-dead body can rise during
  them.
- Refused (0 minutes): asleep; no such corpse in view; a corpse already searched
  ("Orton has already been through c3."). A body that rose during the walk is gone:
  "Orton gets to where c3 lay, but the body is gone."
- The pockets are rolled once and the corpse becomes `searched`. The fact lists
  what it holds: "Orton goes through c2: a hi-vis vest, jeans, a kitchen knife."
  An empty body gives "nothing".

### `TAKE <item> from <corpse>`

Costs **1 minute** per item, stretched by pain, mood and cold like any `TAKE`.

- Refused (0 minutes): asleep; no such corpse; the corpse has not been searched
  ("Orton hasn't been through c3 yet."); the item is not on it; the inventory is
  full.
- The item moves to the inventory. A worn item comes off the corpse. Clothing
  keeps its holes. Putting it on is a separate `WEAR`. The fact: "Orton takes the
  dead man's jacket." ("the dead woman's" for a woman).
- **Unhappiness.** Each minute of taking an item adds 1.8 unhappiness: twice
  that for Cowardly, half for Brave, none for Desensitized. `SEARCH` adds none.

An item name may be part of the item's name: `TAKE jacket from c3`.

### Zombie loot

A corpse's pockets are rolled once, at the first `SEARCH`: the corpse's outfit
table first, if it has one (15 of the 27 outfits do), then the default table for
its sex. For each entry in table order one roll:

```
the item drops if a whole number below 10,000 is below chance x 100 x modifier
```

so the chance is `chance x modifier / 100`. The modifier is by kind of item:

| Kind | Modifier |
| --- | --- |
| other, food | 0.8 |
| key | 0.4 |
| medical, literature, container, weapon, media, clothing, material | 0.6 |

Entries whose item is not in the catalogue are skipped without a roll. The
catalogue includes clothing, so a locket and the like can drop from pockets.
Painkillers (chance 0.1, medical) drop from 0.06% of bodies. A construction
worker's table adds Nails (chance 20, material: 12%). Pockets stop filling at
12 kg. A skeleton gets no pocket roll, and neither does one that rots into
a skeleton before it is searched. The player's own body is searched already.

A corpse's contents also hold what it was wearing and carrying when it was made,
so the loot a zombie really drops is its clothes and its attached weapon.

## Corpse sickness

Standing among many bodies adds food sickness.

**The count.** In a zone that is part of a building, every body in every zone of
that building (so the apartment and the hallway share one count). Elsewhere,
the bodies in that zone. Skeletons count. The count is capped at 25.

**The rate:**

```
excess = min(count - 5, 20)                          # nothing at 5 or fewer
rate   = 1.134 x excess  food sickness per game hour
rate  x= 1 - defence / 100                           # the best worn corpse sickness defence
rate  x= 0.75 Resilient, 1.25 Prone to Illness
```

That is 1.134 food sickness an hour for the sixth corpse, up to 22.68 an hour at
25. **The usual decay stops while the rate applies,** and runs again when the
rate is 0, including when a defence of 100 takes it there.

The fact when the count first passes 5 in a zone: "The smell of the dead hangs
thick here." It is given again only after the count has fallen to 5 or fewer, or
the player has been to another zone with the same problem.

## The player who rises

A player who dies with `zombie_infection` of 0.001 or more becomes a zombie where
they fell, whatever killed them. The engine builds it when the game ends so the
final state is consistent:

- it is a freshly rolled zombie with `risen_from_player`, the player's sex, the
  player's worn items and carried inventory;
- it is in the zone where the player died, at gap 1, idle;
- it lies until its delay is up, uniform from 0 to just under 1 minute;
- held items are dropped on the ground where the player died and stay there;
- if it is ever killed, its body is already searched and holds those items.

The game is over, so nothing acts on this zombie. The final fact is "...and rose
again."; no second fact is added.

## Interruptions

No new cause. A fake-dead corpse that rises is a zombie newly spotting the player.
`SEARCH` and `TAKE ... from` are 1-minute actions that complete before the
minute's interruption check, so an attack during them cancels the rest of the
plan, not the item just taken.

## Traits

| Trait | Effect |
| --- | --- |
| Desensitized | no unhappiness from taking items off a corpse |
| Cowardly | that unhappiness x2 |
| Brave | that unhappiness x0.5 |
| Resilient | corpse sickness x0.75 |
| Prone to Illness | corpse sickness x1.25 |

## Skills and XP

None. Killing, looting and searching give no XP. A weapon hit on a crawler gives
weapon XP as any hit does.

## Hooks into earlier specs

- **Game clock:** `SEARCH` joins `TAKE` and `DROP` at 1 minute.
- **Survival stats:** food sickness gains the corpse source and its decay rule;
  `StatContext` carries `corpse_count` and `corpse_defence`; unhappiness gains the
  stripping source.
- **Clothing:** `ClothingItem` has `corpse_sickness_defense`; the catalogue holds
  the zombie outfits' items; `holes` is also written by zombie outfits.
- **Zombies:** a kill leaves a corpse; a crawler is not an attacker, cannot be
  defended against and does not drag down; the minute loop gains step 3b; new
  zombies are dressed.
- **LLM contract:** new verb `SEARCH`; `TAKE` gains `from <corpse>`; new
  `[CORPSES]` block; `[THREATS]` says "crawling".
- **Melee combat:** crawlers count as down and cannot be shoved; zombie armour is
  live; a stuck knife goes into the corpse.
- **Health and infection:** the rising player is built.
- **Doors and barricades:** crawlers never thump.

## What the narrator and the player see

- **Facts:**
  - "z3 drops to the ground and starts to crawl."
  - "A body on the ground lurches to its feet."
  - "A body on the ground twitches and starts to drag itself across the floor."
  - "Orton goes through c2: a hi-vis vest, jeans, a kitchen knife."
  - "Orton takes the dead man's jacket."
  - "The smell of the dead hangs thick here."
- **`[CORPSES]`:** one line per corpse the player can see (within 20 tiles
  scaled by light, never below a quarter of that), with the distance words of
  `[THREATS]`:
  - the parser sees the id: `- c3, close, a man in a hi-vis vest and jeans, fresh,
    not searched` or `- c3, close, fresh, searched: hi-vis vest, jeans, kitchen
    knife`; a skeleton is `- c3, close, bare bones`;
  - the narrator sees the same line without the id, and ids in facts read as "the
    body";
  - a corpse is never described as fake-dead, crawling or anything but dead.
- **`[THREATS]`:** a crawler reads "crawling toward you" or, when it has reached
  the player, "crawling". A lunger's "fast" never applies to a crawler.
- **Parser:** `SEARCH` is listed when a body is in view; `TAKE` also when a
  searched body in view holds something. The plan schema offers the corpse ids and
  the items they hold.
- **Page:** `/play` gains `corpses: [{id, distance_word, rot_word, searched,
  contents}]` (contents empty until searched), and `crawling` among a threat's
  `state_word` values. The Nearby screen shows "The dead" with the distance, the
  rot word, whether it is searched and what it held.

## Saves

The schema is version 21 and old saves are discarded. A save adds `world.corpses`
(every field), `world.next_corpse_number`, the zone the smell fact was last given
in, and per zombie the fields in [What a zombie gains](#what-a-zombie-gains). A
worn item saves its holes.

## Edge cases

- **A flagged zombie dies standing.** No crawler, no corpse difference.
- **A crawler hit again.** No crawler roll: it already is one.
- **Three zombies and a crawler on you.** Three attackers; the drag-down still
  needs three standing zombies.
- **Only crawlers on you.** `attackers` is 1, no defence roll, no drag-down.
- **A fake-dead corpse the player never approaches.** It stays, rots and is
  removed at 216 hours like any corpse.
- **Searching a fake-dead corpse.** The walk crosses its ring, so it rises on the
  way; the search is refused as the corpse is gone, and the sighting interrupts
  the plan anyway.
- **A knife close kill.** Always leaves a corpse; the knife is in its contents.
- **Corpses on leaving.** They stay in their zone and keep rotting.
- **A skeleton from rot.** It keeps no clothes or contents; items the player
  already took stay taken.
- **Looting while zombies are on you.** Allowed; each minute is a normal minute
  of the loop.
- **No corpses, no sickness.** Five or fewer give nothing.
- **A player who dies infected in the street.** The zombie is placed in the
  street; nothing acts on it.
- **Determinism.** Every roll uses the injected `rng`: the sex, the outfit, its
  references in table order, then the attached weapon; pockets in table order;
  the minute loop's corpse steps in id order.

## Testing

| Module | What it covers |
| --- | --- |
| `tests/test_zombie_outfits.py` | the pool, references, the catalogue items, attached weapons, zombie defence, the hit part, the armour step |
| `tests/test_crawlers.py` | the crawler roll, going down, speed, posture, thumping, crawler attacks, `attackers` |
| `tests/test_corpses.py` | kill corpses, outbreak corpses, rot and removal, fake-dead rising |
| `tests/test_corpse_loot.py` | `SEARCH`, `TAKE ... from`, pocket chances, unhappiness |
| `tests/test_corpse_sickness.py` | the count, the rate, the decay rule, the smell fact |
| `tests/test_reanimation.py` | the player who rises |
| `tests/test_context.py`, `tests/test_engine.py`, `tests/test_plan_schema.py`, `tests/test_persistence.py` | the `[CORPSES]` block, the payload, the plan schema, the save |
