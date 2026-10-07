# Doors, Thumping and Barricades

> **Status: Implemented.**

A closed door no longer holds forever. The dead pound on doors and windows until
they give way, and the player can open, close, board up, pry open and break
them. This mechanic puts doors and windows on the connections between zones,
lets zombies thump them, and gives Carpentry its first use.

Four facts shape everything below:

- **One zombie can't break a door.** A door only takes damage while two or more
  zombies are at it. A lone zombie pounds for ever and does nothing.
- **A barricade takes damage from a single zombie.** A boarded door falls to
  one patient zombie, slowly, while a bare door never does.
- **A barricade on either side shields the door.** A thump goes to the planks on
  the zombie's own side first, then to the planks on the far side, and only then
  to the door.
- **Every door has 500 health.**

## What we port

| Piece | File |
| --- | --- |
| `BarrierEntity` and `BarrierKind` | `modules/entity/barrier.py` |
| `World.barriers`, `Location.building` | `modules/world/location.py` |
| The thumping fields and the `thumping` state | `modules/entity/zombie.py` |
| `PlayerEntity.at_barrier` | `modules/entity/player.py` |
| `StackItem` (nails) | `modules/item.py`, `modules/entity/item.py` |
| The verbs `OPEN`, `CLOSE`, `BARRICADE`, `UNBARRICADE`; `ATTACK` on a barrier | `modules/action/types.py`, `modules/action/parser.py`, `modules/action/schema.py`, `modules/action/words.py`, `modules/resolution.py` |
| The two shipped doors, every number and every fact | `data/world/barriers.py` |
| Hammer, Plank, Nails, starting loot | `data/items.py`, `data/world/locations.py` |
| Time costs | `data/time_costs.py`, `modules/units.py` |
| Blocking, vision, damage, plank health, distance | `managers/world/barriers.py` |
| The verbs and the crossing | `managers/world/barrier_use.py`, `managers/simulation.py`, `managers/validator.py` |
| Starting, stepping and releasing thumpers | `managers/zombies/thumping.py`, `managers/zombies/population.py` |
| Barrier sounds | `managers/zombies/noise.py` |
| Stress from sounds | `managers/body/stats/drivers.py`, `managers/body/stats/engine.py` |
| `[DOORS AND WINDOWS]` and `[THREATS]` | `managers/context.py` |
| The `barriers` payload, saves | `adapters/engine.py`, `adapters/save/codec.py`, `static/app.js`, `templates/index.html` |

## Barriers

A **barrier** is a door or a window on a connection between two zones. Barriers
live in `World.barriers`, keyed by id, because each belongs to two zones at
once. They replace the old door entity.

| Field | Meaning |
| --- | --- |
| `barrier_id` | `door_apartment`, `door_lobby` |
| `kind` | `door` or `window` |
| `zones` | the two zones it joins, the barrier's **sides** |
| `inside_zone` | which side counts as inside, for the lock |
| `name`, `aliases` | what the prompts call it ("apartment door") and what the parser may say ("front door", "my door") |
| `open` | an open barrier stops nothing |
| `broken` | a broken door is gone for good; a smashed window stays a gap with a frame |
| `locked`, `key_id` | the lock |
| `health`, `max_health` | door 500; single-pane window 50, double-pane 100 |
| `barricades` | per side (a zone id), a list of up to 4 plank healths, innermost first |

A **barrier of a zone** is any barrier on one of its connections.

