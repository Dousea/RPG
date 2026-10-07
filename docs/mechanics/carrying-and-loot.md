# Carrying, Containers and Loot

> **Status: Implemented.**

Everything the player has weighs something. A Strength-based capacity sets
when the load starts to hurt, bags hold things and ease the weight while they
are worn or held, and a body can be picked up and carried. The Heavy Load
status effect, which earlier mechanics read as 0, is live.

The mechanic ships in three stages. This document describes all three.

1. **Carrying**: weight, capacity, Heavy Load and what it switches on, bags,
   `PUT`, and carrying a corpse.
2. **Loot containers**: rooms, containers, `SEARCH` on them, the loot roll.
3. **Places and items**: six new zones and the items the loot tables can drop.

Three facts shape the rest:

- **Two limits, not one.** The Strength-based capacity only sets Heavy Load.
  The hard limit on what the player carries is 50 kg. A character can carry
  past their capacity, slowly hurting themselves, up to that limit.
- **Worn and held weigh less; only a worn or held bag reduces.** Anything worn
  or in a hand weighs 0.3 of its weight. A bag's reduction applies to its
  contents only while the bag is worn or held.
- **A body has weight here.** A carried body weighs 6 kg (bones 2.1 kg), fills
  both hands and counts toward Heavy Load.

Ids and names stay generic: `schoolbag`, `toolbox`, `satchel`.

## What we port

| Piece | File |
| --- | --- |
| Every number below: capacity, weight, Heavy Load, transfer time, Strength XP, corpse carrying | `data/carry.py` |
| Weight, capacity, Heavy Load level, transfer frames, bag room, Strength XP rolls, walking drain, overload loss | `managers/carry.py` |
| The bag type and each item's weight | `modules/item.py`, `data/items.py` |
| What a bag holds | `modules/entity/item.py` |
| Heavy Load in the endurance driver and the status effect row | `managers/body/stats/drivers.py`, `managers/body/stats/status_effects.py`, `data/body/status_effects.py` |
| The overload loss | `managers/body/health.py` |
| The verbs `PUT` and `CARRY`, `TAKE all` | `modules/action/types.py`, `modules/action/parser.py`, `managers/validator.py`, `managers/simulation.py` |
| The six new zones, their exits and aliases | `data/world/locations.py` |
| Their room layouts | `data/loot/containers.py` |
| Their barriers | `data/world/barriers.py` |
| Their zombie fields and indoors flags | `data/zombies/lore.py`, `data/world/climate.py` |
| The new foods, drinks and weapons | `data/loot/items.py`, `data/items.py` |
| The loot tables and the item mapping (generated) | `data/loot/tables.py`, `data/loot/catalogue.py` |
| Bags in zombie outfits and on corpses | `data/zombies/outfits.py`, `managers/zombies/dress.py`, `managers/corpses/search.py` |

## Converting rates to game hours

- **Timed-action frames** are 180 per game minute. A transfer's frames divide by
  180 and round by the shared rule: under a minute and a half is 1 minute,
  otherwise the nearest minute.
- **Frame rate** (10 800 an hour, 180 a minute): the walking drain and the
  overload loss.
- **Real seconds:** Strength XP checks run at most once per real second, and a
  game minute is 3.75 real seconds, so a minute of walking gives 3.75 checks.

All of them go through `modules/units.py`.

## Carrying

### Weight

What the player weighs is everything they have, summed:

```
weight(item)             = own weight + what is inside        # loose in the pack
weight(worn or held)     = (own weight + what is inside) x 0.3
weight(worn or held bag) = own weight x 0.3 + contents x (1 - reduction / 100)
carried = the pack + what is worn + what is in the hands or on the shoulders + a carried body
```

A bag's contents are the sum of what is in it, so a bag inside a bag counts in
full; the reduction applies once, at the bag that is worn or held. A drink's
litres count as kilograms, so a full 1 L water bottle weighs 1.1 kg. A stack of
nails weighs 0.05 kg a nail left in it. A drained drink is no lighter. Weights
compare rounded to a hundredth of a kilo.

The slot count is gone. The pack refuses an item that would take the total past
50 kg: "<name> can't carry any more." A bag refuses what would take its
contents past its capacity, and a bag holds at most 50 kg less its own weight.

