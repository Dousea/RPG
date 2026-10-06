# Status Effects and Consumption

> **Status: Implemented.**

A status effect is a named condition with four levels. One stat crossing fixed
thresholds drives it. Status effects are what the narrator describes and what the
player sees. Raw stat numbers never leave the engine. Eating and drinking are
the main way the player moves stats back down.

## Layout

| Layer | File | What it holds |
| --- | --- | --- |
| modules | `modules/stats.py` | `StatusEffect` |
| modules | `modules/item.py` | the food fields on `ConsumableItem` |
| modules | `modules/entity/player.py` | `PlayerEntity.food_eaten_timer` |
| data | `data/status_effects.py` | `STATUS_EFFECT_THRESHOLDS`, level names, well-fed, alcohol and penalty constants |
| data | `data/items.py` | the shipped food and drink |
| managers | `managers/stats.py` | `status_effect_level`, `active_status_effects`, the penalty functions, the timer drain |
| managers | `managers/simulation.py` | consuming an item |
| managers | `managers/context.py` | the `[CONDITION]` block |
| adapters | `adapters/engine.py` | the `/play` `effects` payload |

## Status effects

A value strictly above a column gives that level. A value at or below the first
column is level 0. Endurance is inverted: a value at or below a column gives
the level.

| Status effect | Stat | L1 | L2 | L3 | L4 | Level names |
| --- | --- | --- | --- | --- | --- | --- |
| Hungry | hunger | 0.15 | 0.25 | 0.45 | 0.70 | Peckish, Hungry, Very Hungry, Starving |
| Thirst | thirst | 0.12 | 0.25 | 0.70 | 0.84 | Slightly Thirsty, Thirsty, Parched, Dying of Thirst |
| Tired | fatigue | 0.60 | 0.70 | 0.80 | 0.90 | Drowsy, Tired, Very Tired, Ridiculously Tired |
| Endurance | endurance (at or below) | 0.75 | 0.50 | 0.25 | 0.10 | Moderate Exertion, High Exertion, Excessive Exertion, Exhausted |
| Stress | stress | 0.25 | 0.50 | 0.75 | 0.90 | Anxious, Agitated, Stressed, Nervous Wreck |
| Panic | panic | 6 | 30 | 65 | 80 | Slight Panic, Panic, Strong Panic, Extreme Panic |
| Bored | boredom | 25 | 50 | 75 | 90 | Bit Bored, Bored, Very Bored, Extremely Bored |
| Unhappy | unhappiness | 20 | 45 | 60 | 80 | Sad, Very Sad, Depressed, Severely Depressed |
| Pain | pain | 10 | 20 | 50 | 75 | Minor Pain, Pain, Severe Pain, Agony |
| Drunk | intoxication | 10 | 30 | 50 | 70 | Tipsy, Drunk, Very Drunk, Hammered |
| Sick | max(food sickness, infection) ÷ 100 + sickness | 0.25 | 0.50 | 0.75 | 0.90 | Queasy, Nauseous, Sick, Fever |
| Food Eaten | well-fed timer | above 0 | above 1600 | above 3200 | above 4800 | Well Fed at every level |
| Injured | 100 − HP | 20 | 40 | 60 | 75 | A Little Hurt, Injured, Severe Injuries, Critical Injuries |
| Bleeding | bleeding body parts, capped at 4; 4 if the neck bleeds | 1 | 2 | 3 | 4 | Minor Bleeding, Bleeding, Severe Bleeding, Massive Blood Loss |

- Injured is off at 0 HP.
- Bleeding is level 0 until the health spec supplies bleeding parts.
  `bleeding_level(parts, neck)` already applies the cap.
- The "Well Fed" name is shared by all four Food Eaten levels for now.
- Wet, Hypothermia, Hyperthermia, Has a Cold and Windchill join this table with
  the weather and body-temperature specs.

`status_effect_level(status_effect, value)` returns 0 to 4. `StatsEngine` compares every
status effect's level before and after each chunk and reports one fact per change, in
table order ("Orton is now Peckish.", "Orton is no longer Peckish.").

## What status effects do

| Effect | Rule |
| --- | --- |
| Melee damage | Panic at level 2 or more subtracts 0.1 per level. Stress at level 2 or more subtracts 0.1 per level. The hit is floored at 0.1. |
| Fatigue gain | Endurance feeds fatigue. |
| Unhappiness gain | Bored and Stress levels feed unhappiness. |
| HP loss | Starving, Dying of Thirst and Fever cost HP over time. |
| Sleep | `SLEEP` is refused at Panic level 1 or more, and at Pain level 2 or more unless fatigue is above 0.85. |
| Crit chance | 5 per Endurance level, 5 per Heavy Load level and 1.3 per Panic level are lost. |
| Defence | 2 per Endurance level, 3 per Tired level and 2 per Drunk level are lost. |

