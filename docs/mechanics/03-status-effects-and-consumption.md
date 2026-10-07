# Status Effects and Consumption

> **Status: Implemented.**

A status effect is a named condition with four levels. One stat crossing fixed
thresholds drives it. Status effects are what the narrator describes and what the
player sees. Raw stat numbers never leave the engine. Eating and drinking are
the main way the player moves stats back down.

## Layout

| Layer | File | What it holds |
| --- | --- | --- |
| modules | `modules/body/stats.py` | `StatusEffect` |
| modules | `modules/item.py` | the food fields on `ConsumableItem` |
| modules | `modules/entity/player.py` | `PlayerEntity.food_eaten_timer` |
| data | `data/body/status_effects.py` | `STATUS_EFFECT_THRESHOLDS`, level names, well-fed, alcohol and penalty constants |
| data | `data/items.py` | the shipped food and drink |
| managers | `managers/body/stats/status_effects.py` | `status_effect_level`, `active_status_effects`, the penalty functions, `alcohol_intoxication` |
| managers | `managers/body/stats/engine.py` | the timer drain |
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
| Sick | max(food sickness, zombie infection, general wound infection) ÷ 100 + sickness | 0.25 | 0.50 | 0.75 | 0.90 | Queasy, Nauseous, Sick, Fever |
| Food Eaten | well-fed timer | above 0 | above 1600 | above 3200 | above 4800 | Well Fed at every level |
| Injured | 100 − health | 20 | 40 | 60 | 75 | A Little Hurt, Injured, Severe Injuries, Critical Injuries |
| Bleeding | bleeding body parts, capped at 4; 4 if the neck bleeds | 1 | 2 | 3 | 4 | Minor Bleeding, Bleeding, Severe Bleeding, Massive Blood Loss |

- Injured is off at 0 health, and reads the health the body parts give
  ([health](12-health-and-infection.md#overall-health)).
- Bleeding counts the bleeding parts ([health](12-health-and-infection.md#bleeding));
  `bleeding_level(parts, neck)` applies the cap.
- The "Well Fed" name is shared by all four Food Eaten levels for now.
- Wet, Hypothermia, Hyperthermia, Has a Cold and Windchill join this table with
  the weather and body-temperature specs.

`status_effect_level(status_effect, value)` returns 0 to 4. `StatsEngine` compares every
status effect's level before and after each chunk and reports one fact per change, in
table order ("Orton is now Peckish.", "Orton is no longer Peckish."). A change between
two levels with the same name gives no fact. Over one span of time (a wait, a sleep, a
walk) the facts are netted: each status effect is reported once, at the level it ended
on, so a long wait says "Orton is now Extremely Bored." and not every step up to it.

## What status effects do

| Effect | Rule |
| --- | --- |
| Melee damage | Panic at level 2 or more subtracts 0.1 per level. Stress at level 2 or more subtracts 0.1 per level. The hit is floored at 0.1. |
| Fatigue gain | Endurance feeds fatigue. |
| Unhappiness gain | Bored and Stress levels feed unhappiness. |
| HP loss | Starving, Dying of Thirst and Fever cost health over time, and Massive Blood Loss costs more ([health](12-health-and-infection.md#the-body-minute)). |
| Sleep | `SLEEP` is refused at Panic level 1 or more, and at Pain level 2 or more unless fatigue is above 0.85. |
| Crit chance | 5 per Endurance level, 5 per Heavy Load level and 1.3 per Panic level are lost. |
| Defence | 2 per Endurance level, 3 per Tired level and 2 per Drunk level are lost. |

`melee_status_effect_penalty`, `damage_after_status_effects`, `crit_penalty` and
`defence_penalty` in `managers/body/stats/status_effects.py` compute these. The melee spec calls
`melee_status_effect_penalty` (through `damage_after_status_effects`) and `crit_penalty`; the
zombie and health specs call the rest. Heavy Load is 0 until the carrying spec.

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
| `alcohol` | float | alcohol strength of the drink times its litres; 0 for none |
| `cooked` | bool | doubles the well-fed gain |
| `eat_minutes` | minutes | time cost, default 5 |

### Item values

| Item | hunger_change | thirst_change | unhappy_change |
| --- | --- | --- | --- |
| Canned Beans | −0.24 | 0 | +10 |
| Water Bottle (a litre) | 0 | −0.50 | 0 |
| Granola Bar | −0.15 | 0 | 0 |
| Instant Noodles | −0.10 | +0.40 | +20 |

The noodles make the player thirstier. None has alcohol or is cooked. Eating takes 5 minutes each.

### Consuming

Each field applies once. Every stat clamps to its range, so a positive
`unhappy_change` or `boredom_change` raises the stat and clamping keeps it in
range.

- **No instant healing.** Food does not restore HP. The canned beans have no
  HP modifier, and no item heals directly; health comes back only through the
  [body](12-health-and-infection.md#healing).
- **Well-fed timer** (`player.food_eaten_timer`):
  - Food: only when hunger is 0 after the item's hunger change, it gains
    `|hunger_change| × 13000`, doubled if cooked, capped at 11000. Eating while
    still hungry adds nothing. Beans eaten at hunger 0.2 add 3120.
  - Drinks (items tagged `drink`): add `|hunger_change| × 13000` every time,
    with no hunger test and no cap.
  - It drains at 10800 per game hour while time passes, including while eating.
    It drives the Food Eaten status effect and switches the hunger driver to
    its well-fed branch.
- **Alcohol:** see [Alcohol](#alcohol).
- **Time:** the action costs the item's `eat_minutes`.
- **Water** is a drink with a `thirst_change` only.

### Alcohol

Intoxication rises by `400 × alcohol × m`, clamped to 100. Hunger is read after the drink's own hunger change. `m` is 1.1 if hunger is above 0.8, otherwise 1.25 if hunger is above 0.6, otherwise 1. A drink with `alcohol` 0.015 and hunger −0.03 adds 6.0 at hunger 0.5 after the drink, 7.5 at 0.7 and 6.6 at 0.9. No shipped item has alcohol.

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

`SCHEMA_VERSION` is 18. The player saves `food_eaten_timer`. Older saves are
discarded.

## Testing

- `tests/body/test_stats.py`: every threshold just below, at and just above, the
  inverted Endurance column, the Food Eaten timer, Injured, Bleeding, and the
  penalty functions.
- `tests/body/test_stats_engine.py`: one fact per crossing, none without one; the
  timer drain.
- `tests/body/test_consumption.py`: item fields, the timer (apple, cooked, cap),
  alcohol, eat time, no instant healing.
- `tests/test_context.py`, `tests/test_routes.py`: the `[CONDITION]` block and
  the `effects` payload.
- `tests/test_persistence.py`: the timer round-trips; a v5 save is discarded.