| Item | kg |
| --- | --- |
| Adhesive bandage | 0.05 |
| Bandage, dirty and sterilized bandage, ripped sheets (clean, dirty, sterilized), antibiotics | 0.1 |
| Alcohol wipes | 0.3 |
| Painkillers | 0.2 |
| Disinfectant | 0.7 (0.2 bottle, 0.5 litre) |
| Canned beans | 0.8 |
| Water bottle | 1.1 (0.1 bottle, 1.0 litre) |
| Granola bar, instant noodles | 0.2 |
| Nails | 0.05 each |
| Plank | 3.0 |
| Hammer, pistol | 1.5 |
| Barbell | 6.0 |
| Dumbbell | 5.0 |
| The two keys | 0.05 |

Clothing and melee weapons keep the weights they already had.

### Capacity

```
base       = int(8 x modifier[Strength level])
reducers   = the Hungry, Thirst, Sick, Bleeding and Injured losses
capacity   = max(0, base - reducers)
capacity   = int(capacity x trait multiplier)
```

| Strength | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Capacity (kg) | 6 | 7 | 8 | 9 | 11 | 12 | 14 | 15 | 16 | 18 | 20 |

Kilograms lost by status effect level:

| Status effect | L1 | L2 | L3 | L4 |
| --- | --- | --- | --- | --- |
| Hungry, Thirst | 0 | 1 | 2 | 2 |
| Sick, Injured | 0 | 1 | 2 | 3 |
| Bleeding | 0 | 1 | 1 | 1 |

Trait multipliers: Strong 1.5, Stout 1.25, Feeble 0.9, Weak 0.75. They exclude
each other. The Strength trait also moves the Strength level, so Strong at
Strength 9 has `int(18 x 1.5)` = 27 kg. A hungry character carries less: Hungry
level 3 at Strength 5 gives 10 kg.

### Heavy Load

A status effect driven by `carried / capacity`:

| Status effect | L1 | L2 | L3 | L4 | Names |
| --- | --- | --- | --- | --- | --- |
| Heavy Load | above 1.0 | 1.25 or more | 1.5 or more | 1.75 or more | Weighed Down, Overloaded, Very Overloaded, Extremely Overloaded |

It is 0 at 0 health. With capacity 0 and anything carried it is level 4; with
nothing carried it is 0. It is worked out on demand, so it changes the moment
an item moves, a status effect level changes or Strength does. When an action's
own item move changes the level, the turn's facts say so ("is now Very
Overloaded.").

### What Heavy Load does

| Effect | Rule |
| --- | --- |
| Crit chance | -5 per level (melee) |
| Defence | -2 per level against a zombie attack |
| Fitness exercise endurance | x(1 + level / 3), integer division: x1 at levels 0 to 2, x2 at 3 and 4 |
| Endurance regeneration | standing still and walking regenerate only at level 0 or 1 |
| Exercising drain | x1, 1.5, 1.9, 2.3, 2.8 for levels 0 to 4 |
| Walking drain | levels 3 and 4 while moving |
| Overload loss | levels 3 and 4 |
| Body heat | the thermoregulator reads `carried / capacity`, held between 0 and 1 |

- **Walking drain**, per minute: 0.01307 endurance at level 3 and 0.01582 at
  level 4 for the default build, x1.5 while sneaking. Overweight raises the
  factor to 2.9 (from 1.4), Athletic lowers it to 0.8, Asthmatic raises the
  second factor to 1.0 (from 0.7).
- **Overload loss.** At level 3 or 4, awake, not resting (`WAIT` and `SLEEP`
  are resting) and with health above 75, the body loses 1.485 HP a minute at
  level 3 and 2.97 HP at level 4, never past 75 HP. It runs after the body
  minute. It stops at 75 HP, so it cannot kill by itself.

### Bags

A bag has a capacity in kilograms, a weight reduction in percent and, for some,
a largest item it takes.

| Item | Carried | Capacity | Reduction | Weight | Largest item |
| --- | --- | --- | --- | --- | --- |
| Schoolbag | back or hand | 15 | 70 | 1.0 | |
| Duffel bag | back or hand | 18 | 65 | 1.0 | |
| Hiking bag | back or hand | 20 | 75 | 1.2 | |
| Large hiking bag | back or hand | 22 | 80 | 1.5 | |
| Satchel | worn (`satchel`) | 12 | 65 | 1.0 | |
| Fanny pack | worn (`fannypackfront`) | 1 | 85 | 0.2 | |
| Suitcase | hand | 16 | 50 | 3.0 | |
| Garbage bag | hand | 20 | 50 | 0.1 | |
| Toolbox | hand | 8 | 50 | 2.0 | 2 |
| Briefcase | hand | 8 | 50 | 1.5 | 2 |
| Tote bag | hand | 6 | 50 | 0.5 | 2 |
| Handbag | hand | 6 | 50 | 1.0 | 2 |
| Plastic bag | hand | 8 | 50 | 0.1 | |
| Paper bag | hand | 2 | 50 | 0.1 | |

