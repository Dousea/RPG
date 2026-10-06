# Skills

> **Status: Implemented.**

The character has no overall level. They get better at each thing by doing it:
every skill has its own XP and a level from 0 to 10. This document covers the
skill list, the XP each level needs, how XP gains are scaled, where XP comes
from today, Fitness and Strength (including slowly losing them when untrained),
and the `EXERCISE` verb.

What a skill level does in a fight (hit chance, damage, crits, weapon wear) is
left to the melee mechanic. Only the skill effects that touch systems already
built are wired.

## What we port

| Piece | File |
| --- | --- |
| `SkillDefinition`, `SkillState` | `modules/character/skills.py` |
| `ExerciseDefinition`, `ExerciseState` | `modules/character/exercise.py` |
| The 35 skills, XP tables, XP multipliers, loss-timer numbers, trait table, recovery table | `data/skills.py` |
| The 7 exercises and their rep, regularity and stiffness numbers | `data/exercises.py` |
| `SkillEngine`: XP, levels, loss timers, trait swap, exhaustion and hit XP | `managers/skills.py` |
| `ExerciseEngine`: reps, regularity, stiffness, starting regularity | `managers/exercise.py` |
| `EXERCISE` action, resolution and validation | `modules/action/`, `modules/resolution.py`, `managers/validator.py`, `managers/simulation.py` |
| The `EXERCISE` time cost row (chosen minutes, or minutes run on an early stop; the resolver reads it) | `data/time_costs.py` |

## Skills

The 35 skills, in six categories.

| Category | Skills (id: name) |
| --- | --- |
| Combat | `axe`: Axe, `long_blunt`: Long Blunt, `short_blunt`: Short Blunt, `long_blade`: Long Blade, `short_blade`: Short Blade, `spear`: Spear, `maintenance`: Maintenance |
| Firearm | `aiming`: Aiming, `reloading`: Reloading |
| Crafting | `carpentry`: Carpentry, `carving`: Carving, `cooking`: Cooking, `electrical`: Electrical, `glassmaking`: Glassmaking, `knapping`: Knapping, `masonry`: Masonry, `blacksmithing`: Blacksmithing, `mechanics`: Mechanics, `pottery`: Pottery, `tailoring`: Tailoring, `welding`: Welding |
| Survivalist | `first_aid`: First Aid, `fishing`: Fishing, `foraging`: Foraging, `tracking`: Tracking, `trapping`: Trapping |
| Physical | `fitness`: Fitness, `strength`: Strength, `lightfooted`: Lightfooted, `nimble`: Nimble, `running`: Running, `sneaking`: Sneaking |
| Farming | `agriculture`: Agriculture, `animal_care`: Animal Care, `butchering`: Butchering |

Fitness and Strength are the two passive skills.

## XP and levels

XP needed for each level on top of the one before:

| Level | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Most skills | 75 | 150 | 300 | 750 | 1,500 | 3,000 | 4,500 | 6,000 | 7,500 | 9,000 |
| Fitness, Strength | 1,500 | 3,000 | 6,000 | 9,000 | 18,000 | 30,000 | 60,000 | 90,000 | 120,000 | 150,000 |

The XP to reach a level is the running total: 525 for level 3 of a normal skill,
67,500 for level 6 of Fitness. XP is capped at the level-10 total: 32,775 for
most skills, 487,500 for Fitness and Strength.

- Each skill is `SkillState(level, xp)`, with `xp` the total.
- At the start, the XP is set to the total for the starting level, for all 35
  skills.
- After XP changes, the level goes up while XP is at least the total for the
  next level (to at most 10), and down while XP is below the total for the
  current one. Only negative XP can lower a level.

## Gaining XP

`SkillEngine.add_xp(player, skill, amount)` returns the level-change facts.

1. **Asleep:** no XP at all, gain or loss.
2. **Boost multiplier**, from the starting boost:

   | Boost | Multiplier |
   | --- | --- |
   | none, or 0 | ×0.25 |
   | 1 | ×1 (Running ×1.25) |
   | 2 | ×1.33 |
   | 3 | ×1.66 |

   Fitness and Strength are always ×1 here. Running skips the ×0.25 but keeps
   the increases.
3. **Traits:** Fast Learner ×1.3 and Slow Learner ×0.7 (neither touches Fitness
   or Strength; Slow Learner also skips Running). Reluctant Fighter ×0.75 on
   Axe, Long Blunt, Short Blunt, Long Blade, Short Blade, Spear and Aiming.
   Crafty ×1.3 on the Crafting skills.
