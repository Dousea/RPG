# Body Temperature, Wetness and Colds

> **Status: Implemented.**

The weather reaches the player's body. Rain soaks through clothing layer by
layer. Cold air and wind pull heat from each body part according to what covers
it. The core temperature drifts toward hypothermia or hyperthermia. Cold, wet
skin leads to catching a cold. A body fighting the temperature burns more
energy, water and sleep.

## What we port

| Piece | File |
| --- | --- |
| Felt air and wind chill | `managers/world/climate.py` |
| Thermal state saved per player | `modules/body/thermal.py` |
| Constants, met table and node table | `data/body/thermal.py`, `data/world/climate.py`, `data/character/traits.py` |
| Heat balance, body multipliers, thermal damage | `managers/body/thermoregulator.py` |
| Wetness driver | `managers/body/wetness.py` |
| Cold driver | `managers/body/cold.py` |
| Status effect rows | `data/body/status_effects.py`, `managers/body/stats/status_effects.py` |

The three drivers join the stat engine's default list after the survival
drivers, in the order wetness, thermoregulator, cold. `StatContext` carries the
floor, the power flag, the metabolic activity, the carried-weight ratio (0
until carrying exists), the player's trait ids and the player itself for them.
The stat engine takes an injected `random.Random` for the cold driver; the
simulation passes its own.

Rates written per frame in the source come in two kinds. The thermoregulator,
the thermal damage tick, the catch counter's fall and the sneeze timer run on
real frames: 112.5 per game minute. The wetness walk, the cold course and the
catch counter's rise run on game frames: 180 per game minute. Conversions go
through `modules/units.py`.

## Air temperature felt

`felt_air_temperature` gives the still air a body feels, and `felt_air` returns
it together with the wind-chill air. `T` is the outdoor temperature.

- **Outdoors:** still air is `T`. Wind-chill air is `min(w, T)` with
  `w = 13.12 + 0.6215·T − 11.37·v^0.16 + 0.3965·T·v^0.16` and `v` the wind in
  km/h. There is no temperature or wind limit. At no wind the formula still
  reads below `T` above about 34.8 °C.
- **Indoors with power:** 22 °C, both airs.
- **Indoors without power, `T` at or below 22 °C:**
  `T + (22 − T) × (0.4 + 0.2 × daylight)`, with the difference times 0.85 on
  floor 1.
- **Indoors without power, `T` above 22 °C**, with `d = T − 22` and
  `m = 0.4 + 0.2 × daylight`: floor 0 is `T − d × 0.85 × m`. Floor 1 is
  `T − d × (m + 0.2 × (1 − daylight))`, with no 0.85.
- **Indoors:** the wind-chill air equals the still air.

The Windchill status effect reads the amount: still air minus wind-chill air outdoors
(0 when that is not positive), 0 indoors. The thermoregulator reads both airs,
thermal damage reads the wind-chill air, drying reads the still air.

`World.power_on` is true at the start and nothing turns it off yet.
`Location.floor` is 1 for the apartment and 0 for the building. Heat sources and
vehicles add nothing. With no weather loaded the felt air is a still 22 °C at
humidity 0.5.

## The thermoregulator

