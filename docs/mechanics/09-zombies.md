# Zombies

> **Status: Implemented.**

Once the outbreak starts, the world holds individual zombies. Each one is rolled
with its own health, speed, sight, hearing and memory, and lives in a zone at a
set population density. They notice the player by sight and by noise, chase at
their own speed, forget the player after a short while, and attack with a
defence roll, a wound roll and a drag-down rule.

The world has zones, not tiles, so every zombie carries one number the formulas
need: its **gap**, the distance in tiles between it and the player. Everything is
stepped minute by minute.

What the player does to a zombie (damage, crits, knockdowns, shoves, weapon
wear) is left to the melee mechanic. Wounds land in a body part; bleeding,
infection and the limp belong to the [health mechanic](12-health-and-infection.md).

## What we port

| Piece | File |
| --- | --- |
| `ZombieEntity` and its states | `modules/entity/zombie.py` |
| Zone `size_tiles`, `chunks`, `zombie_intensity`; the outbreak time, the zombies, the kill counts | `modules/world/location.py` |
| `Pace`, the four ways the player moves | `modules/world/pace.py` |
| `PlayerEntity.sneaking` | `modules/entity/player.py` |
| `MOVE_TO ... run`, `STANCE`, the zombie `ATTACK` target | `modules/action/types.py`, `modules/action/parser.py`, `modules/resolution.py` |
| The story effect that starts the outbreak | `modules/story/beats.py`, `managers/simulation.py` |
| Every number below | `data/zombies/lore.py`, `data/world/locations.py` |
| Hop minutes by pace, the approach minutes on an `ATTACK` | `data/time_costs.py` |
| Rolling, population, spotting, hearing, movement, memory, the minute loop, the threat words | `managers/zombies/population.py` |
| Footstep and cough noise | `managers/zombies/noise.py` |
| The defence roll, drag-down, wounds, clothing defence and holes | `managers/zombies/attack.py` |
| Running the loop before each stat chunk, interruptions, pace on a walk | `managers/simulation.py` |
| Zombie ids, `STANCE` and pace in the validator | `managers/validator.py` |
| The `[THREATS]` block | `managers/context.py` |
| `threats` and `sneaking` in the page payload | `adapters/engine.py`, `static/app.js` |
| Saving the outbreak | `adapters/save/codec.py` |

## Settings

There are no sandbox settings. The values the rest of this document uses:

| Setting | Value |
| --- | --- |
| Zombie strength | 3, so three attackers drag the player down |
| Speed | half Shamblers, half Fast Shamblers; no sprinters |
| Health | 0.5 to 3.8 |
| Cognition | zombies can't open doors |
| Memory | 800 ticks (see [The minute loop](#the-minute-loop)) |
| Sight and hearing | each zombie is Normal or Poor, 50/50 |
| Population multiplier | 0.65; start 1.0, peak 1.5 on day 28 |
| Redistribution | every 12 game hours |
| Respawn | none |
| The player's spawn building | starts clear of zombies |

## The outbreak

`World.outbreak_started_at` holds the game minute the dead started walking, or
nothing before that.

- While it is empty there are **no zombies**, and the minute loop does nothing.
- The story effect `start_outbreak` sets it to the current minute. Nothing else
  does. The simulation core applies it with `apply_story_effect`.
- At that moment every zone is populated ([Population](#population)). The
  player's own zone is too, so the dead can already be close. Every zombie in
  view then counts as newly seen on the next minute.
- "Days since the outbreak" is `(now − outbreak_started_at) / 1440` and drives
  the population curve.

Zombies ignore NPCs.

## Zones

| Zone | `size_tiles` | `chunks` | `zombie_intensity` | Target at the outbreak |
| --- | --- | --- | --- | --- |
| `zone_home` | 8 | 1 | 0 | 0 (spawn building cleared) |
| `zone_building` | 20 | 3 | 32 | about 2 |
| `zone_street` | 40 | 6 | 96 | 9 |
| `zone_bodega` | 10 | 1 | 63 | about 1 |
| `zone_neighborhood` | 80 | 16 | 64 | 16 |
| `zone_flat_vacant` | 8 | 1 | 0 | about 0.04 |
| `zone_flat_tenant` | 8 | 1 | 64 | about 1 |
| `zone_pharmacy` | 14 | 2 | 63 | about 2 |
| `zone_clinic` | 20 | 3 | 48 | about 2.3 |
| `zone_supermarket` | 30 | 6 | 63 | about 6 |
| `zone_hardware` | 20 | 3 | 63 | about 3 |

`size_tiles` is the farthest a zombie in the zone can be from the player.
`chunks` counts 8×8-tile chunks. `zombie_intensity` is a byte, 0 to 255.

Every connection between zones is **40 tiles** (`HOP_TILES`), the distance the
player covers in one 10-minute hop at walking pace.

## Population

The target count of a zone:

```
per_chunk = 0.06 + 11.94 × (zombie_intensity × 0.5 / 255)
target    = chunks × per_chunk × 0.65 × curve(days)
```

`curve(days)` rises linearly from 1.0 at the outbreak to 1.5 on day 28, then
holds: 1.25 on day 14. Only the outbreak fill leaves the spawn zone empty; every
redistribution after it works from the curve, so the spawn zone's target is
about 0.04 and a zombie can very rarely be placed there.

The fractional part of the target is rounded at random: 2.4 is 2 with a 60%
chance and 3 with a 40% chance, using the simulation's own random source.

- **At the outbreak:** each zone gets its day-0 target.
- **Redistribution:** every 12 game hours after the outbreak, each zone's target
  is recomputed from the curve. Idle zombies move one hop at a time from zones
  above their target to adjacent zones below theirs, and zones still below target
  then gain new zombies, but only as many as the zone's kills leave room for.
  Zones go in map order and idle zombies in id order. Each zombie goes to the
  neighbour with the largest deficit (ties to the earlier zone) and moves once.
  A zombie arriving in the player's zone gets a gap and a facing.
- **No respawn:** a killed zombie is gone for good. The zone's kill count keeps
  its population from growing back over it.
- **Closed doors:** redistribution never moves a zombie across a blocking door or
  window, and a zone whose every connection is blocked gains no new zombies; see
  [doors](13-doors-and-barricades.md#thumping).

## A zombie

Each zombie is rolled once:

| Field | Rolled as |
| --- | --- |
| `zombie_id` | `z1`, `z2`, … in order of creation |
| `health` | 0.5 to 3.5 plus 0 to 0.3 |
| `speed_type` | 50% Shambler (3), 50% Fast Shambler (2) |
| `speed_mod` | Shambler: 0.55 to 0.70. Fast Shambler: with 2/3 chance the same shambling gait, otherwise 0.85 to 1.0 and `lunger` is true |
| `strength` | 3 |
| `memory` | 800 |
| `sight`, `hearing` | 2 (Normal) or 3 (Poor), 50/50 each |

Runtime fields, all saved: `state`, `gap`, `facing_cos` (−1 to 1, how directly it
looks at the player), `time_since_seen` (ticks, starts at 100000), `has_chased` (set the first time it
spots, is hit by, or reaches the player; never cleared),
`bonus_spot_time` (ticks), `side` (while attacking) and `sound_gap` (while
alerted).

### States

- **idle:** stands about. It re-draws `facing_cos` uniformly in [−1, 1] each
  minute, because there is no wander path.
- **alerted:** heard a sound and walks toward it, facing the way it walks.
- **chasing:** has spotted the player, faces them and closes the gap.
- **attacking:** within 1 tile; attacks each minute.
- **thumping:** held at a blocking door or window, pounding on it; see
  [doors](13-doors-and-barricades.md#thumping). A new step 3a of the minute loop
  deals its thumps.

A zombie at 0 health is removed from the world.

## The minute loop

The loop runs in 1-minute steps for every minute an action spends, before the
stat chunk that covers that minute. It runs only after the outbreak. Each minute:

0. **Swing:** the player's `ATTACK` or `SHOVE`, if this minute is one ([Melee Combat](11-melee-combat.md)).
1. **Sounds:** the player's sounds ([Noise](#noise)).
2. **Hearing:** each idle or alerted zombie checks the loudest sound it hears.
3. **Movement:** alerted and chasing zombies close their gap; the player's own
   movement opens it.
   3a. **Thumping:** each thumping zombie deals its thumps ([doors](13-doors-and-barricades.md#thumping)).
4. **Spotting:** each idle or alerted zombie in the player's zone, and each
   chasing zombie, rolls to see the player.
5. **Memory:** timers advance; a chaser that lost the player goes idle.
6. **Attacks:** every zombie at gap 1 or less attacks, unless it is down or staggered.
7. **Interruption check.**

A minute is 180 ticks. A per-tick chance `p` becomes `1 − (1 − p)^180` for the
minute, and a tick timer advances by 180 per minute.

Redistribution is checked at the start of each minute.

### Where the zombies are

- **In the player's zone:** every zombie has a gap from 1 to `size_tiles`. When
  the player enters a zone, each zombie there that isn't already hunting gets a
  fresh gap, drawn uniformly, and a random facing.
- **In other zones:** a zombie one hop away is 40 tiles from the player for
  hearing, two hops 80. Its place inside its zone doesn't matter until the
  player arrives.
- **Chasers** keep their own gap across zone changes. A chaser belongs to the
  player's zone while its gap is within that zone's size, and otherwise to the
  zone the player just left. A chaser that is not in the player's zone joins it
  once its gap is within the zone's size.

## Pace

| Pace | Speed | Minutes per hop | Footsteps | Spotting factor |
| --- | --- | --- | --- | --- |
| walk (default) | 4 tiles per minute | 10 | walk | 1.0 |
| run | 8 tiles per minute | 5 | run | 1.5 |
| sneak | 2 tiles per minute | 20 | sneak | 0.8 |
| standing still (any other action) | 0 | | none | 0.8 |

- `MOVE_TO <place> run` runs. Any other `MOVE_TO` walks, or sneaks while the
  player is sneaking. Running ends sneaking.
- `STANCE sneak` and `STANCE stand` toggle `player.sneaking`. They take no time.
  Sneaking applies its spotting modifier even when standing still.
- Running minutes count as exercise for the stat engine, so they drain
  endurance at the running rate.
- A walk is made one hop at a time. The player enters each new zone for the last
  minute of its hop, so zombies there can notice them that minute. Before the
  outbreak the whole hop is spent in the new zone.

## Noise

A sound has a **radius** and a **volume**, both in tiles.

**Footsteps**, each minute the player moves:

```
volume = pace_speed × 1.4        (walk 0.5, run 0.75, sneak 0.25)
         × 0.6 if Graceful, × 1.2 if Clumsy
         × 0.5 if no shoes are worn
         × lightfoot_mod(Lightfooted level)
         × (2 − nimble_mod(Nimble level))
         × sneak_spot_mod(Sneaking level) if sneaking
radius = ceil(volume × 10); halved and rounded down indoors; at least 1 while sneaking
```

| Level | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `lightfoot_mod` | 0.99 | 0.90 | 0.79 | 0.71 | 0.65 | 0.59 | 0.52 | 0.45 | 0.37 | 0.30 | 0.20 |
| `nimble_mod` | 1.00 | 1.10 | 1.14 | 1.18 | 1.22 | 1.26 | 1.30 | 1.34 | 1.38 | 1.42 | 1.50 |
| `sneak_spot_mod` | 1.14 | 1.08 | 0.96 | 0.90 | 0.84 | 0.78 | 0.72 | 0.66 | 0.60 | 0.54 | 0.48 |

A default character makes 7 tiles of noise walking, 11 running and 4 sneaking
outdoors, and 3, 5 and 2 indoors. The sound's volume equals its radius.

A moving minute is 8 steps. Each step makes a sound with chance 1/2 (while
sneaking, 1 in `min(12, 4 + Lightfooted)`), so the minute makes a sound with
chance `1 − (1 − 1/odds)^8`: 99.6% walking or running, 90% sneaking at
Lightfooted 0.

| Other sound | Radius | Volume |
| --- | --- | --- |
| Cough or sneeze (from the cold) | 35 | 40 |

A cough or sneeze the stat chunk produces is heard on the next minute of the
loop.

## Hearing

For a zombie at distance `d` from a sound:

```
radius   = sound.radius × hearing_factor × weather_factor
hearing_factor = 1.0 (Normal) or 0.45 (Poor)
weather_factor = 1 − 0.33 × rain − 0.1 × fog
delta    = d² / radius²
           × 1.2 if the zombie and the player are in different zones
           × 1.4 more if one of the two zones is indoors and the other isn't
attract  = sound.volume × clamp(1 − delta, 0, 1)
```

The zombie hears the sound when `d ≤ radius` and `attract > 0`. `d` is the
zombie's gap, or its hop distance from another zone.

An idle zombie that hears a sound becomes **alerted**, with `sound_gap = d`, and
walks toward it. When `sound_gap` reaches 0 it goes back to idle where it
stands. An alerted zombie in another zone that gets within the player's zone
size enters it, with its gap equal to what remains. A zombie alerted inside the player's zone
walks to the sound and idles there; if the player leaves the zone first, it goes
idle where it stands instead of following. An alerted zombie that
reaches the player becomes a chaser. A blocking door or window between an alerted or
chasing zombie and the player stops it, and it thumps on it; see
[doors](13-doors-and-barricades.md#thumping).

## Spotting

`spot_chance` runs for every idle or alerted zombie in the player's zone and
every chasing zombie:

1. `chance = 100 × light`. Outdoors, light is daylight. Indoors with power it is
   1.0; indoors without power it is `0.6 × daylight`.
2. Vision radius: `20 − max((1 − light) × 5, rain × 2.5 + fog × 7)`, times 0.35
   for Poor sight, then clamped to 10 to 20. If the gap is larger, `chance` is 0.
   The clamp comes after the sight factor, so a Poor-sight zombie still sees 10
   tiles.
3. Facing (`facing_cos`): below −0.4 → 0; below −0.2 → ÷8; below 0 → ÷4; below
   0.2 → ÷2; up to 0.4 → ×2; up to 0.6 → ×8; up to 0.8 → ×16; above → ×32.
4. × the pace's spotting factor.
5. × 3 if the gap is under 5 tiles and the player isn't sneaking.
6. × `sneak_spot_mod` if sneaking.
7. × 5 while `bonus_spot_time` is above 0.
8. × 0.45 for Poor sight.
9. × 0.8 Inconspicuous, × 1.2 Conspicuous.
10. Round down, cap at 400, divide by 400: that is `p`, the per-tick chance.

**On success:** `time_since_seen` is 0, `bonus_spot_time` is 720 ticks, and the
zombie is chasing. If it wasn't chasing before, that is a new sighting
([Interruptions](#interruptions)).

**Sneak XP:** while the player sneaks and moves, in a minute in which at least
one zombie rolled, none noticed them, and none had a spot figure above 20 within
15 tiles, Sneaking and Lightfooted each gain 1 XP with chance
`1 − (1 − 1/1100)^180`, about 15.1%.

## Movement

Each minute:

- **Chasing** zombies close the gap by `4 × speed_mod × clamp(gap / 24, 1, 1.3)`
  tiles.
- **Alerted** zombies close their gap and `sound_gap` at the same rate.
- **The player's movement** adds the player's pace speed to every chaser's gap
  while a walk is under way.

So a Shambler (0.55 to 0.70) falls behind a walking player, a lunger (0.85 to
1.0) about keeps pace, and running outpaces both. A gap never falls below 1.

## Memory

- `time_since_seen` rises by 180 each minute and resets to 0 on every success.
  `bonus_spot_time` falls by 180 each minute, to 0.
- When `time_since_seen` is above 800 (the fifth minute without a sighting) a
  chaser drops the player and goes **idle**.
- A chaser rolls its spot every minute at `facing_cos` 1, so it loses the player
  mainly by being outdistanced past its vision radius, or by darkness.

## Zombie attacks

A zombie at gap 1 or less in the player's zone is **attacking**.

- **Sides.** The first attacker takes `front`. Each later one takes a side drawn
  uniformly from `front`, `left`, `right` and `behind`.
- **Rate.** Each attacker makes one attack per game minute.
- **Attackers** is the number of zombies attacking.

Each attack, in order:

1. **Defence**, only from the front and with at most 3 attackers:

   ```
   defend = 3 × weapon_level + 2 × Fitness + 2 × Strength
            − 5 × attackers − 2 × Endurance status effect − 2 × Heavy Load status effect
            − 3 × Tired status effect − 2 × Drunk status effect
   ```

   A roll of 0 to 99 below `defend` defends: the player shoves the zombie off and
   the attack ends. `weapon_level` is the held weapon's category skill minus 1
   (an axe takes the Axe level whole), at most 10, with 0 for bare hands and
   whenever the result would be below 0. Heavy Load is 0 for now.
2. **Drag-down**, if the attack wasn't defended: with 3 or more attackers the
   player is pulled down and killed. The game ends with "<name> was dragged down
   by the dead."
3. **Wound odds:**

   ```
   base       = 15 + combat_mod(weapon_level) − 10 × (attackers − 1)
   bite       = 85 − 30 × (attackers − 1)
   laceration = 65 − 15 × (attackers − 1)
   behind:     base −15, bite −25, laceration −35; bite and laceration −15 more with over 2 attackers
   left/right: base −30, bite −7, laceration −27
   ```

   `combat_mod` by weapon level 0 to 10: −5, −2, 0, 1, 2, 3, 4, 5, 5, 6, 7.
   Thick Skinned multiplies `base` by 1.3 and Thin Skinned divides it by 1.3,
   rounding toward zero.
4. **Body part**, in this order: `hand_l`, `hand_r`, `forearm_l`, `forearm_r`,
   `upperarm_l`, `upperarm_r`, `torso_upper`, `torso_lower`, `head`, `neck`,
   `groin`, `upperleg_l`, `upperleg_r`, `lowerleg_l`, `lowerleg_r`, `foot_l`,
   `foot_r`. One time in 10
   it is drawn from the first 11, otherwise from the first 10. From behind, with
   chance `10 × attackers + 5`%, it is the neck. A head or neck result is
   redrawn from the arms and torso when a roll of 0 to 99 is above 70 (80 from
   the side, 90 from behind), so it stands about 71% of the time from the front.
5. **Damage:** a thousandth-step fraction times `(0 to 9) + 10`, so 0 to 19.
6. **Kind:** a roll above `base` wounds; otherwise the blow only thumps. A wound
   is a scratch, which becomes a laceration if a roll is above `laceration`, and
   either becomes a bite if a roll is above `bite`.
7. **Clothing:** the part's defence is the sum, over worn items covering it with
   no hole there, of the item's bite defence (for a bite) or scratch defence
   (scratch or laceration), times the item's neck protection on the neck, rounded
   down and capped at 100. A roll below it blocks the hit: no wound, and the
   clothing is not torn. Otherwise every worn layer covering the part gets a hole
   there and the wound lands.
8. **The wound lands.**

A sleeping player is woken by the first attack.

## Wounds

A landed wound takes `damage` off its body part, which lowers overall health by
`damage × the part's weight`:

| Part | Weight |
| --- | --- |
| Hands | 0.1 |
| Forearms, shins, feet | 0.2 |
| Upper arms, thighs | 0.3 |
| Upper torso | 0.35 |
| Lower torso, groin | 0.4 |
| Head | 0.6 |
| Neck | 0.7 |

Whether a wound carries the zombie infection is rolled with it: a bite always, a
laceration 25%, a scratch 7%. The part keeps the result, and the
[body](12-health-and-infection.md#zombie-infection) does the rest.

## Zombies going down

- `ATTACK` targets a zombie by id, or "zombie" for the nearest one the
  player perceives. A zombie in another zone, or one the player can neither see
  nor hear, is refused.
- If the target is more than 1 tile away the player first walks up to it at
  4 tiles per minute: `ceil((gap − 1) / 4)` minutes, added to the swing's 1
  minute. Zombies act during them.
- The swing always connects. What it does to the zombie, and the kill, are in
  [Melee Combat](11-melee-combat.md).
- At 0 health the zombie is killed and removed, and leaves a corpse ([The Zombie Lifecycle](14-zombie-lifecycle.md#corpses)); its zone's kill count goes up.

## Interruptions

An action's remaining minutes are **not spent** when, during a minute:

- a zombie newly spots the player,
- a zombie reaches gap 1, or
- the player is attacked.

The target's own spotting and arrival never count. During the swing of an
`ATTACK` or `SHOVE`, attacks interrupt only when they wound or drag the player
down. During the approach minutes an attack by any zombie other than the target
interrupts too, even when defended.

The action's effects are applied up to that point and the stats advance only
over the minutes that passed. A `MOVE_TO` stops in the zone the player had
reached; a `WAIT` or `SLEEP` ends; an exercise stops with its reps so far. The
fact says why ("A zombie notices Orton and heads straight for him."), and the
rest of the turn's plan is dropped.

## Hooks into earlier specs

- **Survival stats:** `new_zombies_seen` counts zombies that came into view
  during the chunk, for the first time since they were last out of sight. A
  sighting or any interruption wakes a sleeping player in a panic. Minutes with
  an attacking zombie, or at run pace, count as exercise.
- **Status effects:** the defence penalties are wired into the defence roll.
- **Clothing:** `holes` are written by wounds; clothing defence comes from the
  items' `scratch_defense`, `bite_defense` and `neck_protection`.
- **Body temperature:** coughs and sneezes make noise.
- **Character creation:** these traits now take effect: Inconspicuous,
  Conspicuous, Graceful, Clumsy, Thick Skinned, Thin Skinned, Keen Hearing, Hard
  of Hearing and Deaf.
- **Skills:** Sneaking and Lightfooted gain XP from sneaking past zombies;
  Fitness and Strength feed the defence roll.

## What the narrator and the player see

The player perceives a zombie in their zone when:

- **seen:** its gap is within `20 × max(0.25, light)` tiles, or
- **heard:** its gap is within the detection range:

  ```
  range = 2.0 if Deaf, else 3.5; +3 Keen Hearing; −1 Hard of Hearing
  range = 2 + (max(range, 2) − 2) × product of worn items' hearing modifiers above 0
  range = range − fatigue − intoxication × 0.01
  ```

- **Narrator:** a `[THREATS]` block lists each seen zombie by a distance word and
  what it is doing, never by id: "a zombie, close, coming at you", "a zombie, far
  off, hasn't noticed you", "a zombie, on you, right behind you". Zombie ids never
  reach the narrator: in its `[OUTCOMES]` and in the event log each id reads "the
  zombie".

  | Gap | Word |
  | --- | --- |
  | 1 or less | on you |
  | 5 or less | close |
  | 15 or less | nearby |
  | more | far off |

  | State | Words |
  | --- | --- |
  | idle | hasn't noticed you |
  | alerted | turning toward the noise |
  | chasing | coming at you |
  | attacking | attacking you, or right behind you from behind |

  A lunger that has chased the player reads "coming at you fast" in any state.
  A zombie that is only heard is "something shuffling nearby", or "something
  behind you" if it is hunting, never described and with no id. Health, speed
  type, sight and hearing are never shown. The block says "None" when nothing is
  perceived.
- **Parser:** its own `[THREATS]` block lists seen zombies as `z3 (close)`, so it
  can propose `ATTACK z3`, `MOVE_TO … run` and `STANCE sneak`.
- **Page:** the payload gains `threats: [{id, distance_word, state_word}]` and
  `sneaking`. The Nearby screen lists the threats in words, and the Status screen
  shows a Sneaking tag. A heard-only entry has no id and no distance.

## Saves

Schema version 13 adds `world.outbreak_started_at`, every zombie with its runtime
fields, the next zombie number, the last redistribution minute, the kill counts
and `player.sneaking`. A zombie in an unknown zone is dropped on load.

## Edge cases

- **Closed doors.** A blocking door stops an alerted or chasing zombie, which
  thumps on it. Redistribution never crosses one. See
  [doors](13-doors-and-barricades.md#thumping).
- **The outbreak starting mid-action.** The zones fill at that minute, the
  player's own zone included.
- **Asleep.** Spotting uses the standing-still factor and there are no
  footsteps. Any interruption wakes the player.
- **Three or more on you.** With exactly three attackers a front attack can still
  be defended, and a defended attack never drags the player down. With four or
  more, no defence is possible, so the first attack drags the player down.
- **Zero zombies.** Before the outbreak, and in empty zones, the loop does
  nothing.
- **Determinism.** Every roll uses the simulation's own random source, in loop
  order, so a seeded test replays exactly.
