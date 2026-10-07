# Clothing

> **Status: Implemented.**

What Orton wears decides how warm they stay, how fast rain soaks through and
how much wind cuts. This layer holds the data and the wear and remove actions.
What wetness and insulation do to the body arrives with body temperature.

## What we port

Clothing is items worn at body locations. Locations are layered in a fixed
order, from the one next to the skin to the outermost. Each item covers a set of
body parts and carries its own insulation, wind resistance, water resistance
and wetness.

| Piece | File |
| --- | --- |
| `BodyPart`, `BodyLocation`, layer order | `modules/body/parts.py` |
| Exclusivity between locations | `data/clothing/locations.py` |
| Coverage by clothing kind | `data/clothing/coverage.py` |
| `ClothingItem` | `modules/item.py` |
| The catalog entries and Orton's outfit | `data/items.py` |

Not built: textures and visuals, holes from attacks, blood and dirt, tailoring,
bags and containers (the backpack keeps its slot), and the worn-weight
encumbrance multiplier.

## Model

A `ClothingItem` holds:

| Field | Meaning |
| --- | --- |
| `body_location` | one of the 114 locations |
| `covers` | set of `BodyPart` |
| `insulation`, `wind_resistance`, `water_resistance` | 0 to 1 |
| `weight` | kg |
| `scratch_defense`, `bite_defense`, `corpse_sickness_defense` | 0 to 100, default 0 |
| `neck_protection` | multiplier, default 1 |
| `stomp_power` | multiplier, default 1 (trainers 1.8) |
| `hearing_modifier` | multiplier, default 1.0 |

The defence and hearing fields are stored and not yet read. Stomp power scales
stomps ([Melee Combat](11-melee-combat.md#damage)).

Wetness is 0 to 100 and belongs to the carried or worn item, not to the catalog
entry, so it lives on the item entity. It is saved and clamped to 0 to 100 on load. Nothing changes it yet.
The entity also holds `holes`, a set of body parts, written when a zombie's wound tears the clothing ([Zombies](09-zombies.md)). It is saved too.

`PlayerEntity.worn` maps each body location to the entity worn there. Hands and
the backpack stay in `PlayerEntity.equipment`. `layers_for(part)` returns the
worn items that cover a body part, inner to outer. `worn_outer_to_inner()`
returns every worn item, outermost first.

### Body parts and locations

`BodyPart` has 17 members: both hands, forearms, upper arms, upper legs, lower
legs and feet, then upper torso, lower torso, head, neck and groin. Coverage
that reaches the back folds into the upper torso. A bag covers only the back,
so it covers nothing.

`BodyLocation` has 114 members. Each id keeps a `base:` prefix, such as
`base:jacket`. They are declared from innermost to outermost, and that order is
the layer order. A few anchors: `base:underwear` comes before `base:tshirt`,
which comes before `base:sweater`, then `base:jacket`. `base:socks` sits under
`base:shoes`. `base:scarf` and `base:zeddmg` are last. The two wrist locations
(`base:leftwrist`, `base:rightwrist`) hold watches and bracelets.

Exclusivity is symmetric: if A blocks B, B blocks A. There are 379 blocked
pairs. Examples: a skirt blocks pants and dresses, a full suit blocks jackets
and pants, the left and right eye patches block each other. T-shirt, hoodie,
jacket, jeans, socks and trainers do not block each other.

Coverage by clothing kind (the ones the catalog uses):

| Kind | Covers |
| --- | --- |
| shirt | torso, upper arms |
| jumper | torso, arms to the wrist |
| jacket | torso, arms to the wrist, neck |
| trousers | groin, thighs, shins |
| shoes | both feet |

## Actions

- `WEAR <item>` puts on a carried garment at its location. It costs 1 minute, scaled by the action-time multiplier (1 for now).
  - Refused if the item is not carried: "No 'X' in inventory to wear."
  - Refused if the item is not clothing: "X cannot be worn."
  - Refused if the location is taken: "Orton is already wearing a T-shirt there." (plural names such as Jeans take no article)
  - Refused if a worn item blocks the location: "Orton cannot wear X while
    wearing Y."
  - It never swaps. The player takes the old item off first.
- `TAKE_OFF <item>` moves a worn item to the inventory. It costs 1 minute, scaled the same way.
  - Refused if the item is not worn.
  - Refused with "Inventory is full." when the inventory holds its maximum
    number of items.
- `TAKE` of a garment only carries it. Its fact says so ("Take Black jacket: succeeded.
  Orton carries it; he is not wearing it."), so the narrator doesn't dress the character.
- A refused action costs no time.

## Items

| Item | Location | Insulation | Wind | Water | Weight kg | Other |
| --- | --- | --- | --- | --- | --- | --- |
| T-shirt | `base:tshirt` | 0.2 | 0.05 | 0 | 1 | |
| Hoodie | `base:sweater` | 0.6 | 0.25 | 0 | 1 | scratch 10, neck 0.5 |
| Jeans | `base:pants` | 0.7 | 0.55 | 0 | 1 | scratch 20, bite 10 |
| Ankle socks | `base:socks` | 0.15 | 0.1 | 0 | 0.1 | |
| Trainers | `base:shoes` | 0.45 | 0.3 | 0 | 1 | scratch 10, stomp 1.8 |
| Black jacket | `base:jacket` | 0.4 | 0.6 | 0.4 | 2 | scratch 40, bite 20, neck 0.5 |

Orton starts wearing the first five. The black jacket lies in the apartment.
The old worn T-shirt item is gone.

## What the narrator and the player see

- The narrator gets a `Wearing:` line, outer to inner, such as
  `Wearing: hoodie, soaked jeans, trainers, ankle socks, t-shirt`. An item at
  wetness 15 or more gets a word: damp from 15, wet from 40, soaked from 75.
  The line never carries a number. Nothing worn reads `Wearing: Nothing`.
- The parser prompt lists worn clothing under the equipped items and carried
  clothing under the inventory, so it can propose `WEAR` and `TAKE_OFF`.
- The `/play` payload has `worn: [{location, name, wetness_word}]`, outer to
  inner. The word is empty for a dry item. `equipment` now holds only the two
  hands and the shoulders.

## Saves

Schema version 8. `player.worn` maps a location id to the saved item, and every
saved item (worn, carried or on the ground) carries `wetness`. An unknown
location, or an item worn at a location that is not its own, is dropped with a
warning. There is no migration.

## Edge cases

- A location blocked by a worn item refuses `WEAR` and names the blocker.
- A location with no coverage (a watch) is wearable and has no thermal effect.
- Wet clothes in the inventory keep their wetness.