`melee_status_effect_penalty`, `damage_after_status_effects`, `crit_penalty` and
`defence_penalty` in `managers/stats.py` compute these. The melee, zombie and
health specs call them. Heavy Load is 0 until the carrying spec.

## Eating and drinking

`USE_ITEM` on a consumable consumes the whole item in one step. Partial
portions are not modelled.

### Item fields

| Field | Unit | Meaning |
| --- | --- | --- |
| `hunger_change` | hunger (0-1 scale) | added to hunger; negative feeds |
| `thirst_change` | thirst (0-1 scale) | added to thirst; negative quenches |
| `unhappy_change` | points | added to unhappiness |
| `boredom_change` | points | added to boredom |
| `stress_change` | stress (0-1 scale) | added to stress |
| `alcoholic` | bool | adds intoxication |
| `low_alcohol` | bool | weak drink, quarter strength |
| `cooked` | bool | doubles the well-fed gain |
| `eat_minutes` | minutes | time cost, default 5 |

Shipped items:

| Item | hunger_change | thirst_change |
| --- | --- | --- |
| Canned Beans | −0.35 | −0.05 |
| Water Bottle | 0 | −0.45 |
| Granola Bar | −0.20 | +0.05 |
| Instant Noodles | −0.40 | +0.10 |

None is alcoholic or cooked. Eating takes 5 minutes each.

### Consuming

Each field applies once. Every stat clamps to its range, so a positive
`unhappy_change` or `boredom_change` raises the stat and clamping keeps it in
range.

- **No instant healing.** Food does not restore HP. The canned beans have no
  HP modifier.
- **Well-fed timer** (`player.food_eaten_timer`): gains
  `|hunger_change| × 13000`, doubled if cooked, capped at 11000. It drains at
  10800 per game hour while time passes, including while eating. It drives the
  Food Eaten status effect and switches the hunger driver to its well-fed branch. An
  apple (−0.16) adds 2080. Eating while well fed stacks up to the cap.
- **Alcohol:** intoxication rises by `400 × portion`. The portion is 2 for a
  whole item with a hunger change and 1 for one without. A `low_alcohol` item
  counts a quarter. It counts ×1.25 if hunger is above 0.8, otherwise ×1.1 if
  hunger is above 0.6 (hunger as it was before the meal). A whole item at hunger
  above 0.8 adds 1000 and one with no hunger change adds 500, before intoxication
  clamps at 100.
- **Time:** the action costs the item's `eat_minutes`.
- **Water** is a drink with a `thirst_change` only.

## What the narrator and the player see

- **Narrator:** the prompt has a `[CONDITION]` block listing every status effect at
  level 1 or above by name and level, for example "Very Hungry (3/4), Drowsy
  (1/4)", or "Fine". It never holds a raw stat value. `[OUTCOMES]` carries this
  turn's level changes, including the ones a meal causes ("Orton is no longer
  Very Hungry."). The narrator describes them and cannot change them.
- **Parser:** the parser prompt has the same `[CONDITION]` block, so it can
  propose `SLEEP`, eating or `WAIT` in character.
- **UI:** `/play` and `/state` carry `effects: [{type, level, name}]`, highest
  level first. `hunger` and `thirst` are not sent. The page shows each as a tag.

## Edge cases

- Levels use `>` against the clamped value (`<=` for Endurance): hunger of
  exactly 0.15 is level 0, endurance of exactly 0.75 is level 1.
- Several status effects changing in one chunk each give their own fact, in table
  order.
- A chunk reads the well-fed level at its start, so the hunger driver treats the
  last chunk before the timer runs out as well fed.

## Saves

`SCHEMA_VERSION` is 6. The player saves `food_eaten_timer`. Older saves are
discarded.

## Testing

- `tests/test_stats.py`: every threshold just below, at and just above, the
  inverted Endurance column, the Food Eaten timer, Injured, Bleeding, and the
  penalty functions.
- `tests/test_stats_engine.py`: one fact per crossing, none without one; the
  timer drain.
- `tests/test_simulation.py`: item fields, the timer (apple, cooked, cap),
  alcohol, eat time, no instant healing.
- `tests/test_context.py`, `tests/test_routes.py`: the `[CONDITION]` block and
  the `effects` payload.
- `tests/test_persistence.py`: the timer round-trips; a v5 save is discarded.