A schoolbag lies on the floor of the apartment.

| Where | Verb | Rule |
| --- | --- | --- |
| On the back (the shoulders) | `EQUIP` | one at a time; back bags only |
| Held in the left hand | `EQUIP` | blocks a two-handed weapon; hand bags, and back bags when the shoulders are taken |
| Worn at the body | `WEAR` | like any garment; satchel and fanny pack |

`EQUIP <bag>` puts a back bag on the shoulders if they are free, else in the
left hand ("<name>'s hands and back are full."; a hand-only bag says "<name>'s
hand is full."). A held bag always takes the left hand, so a one-handed weapon
in the right stays usable. A body bag is refused for `EQUIP` and a back bag for
`WEAR`. Dropping a bag, from the back, a hand or the pack, leaves its contents
inside it.

Items inside a bag the player has with them (in the pack, worn or held) can be
named by every verb that names a carried item: eat from a bag, wear a jacket
out of a bag, bandage with a bandage from a bag. A bag lying in the world is
opened only by taking it.

### Moving things

Frames per item (`w` is the item's own weight, at most 3 kg):

| From to | Frames |
| --- | --- |
| pack to a carried bag | `120 x w x fill`, `fill` = the bag's contents / its capacity, at least 0.4 |
| pack to the floor (`DROP`) | `50 x w x 0.1` |
| the floor or a corpse to the pack | `50 x w` |
| a carried bag to anywhere | `120 x w` |

Dextrous halves the frames and All Thumbs doubles them. Then the pain, mood and
cold slowdown applies, and the total of one action converts to minutes by the
shared rule. A single small item is 1 minute. `TAKE all` is one action, so its
frames add up before the one conversion: twelve 0.8 kg cans from a corpse are
480 frames, 3 minutes. A 3 kg plank into a bag at 90% full is 324 frames, 2
minutes. Moving a worn garment is `WEAR` or `TAKE_OFF` (1 minute), not a
transfer.

### Strength XP

For every minute of `MOVE_TO`, at any pace, with `carried` above half the
capacity, there are 3.75 checks (3, plus a fourth with probability 0.75). Each
check is 1 in 20 for 2 Strength XP: 0.375 XP a minute in expectation. At or
below half, nothing. Strength skips the XP boost.

### Carrying a corpse

`CARRY <corpse>` picks a body up in 1 minute and `DROP corpse` puts it down in
1 minute.

- **Refused** (0 minutes): asleep; no such corpse; already carrying one; a
  hand holding a weapon or bag ("<name>'s hands are full."). A bag on the back
  does not refuse. If the body is further than a tile, the player first walks
  up to it, as for `SEARCH`; a body that rose or rotted away meanwhile is gone.
- **While carrying**, `EQUIP`, `UNEQUIP`, `ATTACK`, `SHOVE`, `USE_ITEM`, `TAKE`,
  `PUT`, `SEARCH`, `BANDAGE`, `REMOVE_BANDAGE`, `DISINFECT`, `BARRICADE`,
  `UNBARRICADE`, `EXERCISE` and `SLEEP` are refused ("<name> is carrying a
  body."). `MOVE_TO`, `WAIT`, `STANCE`, `SHOUT`, `TALK`, `WEAR`, `TAKE_OFF`,
  `OPEN`, `CLOSE` and `DROP` stay.
- **Endurance:** moving with a body counts as exercising for the survival
  stats, at 8.75 times the usual exercising drain: 2.457 an hour.
- **Weight:** 6 kg, 2.1 kg for bones. It feeds Heavy Load and the Strength XP
  check like anything else.
- **The body follows the player.** Its zone becomes the zone the player enters,
  and its distance stays 0, never re-rolled. The corpse count falls in the zone
  it left and rises in the one it enters, so carrying bodies out of a building
  lowers its corpse sickness. A fake-dead body in the arms does not get up.
  `DROP corpse` leaves it 1 tile away. A body that rots away leaves the arms.

## Rooms and containers

### Rooms

A zone is the unit of movement and holds typed rooms. A room has
containers; a container has a name, a capacity in kilograms, and either a fixed
list of items or a loot table.

| Part | What it holds |
| --- | --- |
| Room | an id, a name ("kitchen"), aliases, its containers in layout order, and a count of the procedural tables its containers have used |
| Container | an id, a name, aliases, a capacity, the loot table it rolls (or none), its contents, whether it has been gone through, and whether its contents are fixed |
| Zone | its rooms and the room the player enters it into |
| Player | the room they are in |

Shipped layouts:

| Zone | Rooms and containers |
| --- | --- |
| Your Apartment | kitchen: kitchen counter, kitchen cupboards, fridge, freezer. Bedroom: wardrobe, dresser, bedside table. Bathroom: medicine cabinet, bathroom counter. Living room (where the player starts): side table, living room shelves |
| Your Building | hallway (entry): first-aid cabinet. Laundry room: laundry counter. Basement: storage shelves, tool cabinet |
| The Corner Store | shop floor (entry): till counter, store fridge, snack shelves, drinks shelves. Storeroom: stock crates |
| The new zones | see [The rooms](#the-rooms) |

The street and the neighbourhood have no rooms.

- **Names.** A container's name is unique in its zone. A full name finds its
  container from any room of the zone. A bare kind word ("counter", "shelves")
  finds a container only in the room the player is in, and only when exactly one
  there has it; with several, the action is refused and the choices are listed
  ("Which one: snack shelves or drinks shelves?"). Generic words such as "box"
  or "room" are never names. A name only ever resolves inside the current zone.
- **Capacity.** A container holds 50 kg, the freezer 15 kg, and a body 12 kg.
- **Fixed contents.** A container with a fixed list holds those items and is
  never rolled. Items the player puts in it stay.

### Filling a container

A container fills the first time it is opened with `SEARCH`. It never refills.

**The source table.** Each container names the table its furniture type uses.
A table is either one list of items with a number of rolls, or a procedural pick
between several such tables.

**The procedural pick.** Each choice has a weight, a minimum and a maximum use
per room. A choice with minimum 1 that the room has not used yet is forced: the
pick is among the forced choices only. Otherwise the pick is among the choices
the room has used fewer times than their maximum. A draw below the total weight
walks the choices in data order, adding weights, and takes the first whose
running sum reaches the draw. Reaching it, not passing it, makes the first
choice a little likelier: weights 40 and 100 pick the first 41 times in 140. The
room counts the pick, so a choice with maximum 1 is never picked twice in a room.
A container whose table has no choices rolls its own list.

**The roll.** The junk list rolls first, then the main list. Each list makes its
passes (at least one) over its entries in order. An entry spawns when a whole
number drawn below 10000 is under `chance x 100 x modifier`, with the chance a
percent. Junk entries multiply the chance by 1.4 and use modifier 1.

| Kind of item | Modifier |
| --- | --- |
| Perishable food, other | 0.8 |
| Key | 0.4 |
| Ranged weapon | 1.2 |
| Every other kind (canned food, medical, weapon, container, clothing, literature, tool, cookware, material and the rest) | 0.6 |

So a chance 20 medical entry drops 0.12 of the time, a chance 4 perishable food
entry 0.032, and a chance 0.1 weapon entry 0.06 percent. An entry with no
catalogue item is skipped without a roll.

**The capacity cutoff.** When a spawned item would pass the container's capacity,
the rest of that list stops. A full junk list does not stop the main list.

**After a spawn,** outside a shop table:

- a weapon has a 40 percent chance of spawning worn, with a condition between 1
  and its maximum;
- a stack or medical item with more than one use has a 40 percent chance of
  spawning part used;
- a bag spawns filled from its own table, up to its own capacity. In a shop table
  a bag is empty.

A body's pockets use the same roll with the body's 12 kg as the capacity. The
tables are generated data: `data/loot/tables.py` holds 78 item lists, 42
container sources and 16 bag tables; `data/loot/catalogue.py` maps each table
item name to a catalogue item and its kind. Only items that exist in the game are
rolled, so the tables grow with the catalogue.

### The starting kit

Today's fixed items sit in named containers that are never rolled. Every other
container rolls.

| Container | Holds |
| --- | --- |
| first-aid cabinet (hallway) | two bandages, an adhesive bandage, alcohol wipes, painkillers |
| storage shelves (basement) | a hammer, nails, two planks, a hand axe |
| kitchen counter (apartment) | canned beans, a water bottle, a kitchen knife, a frying pan |
| wardrobe (apartment) | a black jacket, a schoolbag |

Nothing lies on the floor of the apartment, the building or the corner store
any more; the corner store's shelves roll shop tables. The street's crowbar and
alley planks and the neighbourhood's baseball bat stay on the ground.

## Places and items

### The new zones

Six zones join the map. Each is indoors, has its own building id (so a barrier
of it wakes only that place), has exactly one barrier, and is entered into one
room.

| Zone | Name | Off | Exit key | Size (tiles), chunks, intensity | Zombies at the outbreak | Barrier |
| --- | --- | --- | --- | --- | --- | --- |
| `zone_flat_vacant` | The Vacant Flat | the building | `vacant flat` | 8, 1, 0 | about 0.04 | door, 500, closed, unlocked |
| `zone_flat_tenant` | The Tenant's Flat | the building | `tenant flat` | 8, 1, 64 | about 1 | door, 500, closed, locked, no key |
| `zone_pharmacy` | The Pharmacy | the neighbourhood | `pharmacy` | 14, 2, 63 | about 2 | window, one pane (50), closed, locked |
| `zone_clinic` | The Clinic | the neighbourhood | `clinic` | 20, 3, 48 | about 2.3 | door, 500, closed, unlocked |
| `zone_supermarket` | The Supermarket | the neighbourhood | `supermarket` | 30, 6, 63 | about 6 | window, two panes (100), closed, locked |
| `zone_hardware` | The Hardware Store | the neighbourhood | `hardware store` | 20, 3, 63 | about 3 | door, 500, closed, locked, no key |

- The two flats are on floor 1, like the apartment; the shops are on floor 0.
  The tenant's flat sleeps on the floor with a bed in its bedroom, as the
  apartment does; the vacant flat has no bed.
- The building gains the exits `vacant flat` and `tenant flat`; the
  neighbourhood gains `pharmacy`, `clinic`, `supermarket` and `hardware store`.
  Each new zone's `out` goes back.
- **Aliases.** The neighbourhood's `pharmacy`, `drugstore`, `supermarket`,
  `grocery store` and `clinic` moved to the new zones, which add `walk-in
  clinic`, `hardware store` and `tool store`. `hospital`, `coffee shop`, `park`
  and the others stay with the neighbourhood. "Emma's apartment" stays an alias of
  the building. No new alias is a bare generic word (`flat`, `shop`, `store`,
  `door`): "the shop" and "the store" name no zone.
- **Leaving.** "Leave the pharmacy" from the pharmacy goes out to the
  neighbourhood, as "leave the apartment" does from home. Naming another zone in
  an exit phrase walks out of nothing.
- **Barriers.** Each barrier's name is its place and its kind ("pharmacy
  window", "tenant flat door"); a bare "door" or "window" means the one in the
  zone the player is in. A locked barrier with no key can only be smashed or
  boarded up from outside. Moving to a zone behind a locked one stops at it
  ("at the locked window to The Pharmacy").
- **Entry room.** The flats' living room, the shops' shop floor (the
  supermarket's aisles) and the clinic's exam room. A player who enters a zone is
  in its entry room.

### The rooms

A container is built only if one of its tables can drop an item that exists in
the game; the rest are left out and come back as the catalogue grows. Names are
unique inside a zone.

| Zone | Rooms and containers |
| --- | --- |
| The Tenant's Flat | the apartment's rooms, every container stocked from tables: kitchen (counter, cupboards, fridge, freezer), bedroom (wardrobe, dresser, bedside table), bathroom (medicine cabinet, bathroom counter), living room (side table, living room shelves) |
| The Vacant Flat | kitchen (counter, cupboards), bedroom (wardrobe), bathroom (medicine cabinet), an empty living room |
| The Pharmacy | shop floor: pharmacy counter, left shelves, right shelves, shop fridge. Back room: dispensing counter, medicine fridge, supply crates |
| The Clinic | exam room: exam counter, exam desk, side table. Office: office desk, office counter. Supply room: supply counter, supply shelves, supply fridge, supply crates, supply desk |
| The Supermarket | aisles: checkout counter, four aisle shelf units (first to fourth), drinks fridge. Stockroom: stockroom fridge, two stock crates |
| The Hardware Store | shop floor: tool counter, three shelf units, shop crates. Storeroom: two storeroom crates |

A room with several shelf units shares one count of the tables it has used, so
each unit forces a different table: the supermarket's four units take four of
its twelve shelf tables before any repeats. The tenant's flat holds no fixed
items, so its freezer and living room shelves open empty until the catalogue has
something for them.

### Item mapping

The loot tables name items by their table name. `data/loot/catalogue.py` maps
each to a catalogue id and a kind. The generator keeps only mapped names, so a
table can only ever name items that exist; an unmapped name is skipped without a
roll.

| Table item | Catalogue id | Kind |
| --- | --- | --- |
| painkillers, bandages, wipes, antibiotics, disinfectant | the matching medical items | medical |
| ripped sheets (clean and dirty), water bottle | the matching items | other |
| granola bar, canned beans, and every row of [New items](#new-items) except the weapons | the matching foods and drinks | canned food |
| instant noodles | `item_instant_noodles` | food |
| hammer, crowbar, hand axe, plank, bat, kitchen knife, pan, dumbbell, barbell, and the eight weapons below | the matching weapons | weapon |
| nails | `item_nails` | material |
| each bag | the matching bag; a handbag and a purse are one item, so are the two plastic bags | container |
| a piece of clothing that is in the zombie clothing catalogue | the same id | clothing |

The four crisps variants are one item. The diet and other cola cans, the grape
juice box and the other shovel and sledgehammer variants have different values
and stay out. Books, tools, cookware, ingredients, raw and perishable food,
alcohol, light sources, firearms and ammunition, keys and the rest of the long
list wait for the mechanics that give them behaviour.

### New items

Values follow the same rule as the first items: hunger, thirst and stress as
fractions, unhappiness as points, a drink's effect scaled by how much it holds.
A can ships opened: the can opener comes with crafting.

| Item | Hunger | Thirst | Unhappy | Weight (kg) |
| --- | --- | --- | --- | --- |
| Canned soup | -0.25 | -0.04 | 0 | 0.8 |
| Canned tuna | -0.18 | 0 | 0 | 0.3 |
| Canned corn | -0.16 | -0.04 | 0 | 0.8 |
| Canned peaches | -0.15 | 0 | -10 | 0.8 |
| Canned chili | -0.16 | 0 | 0 | 0.8 |
| Canned sardines | -0.14 | 0 | 0 | 0.3 |
| Canned bolognese, corned beef | -0.24 | 0 | 0 | 0.8 |
| Canned carrots | -0.12 | -0.04 | 0 | 0.8 |
| Canned fruit cocktail, pineapple | -0.15 | 0 | -10 | 0.8 |
| Canned fruit beverage | -0.15 | -0.85 | -10 | 0.8 |
| Canned condensed milk | -0.10 | -0.10 | 0 | 0.8 |
| Canned mushroom soup | -0.10 | -0.04 | 0 | 0.8 |
| Canned peas | -0.16 | -0.03 | 0 | 0.8 |
| Canned potatoes | -0.18 | -0.07 | 0 | 0.8 |
| Canned tomatoes | -0.12 | -0.08 | 0 | 0.8 |
| Crackers | -0.05 | 0 | 0 | 0.1 |
| Chocolate bar | -0.20 | 0 | -10 | 0.2 |
| Crisps | -0.15 | 0 | -5 | 0.2 |
| Soda can | -0.036 | -0.09 | -3 | 0.6 |
| Juice box | -0.02 | -0.06 | -10 (and stress -0.04) | 0.3 |

The bags are the stage 1 rows, unchanged. Eight melee weapons join the
catalogue with the same fields as the first weapons:

| Weapon | Kind | Weight (kg) | Hands | Damage against an NPC |
| --- | --- | --- | --- | --- |
| Rolling pin | small blunt | 1.5 | one | 2 |
| Meat cleaver | axe | 1.0 | one | 3 |
| Screwdriver | small blade (stabs) | 0.5 | one | 3 |
| Wrench | small blunt | 1.0 | one | 4 |
| Pipe wrench | small blunt | 1.5 | one | 4 |
| Tire iron | small blunt (pries planks off) | 1.5 | one | 4 |
| Shovel | blunt | 2.0 | two | 8 |
| Sledgehammer | blunt | 6.0 | two | 14 |

**Bags on the dead.** A zombie's outfit can carry a bag: the schoolbag, the
duffel bag, the satchel or the fanny pack, in nine outfit references. The bag
goes into what the zombie carries, not what it wears, and stays on its corpse.
A bag the zombie was dressed in fills from its own table the first time its
corpse is searched, after the pockets, and never again: not when emptied, and
not when the body rises and dies once more. Bags from the player's own
inventory never roll. Weapons stuck in a zombie include the meat cleaver and the
screwdriver before day ten.

## Verbs

All of them refuse while the player is asleep (0 minutes). A move of items takes
its transfer time.

- **`MOVE_TO <room>`:** a name that is a room of the current zone moves the
  player there in 1 minute and sets their room and spot to its name; rooms are
  tried before zones. Refused for the room they are in ("<name> is already in the
  living room."). A name that is no room falls to the usual zone and spot rules.
  Leaving for another zone puts the player in that zone's entry room.
- **`SEARCH <room or container>`:** opening a container takes 1 minute. A
  container in another room costs 1 minute more to get to its room. `SEARCH
  <room>` opens each unopened container of the room in layout order, a minute
  each. An interruption between containers ends it after the container it was in;
  the rest stay closed. Refused: carrying a body; no such room or container ("There
  is no 'x' to search here."); an ambiguous bare word; one already gone through
  ("<name> has already been through the kitchen."). The fact names what the
  container held, with counts: "<name> goes through the kitchen cupboards: two
  canned beans and a bandage." or "... and finds nothing." The items stay in
  the container.

- **`TAKE <item> from <corpse, bag or container>`, `TAKE all`, `TAKE all from
  <source>`:** the plain `TAKE <item>` takes from the ground, or, when the ground
  has none, from the first opened container of the player's room (in layout
  order) that holds it; `from <corpse>` stays; the
  source may be a carried bag or an opened container in the room the player
  is in ("The kitchen counter hasn't been gone through."; "The kitchen counter is
  in the kitchen, not here."; "The kitchen counter holds no 'x'."). `TAKE all` with no source takes everything
  on the ground, or, when the ground is bare, everything in the first opened
  container of the room that holds anything; with a source, everything in it, as one action. Refused: no
  such bag ("<name> has no 'x' to take from."); the bag holds no such item;
  nothing to take; the pack would pass 50 kg ("<name> can't carry any more.");
  carrying a body. A bag lying on the ground is taken as one item, with its
  contents.
- **`PUT <item> in <bag or container>`:** moves a carried item into a bag the
  player has with them, or into an opened container of their room. Refused: no
  such item or target; the container hasn't been gone through; it would pass the
  target's capacity or a bag's largest item ("The toolbox is full.", "The freezer
  is full."); a bag into itself or into a bag it holds; carrying a body.
- **`DROP <item>`:** takes the item from anywhere the player has it, a bag or
  the back included, and leaves it on the ground. **`DROP corpse`** puts a body
  down.
- **`EQUIP`, `UNEQUIP`, `WEAR`, `TAKE_OFF`** work on bags as on any item, 1
  minute each. `UNEQUIP` and `TAKE_OFF` refuse if the pack would pass 50 kg.
- **`CARRY <corpse>`:** see Carrying a corpse.

## Interruptions

No new cause. Heavy Load rising uses the status effect level-change facts and
does not interrupt. A room `SEARCH` is the one multi-minute action of this
mechanic: the minute loop can interrupt it between containers, and a container's
minute completes before the check.

## Traits

| Trait | Effect |
| --- | --- |
| Strong, Stout, Feeble, Weak | capacity x 1.5, 1.25, 0.9, 0.75 |
| Dextrous, All Thumbs | transfer frames x 0.5, x 2 |
| Overweight, Athletic, Asthmatic | the walking drain at levels 3 and 4 |

## Skills and XP

Strength gains XP from walking loaded and sets capacity. Fitness exercise
costs twice the endurance at Heavy Load 3 and 4. No other skill is touched.

## Hooks into other mechanics

- **Survival stats:** the exercising drain, walking and standing regeneration,
  and the walking drain read the Heavy Load level; the body minute carries the
  overload loss.
- **Status effects:** Heavy Load joins the table; the crit penalty reads the
  live level.
- **Body temperature:** the thermoregulator's carry term reads
  `carried / capacity`.
- **Skills:** a Fitness rep costs more endurance at levels 3 and 4.
- **Zombies and melee:** defence and crit chance read the live level.
- **Clothing:** the slot count is gone; a bag worn at the body shares the worn
  items with garments.
- **Corpses:** a carried body follows the player and keeps its distance.
- **Barricades:** the hammer, planks and nails can be in a bag, and a plank
  pried off goes to the floor when the pack is at its limit.
- **Zombie loot:** the kind multipliers and the item map moved to the shared
  loot data; a body's pockets stop at its 12 kg.
- **Zones:** the apartment, the building and the corner store gain rooms.
- **Clock:** a room move takes 1 minute; opening a container takes 1.

## What the narrator and the player see

- **Narrator.** Facts say what happened in words and never give weights:
  "<name> puts the hammer in the toolbox.", "<name> takes the canned beans out
  of the schoolbag.", "<name> sets the schoolbag on his back.", "<name> hauls
  the body up and carries it.", "<name> lets the body fall." Heavy Load reaches
  the narrator in `[CONDITION]` ("Very Overloaded (3/4)") and in the level
  change facts. A carried body reads "carried" in `[CORPSES]`.
- **Parser.** `[INVENTORY]` shows where each bag is and what is in it:

  ```
  [INVENTORY]
   - Schoolbag (on your back): Canned Beans, Bandage
   - Toolbox (in your hand): Hammer
   - Duffel Bag: Toolbox (Plank)
   - Canned Beans
  ```

  A bag with nothing in it says "empty". `PUT` is listed when the player has a
  bag, `TAKE` when a bag or the ground gives something to take, and `CARRY`
  when a body is in view. The plan schema offers the bags, what is in them and
  "all" as `TAKE` sources and items.
- **Rooms.** `[ROOMS]` comes after `[ZONES]` and before `[DOORS AND WINDOWS]`, in
  both prompts. It lists the rooms of the player's zone with their containers; an
  opened container lists what is left in it, and an unopened one never lists
  contents, so nothing can be invented:

  ```
  [ROOMS]
  kitchen (you are here): kitchen counter (opened: canned beans, water bottle), kitchen cupboards (not opened)
  bedroom: wardrobe (opened: black jacket, schoolbag), dresser (not opened)
  ```

  A zone without rooms says "None". `SEARCH` is listed when the zone has rooms,
  `TAKE` when an opened container in the room holds something, and `PUT` when
  one is opened. The plan schema offers the zone's rooms and containers to
  `SEARCH`, and the opened containers of the room to `TAKE ... from` and `PUT`.
- **Player (UI).** The inventory screen shows the weight against the capacity
  in kilograms and each bag with its place and contents; Heavy Load shows in the
  status strip. `/play` gains `carry` (`weight`, `max_weight`, `level`, `bags`)
  and a `carried` flag on a body, and `rooms`: each room of the zone with whether
  the player is in it and its containers (`name`, `opened`, and `contents` only
  once opened). The Nearby screen lists them under "Rooms".

## Saves

Schema 24. Stage 1 adds nested `contents` on every item, `carrying_corpse` and
`carrying_skeleton` on the player, and bags in the shoulder slot and worn at the
body. Stage 2 adds each zone's rooms (every container's `opened` flag, fixed flag
and contents, each room's table counts), the zone's entry room and the player's
room. Stage 3 adds the six zones and their barriers to the starting world.
Incompatible saves are discarded.

## Edge cases

- **Capacity 0:** at Strength 0 with Hungry 4 and Injured 4, anything carried is
  Heavy Load 4.
- **Past 50 kg** the pack refuses, and a bag refuses past its capacity; level 4
  (1.75 x capacity) is reachable only while capacity is at most 28.
- **A bag in a bag** counts in full; the reduction applies at the worn or held
  bag once. A bag can't go into itself or into a bag it holds.
- **Dropping a bag** from the back or a hand drops it with its contents inside;
  eating from a bag is a normal `USE_ITEM`.
- **A body that becomes bones** while carried weighs 2.1 kg from the next action.
- **A closed container** can't be taken from or put into, so the narrator can't
  hand the player an unseen item.
- **A container is never refilled,** even when the player empties it.
- **A full container during a fill** stops only the list that overflowed.
- **A saved room that no longer exists** counts as no room.

## Testing

`tests/test_carry.py` (capacity, weight, Heavy Load, drains, overload loss,
transfers, bag verbs, Strength XP), `tests/corpses/test_carry.py`,
`tests/test_validator.py` (the refusals), `tests/test_items.py` (weights, bag
rows), `tests/test_persistence.py` (nested contents, the carried body),
`tests/test_context.py` and `tests/test_engine.py` (the blocks and `/play`).

Stage 2: `tests/loot/test_rolls.py` (the roll, the pick, the cutoff, the table
shape and the catalogue), `tests/world/test_rooms.py` (the layouts, the starting kit,
name resolution, room moves), `tests/loot/test_containers.py` (`SEARCH`, `TAKE` and
`PUT` with containers), `tests/test_plan_schema.py`, `tests/world/test_corner_store.py`.

Stage 3: `tests/loot/test_data.py` (the new foods, drinks and weapons, the item
mapping, every container bound to a generated table, every container opening
within its capacity), `tests/world/test_places.py` (the zones, their barriers,
aliases, exit phrases and rooms), `tests/zombies/test_population.py` (the outbreak
targets), `tests/zombies/test_outfits.py` (bags on the dead), plus the schema and
`/play` checks in `tests/test_persistence.py` and `tests/test_engine.py`.