`Location.building` names the building a zone is part of. `zone_home` and
`zone_building` are the `apartment_block`, `zone_bodega` is the `corner_store`,
and each of the six zones of [Carrying, Containers and Loot](25-carrying-containers-and-loot.md#the-new-zones)
is a building of its own, so a barrier of one wakes only that place. The street
and the neighbourhood have none.

### The shipped barriers

| Barrier | Kind | Joins | Inside | Start |
| --- | --- | --- | --- | --- |
| `door_apartment` | door, 500 | `zone_home` and `zone_building` | `zone_home` | closed, locked, key `item_apartment_key` |
| `door_lobby` | door, 500 | `zone_building` and `zone_street` | `zone_building` | closed, unlocked |
| `window_bodega` | window, 50 | `zone_street` and `zone_bodega` | `zone_bodega` | closed, locked, no key |
| `door_flat_vacant` | door, 500 | `zone_building` and `zone_flat_vacant` | `zone_flat_vacant` | closed, unlocked |
| `door_flat_tenant` | door, 500 | `zone_building` and `zone_flat_tenant` | `zone_flat_tenant` | closed, locked, no key |
| `window_pharmacy` | window, 50 | `zone_neighborhood` and `zone_pharmacy` | `zone_pharmacy` | closed, locked, no key |
| `door_clinic` | door, 500 | `zone_neighborhood` and `zone_clinic` | `zone_clinic` | closed, unlocked |
| `window_supermarket` | window, 100 | `zone_neighborhood` and `zone_supermarket` | `zone_supermarket` | closed, locked, no key |
| `door_hardware` | door, 500 | `zone_neighborhood` and `zone_hardware` | `zone_hardware` | closed, locked, no key |

- The apartment door starts locked: from the building side it needs the key
  while it is locked, from inside it doesn't. Opening a locked barrier from its
  inside, by `OPEN` or by a `MOVE_TO` crossing, unlocks it for good. Opening
  with the key from outside leaves the lock as it was.
- The shop window is the only way into the corner store (`zone_bodega`, the
  `corner_store` building): its door is chained shut from inside. It has no key,
  so from the street it can't be opened, only smashed or boarded up; from inside
  it opens and unlocks. A zombie shut in the store thumps it from within. The
  supermarket window is a double pane (`max_health` 100).
- The new flats and shops each have exactly one barrier. A locked one with no key
  can't be opened from outside, only smashed or boarded up.

### The player's distance to a barrier

Sounds and stress need how far the player is from a barrier of their zone. Call
it `d_b`.

- **1 tile** while the player is **at** it: after `OPEN`, `CLOSE`, `BARRICADE`,
  `UNBARRICADE` or `ATTACK` on it, or after a `MOVE_TO` whose last hop came
  through it. Any later `MOVE_TO` within a zone clears this.
- Otherwise, and for every other barrier of the zone, **half the zone's size**: 4 in `zone_home`, 10 in `zone_building`,
  20 on the street.

Getting to a barrier the player isn't at costs **1 minute**, before the action
itself. Zombies act during it.

### What a barrier stops

A barrier **blocks** its connection while it is a closed door that isn't broken,
or a closed window that isn't smashed. A barricade with any plank left blocks it
too, whatever the door or window behind it is doing.

- An open door, a broken door, an open window or a smashed window doesn't block.
- **Vision:** a closed door blocks sight. Glass doesn't. A barricade blocks
  sight from 3 planks on one side; 1 or 2 planks don't.

## Thumping

A zombie **thumps** a barrier that blocks its way while it is chasing the
player or walking toward a sound. An idle zombie never does. Redistribution
never passes a blocking barrier, and a zone whose every connection is blocked
gains no new zombies, because nothing could get in.

### Starting

Zombies gain a state, **thumping**. In the movement step, a chasing or alerted
zombie in another zone whose way to the player crosses a blocking barrier walks
toward the first one at its usual speed and stops there. It never gets closer
than the barrier: `d_b + 1` tiles from the player for a barrier of the player's
zone, otherwise the boundary of the zone it is in (40 tiles for each connection
still between it and the player). It starts thumping when it gets there, from
the side it is on, so a distant chaser takes several minutes. A zombie in its
cooldown stays put instead. Its fields:

| Field | Meaning |
| --- | --- |
| `thump_barrier` | the barrier it is at; its own zone is the side it is on |
| `thump_rate` | thumps per game minute |
| `thump_carry` | the fraction of a thump kept for the next minute |
| `thump_cooldown` | minutes before it may start thumping again |
| `was_chasing` | whether it was chasing, rather than alerted, when it started |

**The rate.** Each zombie rolls one of three pounding styles when it starts:

| Style | Thumps per game minute |
| --- | --- |
| bang | 1.5 |
| claw | 1.40625 |
| door | 3.0 |

The mean is about **1.97 thumps a minute**. Each minute `thump_carry` grows by
`thump_rate`; the whole part is that minute's thumps and the rest carries. Every
thumper has its own rate and carry.

**Where it stands.** A thumper on the far side of a barrier of the player's zone
stands `d_b + 1` tiles from the player. Every chaser the player leaves behind a
door they shut takes the same place, even one at gap 1; only the zombies that
opening the door released that hop follow through. It doesn't attack, doesn't count toward the
attackers, and can't be the target of `ATTACK`: the barrier is in the way.

### Each thump

The thump goes to the first of these that exists:

1. a barricade with planks on the zombie's side;
2. a barricade with planks on the far side;
3. the door or window itself, if it blocks.

For a window, the glass comes between 1 and 2: the zombie's own planks, then the
glass, then the far side's planks.

| Target | Damage per thump |
| --- | --- |
| A barricade | 3, to the **outermost plank only**; damage past 0 is lost |
| A door | 3, **only when 2 or more zombies are thumping it**, from either side |
| A window | 3 |

A plank at 0 is gone. A barricade with no planks is removed.

From full health and at the mean rate:

| Barrier | 1 zombie | 2 zombies | 3 zombies |
| --- | --- | --- | --- |
| Door (500) | never | about 42 minutes | about 28 minutes |
| One plank at Carpentry 0 (1000) | about 2 hours 50 minutes | about 1 hour 25 minutes | about 56 minutes |
| Four planks at Carpentry 0, then the door | about 11 hours 20 minutes, then never | about 5 hours 40 minutes, then 42 minutes | about 3 hours 45 minutes, then 28 minutes |
| Single-pane window (50) | about 9 minutes | about 4 minutes | about 3 minutes |

### Breaking

When a door's health reaches 0 it **breaks**: it is gone, and the doorway can
never be closed or barricaded again. It drops 1 or 2 planks into the zone on the
side it was hit from. When a window's health reaches 0 it is **smashed**: the
frame stays, and can still be barricaded.

### When the way opens

The barrier stops blocking because it broke, a window smashed, the last plank
went, or the player opened it. Every zombie thumping it stops and gets a
cooldown of 2 minutes. Thumps still unspent that minute are dropped and the
released zombie's carry is 0. Then:

- **The lunge.** If the player is at the barrier (`d_b` 1), the zombie lunges
  through: it is chasing, has just seen the player, and stands at gap 2, in the
  player's zone.
- **Otherwise** it walks to where it last knew the player to be: it is alerted
  with a sound gap of `d_b + 1`, and spotting takes over.

### Stopping

A thumping zombie keeps thumping. Its memory runs out as usual, but that doesn't
stop it. It stops only when:

- the way opens;
- it is killed;
- it hears a sound of radius 10 or more that isn't a zombie's, from its own
  side. Only the player makes those, so this happens when the player is on the
  zombie's side. It becomes alerted toward that sound and gets its cooldown.

A thumper behind a window it can see through (no barricade, or 1 or 2 planks)
still rolls spotting each minute at `facing_cos` 1 with its gap. Behind a closed
door or 3 or more planks it can't.

### Where thumping sits in the minute

A new step **3a** of the minute loop, after movement and before spotting: each
thumping zombie, in id order, deals its thumps for the minute. Barriers that
break or open in step 3a release their thumpers in the same step, and those
zombies take part in spotting and attacks from that minute on.

## Sounds

| Sound | Radius | Volume | Heard by zombies |
| --- | --- | --- | --- |
| A zombie's thump | 20 | 20 | no |
| A door or window breaking | 10 | 20 | yes, except by the zombies that were thumping it |
| The player hitting a door, window or barricade | 20 | 20 | yes |
| Hammering a plank on | `ceil(20 × hammer_mod)` | the same | yes |
| Prying a plank off | 10 | 1 | yes |
| Opening or closing | none | | |

- `hammer_mod` by Carpentry: 1.0 at 0 and 1, 0.8 at 2, 0.6 at 3, 0.4 from 4. A
  plank is 20 tiles of noise for a novice and 8 for a carpenter.
- A barrier sound is heard as if made where the player stands. Sounds made in
  step 3a are heard in the next minute's step 2. The player's own barrier sounds
  are step 1 sounds of their minute. A `BARRICADE` makes **one** hammering sound.

### Stress from sounds

Thumps, breaks and smashes add stress to the player: a thump adds
`0.0048 × (1 − d_b / 20)` and a break or smash `0.0048 × (1 − d_b / 10)`, when
the barrier is one of the player's zone and `d_b` is below the radius. One zombie
at the apartment door with the player across the room (`d_b` 4) adds about
0.0076 stress a minute, **0.45 per game hour**. The stress of a chunk of minutes
is summed over the zombie minutes and added with the stats of that chunk.
**Deaf** characters get none.

## Opening and closing

### `OPEN <barrier>` / `CLOSE <barrier>`

**0 minutes**, after the walk to the barrier if the player isn't at it. A turn
with nothing else costs the one-minute floor.

- **Refused** (0 minutes):
  - not a barrier of the player's zone ("There's no door here.");
  - already open, or already closed;
  - broken ("There's no door left to close."), or a smashed window;
  - barricaded on either side ("The apartment door is barricaded.");
  - locked, from the outside, without the key ("It's locked."). From the inside
    it opens without a key and unlocks.
- **Effect:** `open` flips. Opening a barrier zombies are thumping releases them;
  with the player at it, they lunge.

### `MOVE_TO` through a barrier

`MOVE_TO` crosses each barrier on its route in order:

- **A closed door:** the player opens it (a locked one from inside unlocks),
  passes, and shuts it again behind them. An open door stays open. A broken door
  is a gap. Each costs 0 minutes.
- **A locked door or window from outside, no key:** the move stops at it ("at
  the locked door to Your Apartment"); a window stays closed.
- **A barricade on either side:** the move stops at it ("at the barricaded
  door"). The player can't remove someone else's planks, only break them.
- **A window:** an open or smashed window is climbed through, **+1 minute**. A
  closed, unlocked one is opened first and stays open.
- **Zombies already thumping the far side:** opening the door releases them onto
  the player.

The player ends the move at the last barrier they came through (`d_b` 1). Every
chaser in the zone the player left, behind a door the player closed, becomes a
thumper there, except the zombies that opening the door released. Followers cross with the player.

## Barricading

### `BARRICADE <barrier>`

Nails **one plank** on the player's side.

- **Time:** 200 timed-action frames, so **1 minute**, before the action-time
  multiplier of pain, mood and cold.
- **Needs**, carried or in hand: a hammer with condition above 0, a plank, and
  one nail. The plank with the most condition is used first.
- **Refused** (0 minutes): not a barrier of the player's zone; an open door
  ("Close it first."); a broken door ("There's nothing left to board up."); 4
  planks already on this side; no hammer, plank or nail ("Orton has no nails.").
- **Effect:**

  ```
  plank_health = int(int(plank.condition / plank.condition_max × 1000) × barricade_mod)
  ```

  `barricade_mod` by Carpentry level 0 to 10: 1.0, 1.0, 1.1, 1.14, 1.18, 1.22,
  1.26, 1.3, 1.34, 1.4, 1.5. A full plank is 1000 at Carpentry 0 and 1500 at 10.
  The plank and one nail leave the inventory.
- **Hammer wear:** the hammer loses 1 condition with chance
  `1 / (int(condition_lower_chance × 6) + Carpentry + upkeep)`, where upkeep is
  Maintenance plus half the held weapon's skill level, rounded down. That is
  about 1 in 180 for the hammer. A hammer that reaches 0 snaps and goes to the
  inventory.
- **Noise:** one hammering sound.
- **XP:** Carpentry **+10** through the full XP chain. With no Carpentry boost
  that is +2.5.
- **Metabolic target:** heavy work.

A barricade can go up while zombies thump the other side. Their next thump lands
on it.

### `UNBARRICADE <barrier>`

Takes the **outermost plank** off the player's side.

- **Time:** 200 frames less 5 per Carpentry level, less 20 with **Handy**:
  **1 minute** at every level. Before the action-time multiplier.
- **Needs** a carried tool that pries planks: the hammer or the crowbar.
- **Refused** (0 minutes): no planks on the player's side ("The planks are on
  the other side."), or no planks at all, or no tool.
- **Effect:** the player gets a plank with condition
  `int(max(condition_max × min(plank_health / 1000, 1), 1))`. A hard-hit plank
  comes back weak. The nail is lost. With a full pack the plank lands on the
  floor.
- **Noise:** prying, radius 10.
- **XP:** Carpentry **+2** and Strength **+2**, both flat: the XP chain's
  multipliers don't apply.
- **Metabolic target:** light work.

## Breaking through

`ATTACK <barrier>` is a swing at a door, window or barricade: **1 minute**, after
the walk to it. It hits the first of: the barricade on the player's side, the
barricade on the far side, the door or window. An open or broken barrier with no
planks can't be hit ("There's nothing to hit.").

`door_damage` is the weapon's door damage: crowbar 8, hammer 9, hand axe 20, baseball bat 5, frying pan 3, plank 5,
kitchen knife 1, bare hands 0.

| Target | Damage per hit |
| --- | --- |
| A door | `int(door_damage × 2 × m)`, and with chance 1 in 10 another `int(door_damage × 6 × m)` |
| A barricade | `door_damage × 5`, to the outermost plank |
| A window | smashed outright, by any hit |

`m` by Strength level 0 to 10: 0.5, 0.63, 0.76, 0.89, 1.02, **1.0**, 1.15, 1.27,
1.3, 1.45, 1.7. Level 5 keeps 1.0, below level 4.

| Weapon | A door at Strength 5 | A plank |
| --- | --- | --- |
| Crowbar (8) | 16, or 64 on the 1 in 10: about 24 swings | 40: 25 swings |
| Hammer (9) | 18, or 72: about 22 swings | 45: 23 swings |
| Kitchen knife (1) | 2, or 8: about 190 swings | 5: 200 swings |
| Baseball bat (5) | 10, or 40: about 38 swings | 25: 40 swings |
| Frying pan (3) | 6, or 24: about 64 swings | 15: 67 swings |
| Hand axe (20) | 40, or 160: about 10 swings | 100: 10 swings |
| Bare hands (0) | nothing, but the noise carries | nothing |

- **Endurance:** the swing's usual cost, plus, for a hit on a door itself, by
  Fitness level 0 to 9: 0.01, 0.007, 0.0065, 0.006, 0.005, 0.004, 0.0035, 0.003,
  0.0025, 0.002; nothing at 10. × 0.9 with **Jogger**.
- **Weapon wear and Maintenance XP:** the usual weapon-condition roll. No weapon
  skill XP.
- **A window by hand:** bare hands smash it too.
- **Noise:** the hit sound, and a break sound when it gives.
- The door breaks as under [Breaking](#breaking). A barricade broken from the far
  side drops nothing.

## Items

| Item | Values |
| --- | --- |
| Hammer | one-handed small blunt, 0.5 to 1.0 damage, reach 1.1, crit 20% × 3, condition 10, wear 1 in 30, 1.5 kg, door damage 9; pries planks |
| Plank | two-handed blunt, 0.4 to 0.6, reach 1.3, hits 2, crit 30% × 2, condition 10, wear 1 in 2, 3 kg, door damage 5 |
| Nails | a stack of 5; one is spent per plank |

The crowbar also pries planks off. A plank used as a weapon wears like any other,
and a worn plank makes a weaker barricade.

**Where they are:**

- `zone_building`, the basement storage: a Hammer, Nails (5) and 2 Planks.
- `zone_street`, the alley: 2 Planks.
- Every broken door: 1 or 2 Planks.

## Interruptions

- **A zombie starts thumping a barrier of the player's zone** and the player can
  hear it (`d_b` of 20 or less, not Deaf): a `WAIT` or `EXERCISE` stops. A `SLEEP`
  doesn't, and a thumper that is only heard never counts as a newly seen zombie.
  Once per barrier until the thumping stops.
- **A plank breaks** on a barrier of the player's zone: a `WAIT` or `EXERCISE`
  stops.
- **A barrier of the player's building breaks or smashes** (or of the player's
  zone, outdoors): any action stops, and a sleeper wakes.

Every interruption cancels the rest of the plan.

## Traits

| Trait | Effect |
| --- | --- |
| Deaf | no stress from thumps and breaks; thumping isn't heard, and a thumper is perceived only when seen through glass |
| Jogger | endurance per door hit × 0.9 |
| Handy | −20 frames on unbarricading; it rounds away at our resolution |

## Skills and XP

| Skill | Source | Amount |
| --- | --- | --- |
| Carpentry | each plank nailed | +10, through the XP chain |
| Carpentry | each plank pried off | +2, flat |
| Strength | each plank pried off | +2, flat |
| Maintenance | each weapon hit on a barrier | the usual roll |

Carpentry also raises a plank's health and quiets the hammer. Strength sets the
door-damage factor `m`; Fitness the door-hit endurance.

## Hooks into earlier specs

- **Game clock:** `OPEN` and `CLOSE` cost 0 minutes; `BARRICADE`, `UNBARRICADE`
  and `ATTACK` on a barrier 1; walking to a barrier 1; climbing through a window
  +1. `BARRICADE` and `UNBARRICADE` take the action-time multiplier.
- **Survival stats:** stress gains the sounds source.
- **Body temperature:** the metabolic table is used for heavy work while
  barricading and light work while unbarricading.
- **Skills:** Carpentry's first XP sources and effects; unbarricading gives
  Strength XP. `SkillEngine.add_xp` can add XP flat.
- **Zombies:** the thumping state and step 3a replace "a closed door holds".
  Door, glass and hammering sounds join the noise table. A zone cut off by
  blocking barriers gains no new zombies.
- **LLM contract:** four new verbs; `ATTACK` takes a barrier; a
  `[DOORS AND WINDOWS]` block for the parser and the narrator; `[THREATS]` gains
  thumpers.
- **Melee combat:** a swing at a barrier uses the same endurance cost and weapon
  wear.
- **Health:** `BARRICADE` and `UNBARRICADE` are slowed like the other timed
  actions.

## What the narrator and the player see

- **Facts:**
  - "Something starts pounding on the apartment door."
  - "Orton nails a plank across the apartment door."
  - "Orton pries a plank off the apartment door."
  - "A plank on the apartment door splinters."
  - "The apartment door bursts from its hinges." / "Glass shatters: the window
    gives."
  - "Orton slams the crowbar into the apartment door." (no damage numbers)
  - "The crash wakes Orton."
  - "The apartment door is barricaded."
- **`[DOORS AND WINDOWS]`** (parser and narrator): one line per barrier of the
  player's zone, in words and counts only: "apartment door (to Your Building):
  closed, locked; 3 planks on this side; something pounding on the other side".
  Door and plank health are never shown.
- **`[THREATS]`:** a thumper the player can see through glass (2 planks or fewer)
  is listed by id, "z4, behind the lobby window, pounding". One only heard is
  "something at the apartment door".
- **Parser:** the block's names are the targets for `OPEN`, `CLOSE`, `BARRICADE`,
  `UNBARRICADE` and `ATTACK`. "Board up the door" with 3 planks is three
  `BARRICADE`s.
- **UI:** the `/play` payload has `barriers: [{id, name, state_word, planks_here,
  planks_far, thumping}]`. The Nearby screen lists them with a state tag, plank
  counts on each side and a "Pounding" tag.

## Saves

Schema 18 adds `world.barriers` (each barrier's open, broken, locked and health
state and both sides' plank healths), each zombie's `thump_barrier`,
`thump_rate`, `thump_carry`, `thump_cooldown` and `was_chasing`, the player's
current barrier, and the Nails' `uses`. A barrier missing from a save is rebuilt
from the data. Saves of other versions are discarded and a new game starts.

## Edge cases

- **One zombie at the apartment door.** It pounds until something changes, for
  ever if nothing does, and the player's stress climbs. The door never breaks.
- **Boarding up against one zombie.** Each plank buys about 2 hours 50 minutes at
  Carpentry 0, and then the bare door holds against it. Against two or more,
  planks are the only thing between the player and the door's 42 minutes.
- **Barricading the wrong side.** Planks on the building side of the apartment
  door can't be pried off from inside. The player has to break them, or leave
  another way.
- **Opening into the dead.** `OPEN` on a door with thumpers behind it, from
  `d_b` 1, puts them at gap 2 and chasing: next minute they are on the player.
- **Closing the door on a chaser.** Allowed. A chaser behind it becomes a thumper
  at `d_b + 1`.
- **A story beat across planks.** A beat that moves an NPC across a barrier with
  planks is skipped, and the skip is logged. Closed and locked doors don't stop
  beats.
- **A broken door.** It stays broken. `CLOSE` and `BARRICADE` refuse it, and
  redistribution passes it.
- **`ATTACK` on a zombie behind a door.** Refused: "It's on the other side of the
  door." Hitting the door is `ATTACK` on the door.
- **The last plank of a window.** The zombie climbs in the same minute.
- **The outbreak starts with the lobby door shut.** `zone_building`'s zombies are
  already inside; the street's can only get in by chasing the player to the door.
- **Determinism.** The pounding style roll, the door-hit 1 in 10, the planks a
  broken door drops and the hammer wear use the simulation's injected random
  source, in that order, thumpers in id order.

## Testing

- `tests/world/test_barriers.py`: blocking, vision, the order a thump lands, thump and
  hit damage, plank health, distance, stress.
- `tests/zombies/test_thumping.py`: the three rates, starting, the two-zombie rule, break
  times, release, stopping, sounds, the cut-off zone.
- `tests/world/test_barricade.py`: the verbs, their refusals and costs, XP, hammer wear,
  sounds, hits on barriers, window crossing.
- `tests/test_simulation.py`: `MOVE_TO` through doors, interruptions, stress,
  story beats.
- `tests/test_validator.py`, `tests/test_items.py`, `tests/test_context.py`,
  `tests/test_plan_schema.py`, `tests/test_engine.py`, `tests/test_persistence.py`.