4. **Global multiplier:** ×1.0.
5. Add, clamp to 0 and the level-10 total, then raise or lower the level.

The multipliers apply to losses too. There is no book multiplier yet.

Each level change is a fact: "Your Short Blade skill is now level 3." or "Your
Fitness has dropped to level 4." One gain across two levels gives two facts.

## Where XP comes from

| Source | Rule | Status |
| --- | --- | --- |
| Melee hit on an NPC, per `ATTACK` | Fitness +1 if endurance is above 0.5; Strength +1 | Now |
| Melee hit on a zombie | See [Melee Combat](11-melee-combat.md#xp) | Now |
| Exhausted and not walking | Fitness +6 on each 10-minute boundary where endurance is below 0.25 and the player isn't walking (36 XP per game hour) | Now |
| Exercise | See [Exercise](#exercise) | Now |

Bare hands train only Fitness and Strength. A ranged hit trains nothing yet.
A hit on an NPC trains no weapon skill. Other sources
(wounds, first aid, sneaking, barricades, weapon upkeep, firearms, reading,
crafting, foraging, animals, vehicles) join with their mechanics.

## Fitness and Strength

### Losing them when you stop training

On each 10-minute boundary the clock crosses, both passive skills run a timer:

- The timer starts at −50,000 and rises by 10 every boundary.
- Every positive XP gain in that skill lowers it by 3,000, to at least −50,000.
- Above 20,000, each time `floor(timer / 1200)` changes, the skill loses 1 XP,
  then checks for a level loss.
- Above 31,000 the timer resets to 0.

So after about 49 idle days the skill loses 1 XP roughly every 20 game hours,
and the cycle restarts about 14 days later. The timers run while the player
sleeps, but no XP is lost then. Both timers and their last step are saved.

### Traits that follow the level

Whenever Strength or Fitness changes level, including at creation, the related
trait is replaced:

| Level | Strength | Fitness |
| --- | --- | --- |
| 0–1 | Puny | Unfit |
| 2–4 | Weak | Out of Shape |
| 5 | none | none |
| 6–8 | Stout | Fit |
| 9–10 | Strong | Athletic |

A Firefighter (Strength 5 + 1 = 6) starts Stout and Fit without buying either.
A trait that is already the right one keeps its place in the list. These traits
have no effect of their own yet.

### Effects wired now

| Effect | Where |
| --- | --- |
| Endurance regeneration (resting, standing and asleep) × a factor by Fitness level: 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.55, 1.6 for levels 0–10 | [Survival stats](02-survival-stats.md) |
| The Fitness stat in the heat balance is the Fitness level ÷ 5 − 1 (−1 to 1) | [Body temperature](06-body-temperature.md) |
| Exercise speed and regularity gain | [Exercise](#exercise) |

`StatContext.skills` carries the levels, so the drivers stay pure. A character
with no recorded Fitness reads as Fitness 5.

## Exercise

`EXERCISE <type> [minutes]`. Minutes are 10 to 60 in steps of 10, default 10.
The cost is the minutes chosen, or the minutes run when it
[stops early](#stopping-and-refusing).

| Type | Needs | Trains | Metabolic target | XP mod | Rep period |
| --- | --- | --- | --- | --- | --- |
| Squats | — | legs | Fitness | 1 | 3.0 s |
| Push-ups | — | arms, chest | Fitness | 1 | 1.3 s |
| Sit-ups | — | abs | Fitness | 1 | 1.3 s |
| Burpees | — | legs, arms, chest | Fitness heavy | 0.8 | 2.4 s |
| Barbell curls | a barbell | arms, chest | Fitness heavy | 1.2 | 2.2 s |
| Dumbbell press | a dumbbell | arms | Fitness heavy | 1.8 | 1.5 s |
| Biceps curls | a dumbbell | arms | Fitness heavy | 1.8 | 1.9 s |

The parser matches a name ignoring case, hyphens and spaces ("push-ups",
"Push ups"). An unknown exercise, or minutes outside 10 to 60 in steps of 10, is
refused.

### Timing

```
speed = fitness_level / 5 / 1.1 − endurance_status_effect_level / 20
        (at most 1.5; below 0.85 it becomes 1.0)
reps per game minute = 3.75 × speed / period_seconds
```

At Fitness 5 that is about 1.1 squats or 2.6 push-ups per game minute.

The action runs minute by minute. Each minute the survival drivers advance one
minute with the standing-idle endurance branch and the exercise's metabolic
target, then the minute's reps fire. A fractional remainder carries to the next
minute.

### Each rep

1. **Regularity** for this exercise: `+0.08 × ln 5 / ln(fitness_level / 5 + 4)`,
   to at most 100. The exercise is stamped as done at the current time.
2. **Endurance:** `−0.015 × ln(regularity / 50 + 50) / ln 51`, ×1.3 for a heavy
   exercise.
3. **Future stiffness:** for each trained region, add
   `0.5 × (120 − regularity) / 170`, ×1.3 for heavy, ×(1 + Tired level ÷ 3) with
   integer division (×1 at Tired 0–2, ×2 at 3–4), up to 150. The region's
   72-tick timer starts if it isn't running.
4. **XP:** Strength +4 per `arms` and +2 per `chest`; Fitness +4 per `legs` and
   +2 per `abs`; each × the XP mod, then through [Gaining XP](#gaining-xp). The
   high-level bonus is always ×1.

### Stopping and refusing

- **Refused** at the start if the Endurance status effect is above level 2, or the
  exercise needs an item the player isn't carrying. A refusal costs no time.
- **Stops early** once the Endurance status effect goes above level 2. The action then
  costs only the minutes it ran.
- A carried barbell or dumbbell is enough; there is no equip step.

### Regularity and stiffness over time

A tick is one 10-minute boundary.

- Every exercise done at least once, but not in the last 24 game hours, loses
  0.002 regularity per tick, down to 0. An exercise never done keeps its
  starting regularity.
- A region timer that is above 0 drops by 1 per tick. Once it is 0, the
  region's stored stiffness drains: up to 1 unit per tick, each unit adding 2.5
  stiffness to every body part in the region.

| Region | Body parts |
| --- | --- |
| arms | forearms and upper arms |
| legs | upper legs and lower legs |
| chest | upper torso |
| abs | lower torso |

Part stiffness is saved. It has no effect and does not fade until the health
mechanic lands.

**Starting regularity** is drawn once from the world seed, one draw per exercise
in table order, upper bound excluded: Firefighter 10–19, Fitness Instructor
40–59, Security Guard 7–11, everyone else 0.

### Items

The catalog has a Barbell (two-handed, 15 hit points) and a Dumbbell (one hand,
10 hit points). No zone stocks them yet.

### Metabolic rate

While exercising, the metabolic target is Fitness or Fitness heavy, from the
table.

## Retired

- `PlayerEntity.level` and `experience_points`, and `experience_points_gained`
  on quest events. Nothing awarded them, and the character has no overall level.
- `XPMultiplicativeModifier`: XP multipliers are the fixed steps above.

## What the narrator and the player see

- **Facts:** level changes; "You finish 20 minutes of squats." or "You stop, too
  exhausted to go on.", then "N reps in all.".
- **Narrator:** the `[CHARACTER]` block has a `Skills:` line with each skill at
  level 1 or above and a word for its level: 1–2 novice, 3–4 capable, 5–6
  skilled, 7–8 expert, 9–10 master. No XP numbers, no `Level:` line.
- **Parser:** the prompt has an `[EXERCISES]` section with every exercise and
  what is needed, and a `Carrying:` line saying whether a barbell or dumbbell is
  held. The verb list teaches `EXERCISE`.
- **UI:** the `/play` payload drops `level` and `experience_points` and carries
  `skills: [{id, name, category, level, progress}]` for all 35 skills, where
  `progress` is 0–1 toward the next level (1 at level 10). The Character screen
  lists each skill with a level or some progress, grouped by category, with the
  level number and a bar.

## Saves

Schema v11 stores each skill's level and XP, the boosts, both loss timers and
their last step, and the exercise state: regularity, last-done times, stiffness
still to come, region timers and part stiffness. Older saves are discarded.

## Edge cases

- A big XP gain can cross several levels; each is its own fact.
- At the level-10 cap a positive gain is skipped entirely, including the timer
  drop. So Fitness or Strength at 10 slowly loses XP whatever the player does,
  until it falls below the cap.
- Nothing trains while asleep, but the loss timers keep running.
- Negative starting levels are impossible: creation clamps at 0.
