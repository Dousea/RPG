# Weather

> **Status: Implemented.**

The world has a climate: seasons, a day and night temperature swing, drifting
air masses, fronts that bring rain, storms or snow, wind, clouds and fog. It is
fixed by a per-world seed, so a save always has the same weather. This layer
only produces the weather. Status effects and the narrator read it.

## Layout

| Layer | File | What it holds |
| --- | --- | --- |
| modules | `modules/world/simplex.py` | 2D simplex noise |
| modules | `modules/world/weather.py` | `WeatherSample`, `SeasonModel`, `ClimateValues`, `AirFront`, `WeatherPeriod`, `period_seed` |
| modules | `modules/world/location.py` | `Location.indoors`, `World.seed` |
| data | `data/world/climate.py` | configuration, stage templates, word bands, `INDOORS_BY_ZONE` |
| managers | `managers/world/climate.py` | `ClimateEngine`, word and fact helpers |
| managers | `managers/simulation.py` | advances the climate per stat chunk |
| managers | `managers/context.py` | the `[WEATHER]` block |
| adapters | `adapters/save/codec.py` | seed, front and period in the save |
| adapters | `adapters/engine.py` | the `/play` `weather` payload |

## Configuration

| Setting | Value |
| --- | --- |
| Latitude | 38 degrees |
| Warmest / coldest day mean | 25 / 0 °C |
| Daily swing | 7 °C (lowest 8 h before the daily high) |
| Season lag | 31 days after the solstice |
| High noon | 12.5 h |
| Season noise seeds | 64, 128, 255 |
| Monthly rain share, Jan to Dec | 0.39, 0.35, 0.39, 0.40, 0.35, 0.37, 0.29, 0.26, 0.23, 0.23, 0.30, 0.32 |
| Air mass noise frequency | 166 hours per noise unit |
| Rain time multiplier | 1.0 |
| Fog seed | 1984, reseeded each day |
| Fog | 0.2 plus 0.8 times the day's fog strength |

The day mean temperature follows a cosine that peaks 31 days after the June
solstice (late July) and bottoms in late January, plus slow noise, and stays
between 0 and 25 °C. Day length comes from the latitude: about 14.6 hours in
June and 9.4 in December. Dawn and dusk sit half a day length either side of
high noon. Outdoor temperature also moves up to 3 °C with the air mass.

The calendar starts on 1 October 2023 at 08:00. The world's age in hours is
the game minutes divided by 60.

## The world seed

`World.seed` is drawn once when a new game starts and saved. Four noise
offsets A to D are drawn from it, each from 0 to 8000.

A front starts a period with a generator seeded from the date:

```
seed = (year - 1990) * 100000
     + month * day * 1234
     + (year - 1990) * month * 10000
     + (int(B) - int(A)) * day
```

`month` is 0-based and `day` starts at 1. For 1 October 2023 with A = 100 and
B = 300 the seed is 6,281,306. Two fronts on the same date share a seed.

## Components

`WeatherSample` is a frozen record of the outdoor weather: air temperature (°C),
humidity, wind intensity (0 to 1; times 120 gives km/h), wind angle, cloud
intensity, precipitation intensity, whether it is snow, fog intensity,
daylight, the stage name or `None`, and whether it thunders.

`ClimateEngine(seed, start_date, start_minute_of_day)` offers:

- `sample(minutes)`: the weather at any clock moment.
- `advance_to(minutes)`: the front check for every whole hour crossed, in order.
  When the sign of the air mass differs from the last hour's, a new front and
  exactly one `WeatherPeriod` begin. A 16-hour sleep runs 16 checks.
- `start_period(hour, strength)`: begins a period for a front of strength 0 to 1.

Front strength is the air mass slope at the flip, scaled and capped at 1.

A period's length is a random 24 to 56 hours, scaled by that month's rain share
over 0.3. Its stages come from the strength:

| Strength | Stages (share of the period) |
| --- | --- |
| Below 0.34 | drizzle 40%, showers 30%, clearing 30% |
| 0.34 to below 0.67 | showers 20%, moderate 25%, intermezzo 10%, heavy precipitation 25%, clearing 20% |
| 0.67 and above | showers 15%, heavy precipitation 25%, storm 30% (thunder), heavy precipitation 15%, clearing 15% |

If the air is below 0 °C when the period starts, the storm stage is a blizzard
without thunder. A stage sets precipitation (its peak times a 0.8 to 1.0 draw),
a wind floor, a cloud floor and humidity of at least 0.9. Outside a period it
is dry. Fog builds before dawn, peaks at dawn and burns off within three hours.

The simulation core calls `advance_to` for each stat chunk (at most 10 minutes)
and puts the weather at the chunk's midpoint into `StatContext.weather`. It
also sets `StatContext.indoors` from the zone. After death the climate still
advances with the clock.

## Indoors and outdoors

| Zone | Indoors |
| --- | --- |
| `zone_home` | yes |
| `zone_building` | yes |
| `zone_street` | no |
| `zone_neighborhood` | no |
| the two flats, the pharmacy, the clinic, the supermarket and the hardware store | yes |

Indoors, rain and wind do not reach the player. The weather still exists and the
narrator can still hear it.

## What the narrator and the player see

- The `[WEATHER]` block, in both the narrator and parser prompts, lists sky,
  precipitation, temperature, wind, fog (only above 0.2) and whether the player is
  sheltered. It contains words only.
- Precipitation takes its words from the stage: rain showers, heavy rain, a rain
  storm, rain clearing, steady rain, light rain, a blizzard, a tropical storm, a
  lull in the rain. Each stage has a rain phrase and a snow phrase (for example "heavy rain" and "heavy snow"); the snow one is used while the air is below 0 °C. No stage reads "dry".
- Outcome facts: "It starts to rain.", "It starts to snow.", "The rain stops.",
  "The snow stops.", "The rain turns to snow.", "The snow turns to rain.",
  "Thunder rolls overhead.", "The fog lifts.", "Fog rolls in."
- `/play` and `/state` carry `weather: {summary, temperature_c, sheltered}`. The
  temperature is the outdoor reading rounded to a whole degree.

### Word bands

A value gets a band when it is strictly above the band's lower bound.

| Value | Lower bound | Word |
| --- | --- | --- |
| Wind | at or below 0.05 | still |
| | 0.05 | mild |
| | 0.25 | moderate |
| | 0.5 | strong |
| | 0.75 | storm-strength |
| Cloud | 0 | clear skies |
| | 0.4 | some clouds |
| | 0.7 | overcast |
| Fog (mentioned above 0.2) | 0 | light fog |
| | 0.75 | thick fog |
| | exactly 1.0 | very thick fog |
| Temperature (°C) | below -10 | freezing |
| | -10 | bitter cold |
| | 0 | cold |
| | 8 | chilly |
| | 15 | mild |
| | 22 | warm |
| | 29 | hot |

## Saves

Schema v7 saves `world.seed` and a `weather` block with the current front
(side, strength, start hour) and period (start hour and stages). Everything else
is recomputed from the seed and the clock. A save without a period loads with
none. On load the hourly check resumes from the saved clock's hour.

## Edge cases

- A long span runs the front check once per hour boundary, in order, so fronts
  start and end during a sleep as they would awake.
- Fronts can start from hour 1.
- The snow flag is true whenever the air is below 0 °C, precipitating or not; the narrator only says "snow" when something is falling.
- The tropical storm stage has a phrase but no front produces it yet.