One core temperature (the player's core temperature stat, 37 °C) and one
thermal node per body part, each with a skin temperature, a primary and a
secondary delta. The driver runs the per-frame update in **sub-steps of 10 real
frames** (11.25 per game minute); the last sub-step of a chunk is shorter. Inputs
(air, wetness, activity, reserves) are fixed for a chunk. A relaxation
`x += (target − x) × k` per frame is applied in closed form,
`x = target + (x − target) × (1 − k)^frames`. Against a 1-frame loop over two
hours, the sub-stepped core stays within 0.05 °C and every skin within 0.1 °C.

Each sub-step runs, in order: the core-change cache, the metabolic rate, heat per
node, the core, then the nodes' deltas and skin, the body multipliers and the
thermal damage ticks.

**Inputs.** `energy = 0.6·h + 0.4·f` with `h = 1 − (0.4·hunger + 0.6·hunger²)` and
`f` the same for fatigue. `fluids = 1 − thirst`. Humidity comes from the weather.
Body weight is 80 kg. The Fitness stat is the Fitness level ÷ 5 − 1, from −1 to 1
([skills](skills.md#effects-wired-now)).

### Set point and metabolic rate

The set point is 37 °C, plus 2 per point of the sickness stat (nothing writes
sickness yet).

**Metabolic target.** It starts at the default and every candidate only raises
it. Candidates: the activity, and an exercise term
`clamp01(1 − endurance) × 3.0 × energy`. The target is capped at 10.3, then
multiplied by `1 + w² × 0.35` with `w` the carried-weight ratio (0 for now).

| Metabolic | Met | | Metabolic | Met |
| --- | --- | --- | --- | --- |
| Default | 1.5 | | Walking 2 km/h | 1.9 |
| Light domestic | 1.6 | | Walking 5 km/h | 3.1 |
| Heavy domestic | 2.0 | | Running 10 km/h | 6.9 |
| Default exercise | 3.0 | | Running 15 km/h | 9.5 |
| Using tools | 2.5 | | Fitness | 6.0 |
| Light work | 3.2 | | Fitness heavy | 9.0 |
| Medium work | 3.9 | | Maximum | 10.3 |
| Heavy work | 6.0 | | | |

| Situation | Activity |
| --- | --- |
| waiting, sleeping, any quiet action | default |
| moving between zones | walking 5 km/h |
| attack, unarmed or one-handed blunt | medium work |
| attack, two-handed | heavy work |
| attack, blade (one-handed) or a non-pistol firearm | light work |
| attack, pistol | using tools |

The other rows are in `data/body/thermal.py` for the actions that will use them.

**Metabolic rate** eases toward the target: 0.001 per frame when the target is
higher, 0.0004 when lower. The real rate is `rate × (0.2 + 0.8 × energy × move)`,
where `move` is 1 unless Hypothermia is at least 1. From there it is 0.66, 0.33,
0 at Hypothermia 2, 3, 4, and Hyperthermia 2, 3, 4 overrides it with the same
values. The starting rate is 1.5.

### The node table

| Node | Skin surface | Distance to core |
| --- | --- | --- |
| Torso upper (core) | 0.18 | 0.0 |
| Torso lower | 0.12 | 0.05 |
| Head | 0.08 | 0.05 |
| Neck | 0.02 | 0.02 |
| Groin | 0.06 | 0.3 |
| Upper arm (L, R) | 0.045 | 0.3 |
| Forearm (L, R) | 0.035 | 0.6 |
| Hand (L, R) | 0.01 | 0.8 |
| Upper leg (L, R) | 0.09 | 0.45 |
| Lower leg (L, R) | 0.07 | 0.75 |
| Foot (L, R) | 0.02 | 1.0 |

Skin surface weights each node's heat and its share of the totals and of the
cold delta. Distance to core sets how strongly the node shivers and sweats and
where its skin settles. Every skin starts at 33 °C and every node at 37 °C.

### Clothing per node

For each worn layer covering the part with insulation or wind resistance above 0:

- layer insulation `(2i + 0.5i³) × (1 − 0.75·wet) × (0.5 + 0.5 × condition)`
- layer wind resistance `(w + 0.5w²) × (1 − 0.45·wet) × (0.5 + 0.5 × condition)`

`wet` is the item wetness over 100 and `condition` its hit points over its
maximum. A layer with a hole at the part adds nothing but still counts. A
node's insulation and wind resistance are the sums plus 0.05 per layer. Its
clothing wetness is the layer average. Bare parts have 0 of each.

### Heat per node

With `ss` the skin surface, `I` the insulation, `R` the wind resistance, `bw`
the body wetness over 100, `p` and `s` the node's deltas from the last
sub-step:

1. External air is the still air. If the wind-chill air is colder, it is lowered
   by `(still − chill)/(1 + R)`.
2. `d = external − skin`. Below or at 0 it grows by `1 + 0.75·bw`. Above 0 it is
   divided by `1 + 3·bw`.
3. `heat = d × 0.3 / (1 + I) × ss`.
4. If `p > 0` (cooling): subtract
   `1.5·p·ss/(1+I) × (0.2 + 0.8·fluids) × (0.1 + 0.9·primHeatMod) × humidityMod
   × (1 − 0.2·weightTerm) × (1 + 0.2·fitness)`. Otherwise (shivering) add
   `1.5·|p|·ss × (0.2 + 0.8·energy) × (1 + 0.2·weightTerm) × (1 + 0.2·fitness)`.
5. If `s > 0`: subtract `10.3 × 0.75 × s·ss/(1+I) × (0.1 + 0.9·fluids) ×
   (0.85 + 0.15·humidityMod) × (1 − 0.2·weightTerm) × (1 + 0.2·fitness)`.
   Otherwise add `1.5·|s|·ss × (0.1 + 0.9·energy) × (1 + 0.2·weightTerm) ×
   (1 + 0.2·fitness)`.

`weightTerm = (clamp01((weight/75 − 0.5) × 0.666) − 0.5) × 2` (about −0.245 at 80
kg). `primHeatMod` is 1, except that when the wind-chill air is above set point −
2 it is 0 at still air of set point + 2 or more, else
`1 − (still − (set − 2))/4`. `humidityMod` is 1, minus
`(humidity − 0.5) × 2` above humidity 0.5.

Total heat is the sum plus the real metabolic rate.

### The core

Per frame, `delta = total heat × 0.00025`. Cooling above the set point is scaled
by `1 + (core − set)/2`, and heating below it by `1 + (set − core)/4`. A delta of
more than 0.001 moves the core by half of itself. The core clamps to 20 to 42 °C
and the reported core stat to 20 to 40 °C, so Hyperthermia 3 and 4 cannot be
reached.

The body heat delta is `core − set`. Below the set point a gap of 1 or less is
times 0.8, and a larger gap is `−0.8 − 0.2 × (min(gap, 11) − 1)/10`. It clamps to
−1 to 1.

### The skin

Per node: primary is `b × (1 + dist)` when `b < 0` and `b × (1 + (1 − dist))`
otherwise, clamped to −1 to 1. Secondary is `p × |p| × |p|`. The totals are the
sums weighted by skin surface.

- **Skin range.** The maximum is the core. The minimum starts at core − 20. If
  that is below the still air: in air under 33 °C it is the air; otherwise it is
  `33 + 4 × ((air − 33)/6) × (0.4 + 0.6·(1 − dist))` clamped to 33 up to the
  air, and one quarter degree under the maximum if it exceeds it.
- **Target.** Base is core − 4. For `p < 0` the target moves from the base
  toward `base − 12·(0.4 + 0.6·dist)/(1 + I)` by `|p|`. Otherwise it moves toward
  `min(base + 4·dc × max((1 + I) × 0.5 × dc, 1), core)` by `p`, with
  `dc = 0.4 + 0.6·(1 − dist)`. The result clamps to the range.
- **Rate.** 0.0025 per frame, three times faster when the skin moves toward 33 °C
  from the far side. A node's temperature is the core if its skin is at or above
  the core, else halfway between.

A body in shirt and jeans in still 22 °C air settles with a core of 36.7 to
37.0 °C and holds it. Naked at 22 °C it settles at 36.5 to 36.8 °C. Naked at 0 °C
with wind, the core falls and reaches Hypothermia 1 before level 2.

### Body multipliers

With `p` the primary total and `s` the secondary total, each multiplier starts at 1.

| Multiplier | Shivering side (< 0) | Sweating side (> 0) |
| --- | --- | --- |
| energy (hunger) | `+0.05·p²`, `+0.1·s²` | none |
| fluids (thirst) | none | `+0.25·p²`, `+3.75·s²` |
| fatigue | `+0.25·p²`, `+0.75·s²` | `+0.25·p²`, `+1.75·s²` |

The thermal state stores them. The stat engine puts them into the next chunk's
context, and the hunger, thirst and fatigue drivers multiply by them. A caller
that passes its own multipliers keeps them.

### Thermal damage

A tick runs every 2 real frames (56.25 per game minute). The core-change cache
is the core sampled every 7 sub-steps.

- **Cold:** Hypothermia 4, wind-chill air below 0, and the core not above the
  cache. `frost = 1 − (core − 20)/5`, `seconds = 120 + 480 × frost`, the stage
  rises by `clamp01(|air|/10)/seconds`, is multiplied by 1.2, the duration grows
  by 1.07 and the stage caps at `duration/7200`. The stage reaches 1 after
  about 2 game hours.
- **Hot:** Hyperthermia 4, wind-chill air above 37 and the core not below the
  cache. The stage caps at 0.3. It cannot happen while the core stat caps at 40.
- **Otherwise:** the stage falls 0.011111 per tick (37.5 per game hour) and the
  duration resets.

`health_cap(stage)` is `100 − 100 × stage`. The
[body minute](health.md#the-body-minute) caps health at it, and a
stage of 1 kills.

## Wetness

The walk runs once per game minute. Per-frame amounts are ×180: rain adds
`2.7 × intensity` and drying removes `1.8 × rate` per minute. Thresholds are read
from the state at the start of the minute and results clamp to 0 to 100.

**Source.** Outdoors while it rains, the wetting rate is the rain intensity (0
below 0.1). Snow does not wet. A player indoors is not rained on. Otherwise the
drying rate is `0.1 + (T − 5)/10` for still air `T` above 5 °C, else 0.1.

### The layer walk

Each part has its layers; the walk uses the start-of-minute skin wetness (the
body wetness), which equals the Wetness stat.

**Pass 1: sweat and evaporation.**

1. `perspiration = clamp01(secondary)² × (0.2 + 0.8 × (1 − dist))`.
2. Above 0.1 the skin wets by it. Otherwise, unless it is raining, the skin dries
   by `((skin °C − 20)/22)²` less the rain intensity (never below 0).
3. The amount is ×2.7 if wetting and ×1.8 if drying, and added to the skin.
4. Clothing is touched only if the skin is at least 25 after a wetting, or at
   most 50 after a drying.
5. The delta passes inward from the innermost layer. A wetting is first scaled by
   `0.4 + 0.6 × clamp(air + 10, 0, 20)/20`. Layers with a hole, saturated layers
   (wetting) and dry layers (drying) are skipped, halving the delta. The first
   other layer takes it, times `1 − water_resistance` for sweat. A resistance of
   1 stops it.
6. The part counts perspiring parts: 1 if wetting, plus 1 per layer visited,
   minus 1 if it stopped at a waterproof layer.

**Pass 2: rain and air.** From the outermost layer inward, with a divider of 2:

- holed, saturated (rain) and dry (drying) layers are skipped and flag the walk
- in rain, a layer's resistance scales the delta, and a resistance of 1 stops the walk
- the layer's delta is the amount over the number of parts the item covers, divided
  by the divider if any layer was skipped
- in rain, the first layer to take the delta ends the walk. In drying, layers
  inside the first `perspiring − 1` from the inside also take it, and the divider
  doubles after each layer that takes

Then the skin. With clothes, if nothing sweats and the innermost layer is at 50
or more (rain, skin at most 100) or at most 50 (drying), the skin takes half the
amount. With none, the skin takes all of it.

### The body merge

Body wetness moves by `0.9 ×` the mean change of the parts over the minute. Every
part then equals the body wetness. Item wetness is kept per clothing item.

## Colds

**Catching.** The delta is summed per node. If skin is below 33 °C,
`x = (1 − (skin − 20)/13)²` and the node adds `0.25 × x × skin surface`. Body
wetness multiplies it by `1 + wetness`; clothing wetter than 0.5 multiplies it by
`1 + (wetness − 0.5) × 2`. Neck counts 8 times, upper torso 16, head 4, every
other node once. The delta is multiplied by the Hypothermia level when it is
above 1.

- With no cold and a delta above 0.1, the trait multiplier scales the delta and
  the counter rises `0.54 × delta` per minute.
- At or below 0.1 (before traits), the counter falls 19.6875 per minute, never
  below 0, even during a cold.
- At 100 the counter resets and a cold starts at strength 20 with the sneeze
  timer 0.
- Traits scale the rise: Prone to Illness 1.7, Resilient 0.45, Outdoorsy 0.25.
  Their ids are `pronetoillness`, `resilient` and `outdoorsman`; the character's
  traits come from [character creation](character-creation.md).

**Course.** Cold strength (0 to 100) recovers 2.016 per minute while the player
is indoors, not Wet, not Hypothermic, with fatigue at most 0.5 and hunger and
thirst at most 0.25. Otherwise it worsens at the same rate up to 100. While cold
reduction is above 0 it counts as recovering and strength falls twice as fast;
cold reduction falls 0.9 per minute. Recovery is ×0.5 for Prone to Illness and
×1.5 for Resilient; worsening ×1.2 and ×0.8. The cold is over when strength goes
below 0, and the counter resets.

A cold never touches the sickness stat or the Sick status effect.

### Sneezes and coughs

One timer, in real frames. It stays put below Has a Cold level 2. From level 2
(strength above 40) it drops 112.5 per game minute. When it reaches 0 it triggers
once: level 2 always sneezes, levels 3 and 4 sneeze when a roll of 100 comes
above 50 (49 in 100) and otherwise cough. The timer resets to a draw in 600 to
800 frames (level 2), 300 to 600 (level 3) or 200 to 300 (level 4), less the
frames left in that minute. The narrator gets "<name> sneezes." or "<name>
coughs." A sneeze would make a noise of radius 20 and volume 25, a cough radius
35 and volume 40; nothing hears them yet. Rolls use the injected random source.

## Status effects added to 03

| Status effect | Driven by | L1 | L2 | L3 | L4 | Names |
| --- | --- | --- | --- | --- | --- | --- |
| Wet | wetness | 15 | 40 | 70 | 90 | Damp, Wet, Soaked, Drenched |
| Has a Cold | cold strength (above) | 20 | 40 | 60 | 75 | Sniffly, Has a Cold, Heavy Cold, Bad Cold |
| Hypothermia | core °C (below) | 36.5 | 35 | 30 | 25 | Chilled, Cold, Freezing, Hypothermia |
| Hyperthermia | core °C (above) | 37.5 | 39 | 40 | 41 | Warm, Hot, Overheated, Hyperthermia |
| Windchill | wind-chill amount (above) | 5 | 10 | 15 | 20 | Breezy, Wind Chill, Biting Wind, Freezing Wind |

Hypothermia levels 1 and 2 are hidden while intoxication is above 30 and 70
respectively. Hyperthermia 3 and 4 cannot be reached because the core stat caps
at 40 °C.

## What the narrator and the player see

The new status effects join the `[CONDITION]` block and the `/play` status effect strip, by
name and level. Core temperature, wetness and cold strength are never shown.
The `Wearing:` line already marks wet items.

## Saves

Schema version 9. The player holds a `thermal` object: skin, node temperature,
primary and secondary per body part, metabolic rate, the two totals, the three
multipliers, the core-change cache and its counter, the catch counter, cold
reduction, the sneeze timer and its active counter, the thermal damage stage and
duration, and the leftover tick frames. The core temperature, body wetness, cold
strength and wind-chill amount are saved with the stats. The world holds
`power_on`. No migration.

## Edge cases

- Entering shelter changes the felt air at the next sub-step; the body then eases
  toward it, so warming up takes time.
- Sleeping outdoors in the rain keeps soaking and chilling the player.
- Taking off a wet layer drops it from the model at once; the item keeps its wetness.
- With no weather loaded, every driver runs in still, dry 22 °C air.
- A long wait runs one sub-step per 10 real frames, so a day is about 16,000
  sub-steps.
