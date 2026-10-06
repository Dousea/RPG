# Character Creation

> **Status: Implemented.**

Every game starts on a creation screen. The player builds a survivor: a name and
looks, an occupation, then good and bad traits bought with points, then a
starting outfit. **Orton is a preset**, one ready-made build the player can pick
instead.

Earlier mechanics documents say "Orton" in their examples. Read that as "the
player character".

## What we port

| Piece | File |
| --- | --- |
| `Appearance`, `Gender` | `modules/character/appearance.py` |
| `CharacterBuild`, `ResolvedCharacter` | `modules/character/build.py` |
| `TraitDefinition`, `OccupationDefinition` | `modules/character/definitions.py` |
| The 25 occupations | `data/occupations.py` |
| Trait definitions and the trait factors | `data/traits.py` |
| Limits and the skill list | `data/creation.py` |
| Starting-outfit lists | `data/clothing_selection.py` |
| Name lists and appearance word lists | `data/names.py` |
| The Orton preset | `data/presets.py` |
| `validate`, `resolve`, `randomize`, `new_player` | `managers/creation.py` |
| The creation screen's JSON and the build reader | `adapters/creation_payload.py` |
| `GET /creation`, `POST /creation` | `app.py` |

Not built: voice, chest hair and stubble toggles, granted recipes (nothing
uses them until crafting), occupation vehicles, a choice of spawn region (there
is one start, apartment 3B), and the weight traits changing during play.

## Occupations

There are 25 occupations. A positive cost **adds** points to spend; a negative
cost spends them. Boosts are skill levels (see [Starting skills](#starting-skills)).

| Id | Name | Cost | Granted traits | Skill boosts |
| --- | --- | --- | --- | --- |
| `unemployed` | Custom Occupation | +8 | none | none |
| `burgerflipper` | Burger Flipper | +2 | Keen Cook | Cooking 2, Maintenance 1, Short Blade 1 |
| `tailor` | Tailor | +2 | none | Tailoring 4 |
| `doctor` | Doctor | 0 | none | First Aid 6, Short Blade 1 |
| `farmer` | Farmer | 0 | none | Agriculture 4, Animal Care 1, Strength 1 |
| `fireofficer` | Firefighter | 0 | none | Running 1, Strength 1, Fitness 1, Axe 1 |
| `lumberjack` | Lumberjack | 0 | Ax-pert | Axe 2, Strength 1, Maintenance 1 |
| `nurse` | Nurse | 0 | Night Owl | First Aid 3, Lightfooted 1, Fitness 1 |
| `rancher` | Rancher | 0 | none | Animal Care 4, Butchering 3, Fitness 1 |
| `carpenter` | Carpenter | −2 | none | Carpentry 4, Carving 1, Short Blunt 1, Masonry 1, Maintenance 1 |
| `chef` | Chef | −2 | Keen Cook | Cooking 4, Maintenance 1, Short Blade 1, Butchering 2 |
| `constructionworker` | Construction Worker | −2 | none | Short Blunt 2, Long Blunt 1, Masonry 2, Carpentry 1, Maintenance 1 |
| `electrician` | Electrician | −2 | none | Electrical 5 |
| `fisherman` | Fishing Guide | −2 | none | Fishing 3, Foraging 1, Butchering 1 |
| `repairman` | DIY Expert | −2 | Inventive | Carpentry 1, Maintenance 2, Short Blunt 1, Masonry 1 |
| `securityguard` | Security Guard | −2 | Night Owl | Running 2, Lightfooted 1, Short Blunt 1 |
| `engineer` | Engineer | −4 | none | Electrical 1, Carpentry 1, Masonry 1 |
| `mechanics` | Mechanic | −4 | Vehicle Knowledge | Mechanics 4, Welding 1 |
| `metalworker` | Welder | −4 | none | Welding 4 |
| `parkranger` | Park Ranger | −4 | Herbalist | Trapping 1, First Aid 1, Foraging 1, Knapping 1, Carving 1 |
| `policeofficer` | Police Officer | −4 | none | Aiming 4, Reloading 1, Nimble 1 |
| `burglar` | Burglar | −6 | Burglar | Nimble 2, Sneaking 2, Lightfooted 2 |
| `fitnessinstructor` | Fitness Instructor | −6 | Nutritionist | Fitness 3, Running 2, Strength 1 |
| `smither` | Blacksmith | −6 | Blacksmith Knowledge | Blacksmithing 4, Maintenance 1, Short Blunt 1 |
| `veteran` | Veteran | −8 | Desensitized | Aiming 2, Reloading 2 |

Skills are keyed by lowercase names such as `first_aid` and `short_blade`.

**Custom Occupation takes a job title.** The player can type one ("Software
Developer"), up to 40 characters. It is narration only and has no mechanics.

## Traits

`data/traits.py` holds 97 trait definitions: an id, a name, a one-line
description, a cost, a flag for occupation-only traits, skill boosts, and the
traits it excludes. 81 can be picked and 16 only come from an occupation or
from body weight. Ids are lowercase, with underscores instead of spaces and no
prefix.

- **Selectable traits.** A positive cost is a good trait and spends points. A
  negative cost is a bad trait and gives points.
- **Occupation-only traits.** They can't be picked, and cost no points whatever
  value they carry. That includes the five weight traits (Emaciated, Very Low
  Weight, Low Weight, High Weight, Very High Weight), which no occupation
  grants. At creation two of them come from the metabolism traits below.
- **Traits that grant traits.** Only two do:

  | Trait | Cost | Grants | Granted trait's boost |
  | --- | --- | --- | --- |
  | Slow Metabolism | -2 | High Weight | Fitness -1 |
  | Fast Metabolism | -2 | Low Weight | Fitness -1 |

  Picking the trait adds its granted trait at cost 0. The granted trait's
  boosts and exclusions apply, and the player can't remove it by hand.
  Dropping the trait drops the granted one, unless the occupation also
  grants it. Exclusions are checked over the full trait set, so Slow
  Metabolism with Fit or Athletic is refused in either order.
- **Exclusions** work both ways. A trait can't be picked if a chosen or granted
  trait lists it, or if it lists one of them. A trait's own granted traits
  count too.
- Some traits come in two forms with different ids: the pickable one (`cook`,
  `mechanics`, `nutritionist`, `blacksmith`, `herbalist`, `inventive`) and an
  occupation-only twin (`cook2`, `mechanics2`, `nutritionist2`, `blacksmith2`,
  `herbalist_prof`, `inventive_prof`). The two exclude each other.
- `weak` is the trait named Puny (−10, Strength −5); `feeble` is the one named
  Weak (−6, Strength −2).

Good traits: Athletic 10, Strong 10, Handy 8, Hunter 8, Thick Skinned 8, Bushcrafter 8, Blacksmith Knowledge 6, Brawler 6, Fast Healer 6, Fast Learner 6, Fit 6, Keen Hearing 6, Former Scout 6, Stout 6, Gymnast 5, Hiker 5, Target Shooter 5, Adrenaline Junkie 4, Baseball Player 4, Brave 4, Eagle Eyed 4, Angler 4, Graceful 4, Herbalist 4, Tinkerer 4, Inconspicuous 4, Jogger 4, Organized 4, Resilient 4, Sewer 4, Keen Cook 3, Crafty 3, Vehicle Knowledge 3, Wakeful 3, Cat's Eyes 3, Artisan 2, Dextrous 2, Fast Reader 2, First Aider 2, Gardener 2, Inventive 2, Iron Gut 2, Light Eater 2, Low Thirst 2, Mason 2, Nutritionist 2, Outdoorsy 2, Whittler 2, Speed Demon 1.

Bad traits: Sunday Driver −1, All Thumbs −2, Clumsy −2, Cowardly −2, High Thirst −2, Short Sighted −2, Slow Reader −2, Weak Stomach −2, Slow Metabolism −2, Fast Metabolism −2, Slow Healer −3, Smoker −3, Agoraphobic −4, Claustrophobic −4, Conspicuous −4, Hard of Hearing −4, Hearty Appetite −4, Sleepyhead −4, Prone to Illness −4, Asthmatic −5, Fear of Blood −5, Reluctant Fighter −5, Disorganized −6, Weak −6, Restless Sleeper −6, Out of Shape −6, Slow Learner −6, Thin Skinned −8, Illiterate −10, Unfit −10, Puny −10, Deaf −12.

Occupation-only traits: Ax-pert, Blacksmith Knowledge, Burglar, Keen Cook, Desensitized, Emaciated, Herbalist, Inventive, Marksman, Vehicle Knowledge, Night Owl, Nutritionist, Very High Weight, High Weight, Low Weight, Very Low Weight.

Boosts: Strong and Stout raise Strength by 4 and 2; Weak and Puny lower it by 2
and 5. Athletic and Fit raise Fitness by 4 and 2; Unfit and Out of Shape lower
it by 4 and 2. Other boosts are one skill level, or two for Keen Cook (Cooking),
Mason (Masonry), Whittler (Carving), Artisan (Glassmaking and Pottery) and
Blacksmith Knowledge (Blacksmithing).

### Traits with an effect now

A trait takes effect only where the game already has the mechanic.

| Trait | Effect |
| --- | --- |
| Hearty Appetite | hunger gain ×1.5 |
| Light Eater | hunger gain ×0.75 |
| High Thirst | thirst gain ×2 |
| Low Thirst | thirst gain ×0.5 |
| Wakeful | awake fatigue gain ×0.7; sleep needs ×0.75 of the hours |
| Sleepyhead | awake fatigue gain ×1.3; sleep needs ×1.18 of the hours |
| Restless Sleeper | fatigue recovery asleep ×0.5 |
| Night Owl | fatigue recovery asleep ×1.4 |
| Cowardly | panic gain ×2 |
| Brave | panic gain ×0.3 |
| Desensitized | panic gain ×0.15, then panic reset to 0: never panics |
| Prone to Illness | cold catch ×1.7, recovery ×0.5, worsening ×1.2 |
| Resilient | cold catch ×0.45, recovery ×1.5, worsening ×0.8 |
| Outdoorsy | cold catch ×0.25 |

Sleep "hours" factors shorten or lengthen the sleep needed, so the fatigue
recovered per hour of sleep is divided by them. The drivers read the character's
traits from `StatContext.traits`, a set of ids, not from the player.

Every other trait is **recorded but dormant**: it is on the character and the
narrator sees it, but it changes no number until the system it touches exists.

## Point pool

```
points = occupation cost − Σ cost of each chosen trait
```

Granted traits cost nothing. A build is accepted when `points ≥ 0`. Leftover
points are lost.

Custom Occupation (+8) with Strong (10) is −2 and refused. Add Fear of Blood (−5)
and it is +3 and accepted. Veteran (−8) needs 8 points of bad traits before any
good trait.

**Changing occupation** removes the old occupation's granted traits, drops any
chosen trait that a new granted trait excludes (refunding its cost), and adds
the new granted traits. `managers/creation.change_occupation` does this.

## Starting skills

1. Every skill starts at 0, except Fitness 5 and Strength 5.
2. The occupation's boosts and every trait's boosts (chosen and granted) are
   added, including negative ones.
3. Each skill is clamped to 0 to 10. That is its starting level.
4. The skill's **boost** is `min(3, level)`.

A Firefighter with Strong has Strength 5 + 1 + 4 = 10, boost 3. Custom
Occupation with Unfit has Fitness 5 − 4 = 1, boost 1. Custom Occupation with
Slow Metabolism has High Weight, so Fitness 5 − 1 = 4, boost 3, and 8 + 2 = 10
points left.

Levels and boosts are saved on the character. [Skills](08-skills.md) turns each
level into XP and reads the boosts.

## Appearance and identity

| Field | Values |
| --- | --- |
| `forename` | 1 to 20 characters |
| `surname` | 0 to 20 characters |
| `gender` | `female` or `male`; picks the clothing lists and whether beards are offered |
| `skin_tone` | 1 to 5: pale, light, olive, brown, dark brown |
| `hair_style` | short, long, buzz cut, ponytail, curly, bald |
| `hair_colour` | black, brown, blonde, red, grey, white |
| `beard_style` | none, stubble, short beard, full beard, moustache; male only |
| `backstory` | up to 200 characters, optional, narration only |

`data/names.py` holds 30 female forenames, 30 male forenames and 30 surnames for
random characters, each under 20 characters.

**Pronouns** follow `gender`: she/her or he/him. Engine facts and prompts use the
forename and these pronouns.

## Starting outfit

The player picks one item, or none, per body location. The choices are the
`default` list for their gender, plus their occupation's list, plus the list of
each trait they chose. The lists give each item a `chance`, used only when a
character is dressed at random. Every character also starts with the apartment
key.

There is one default list per gender, 21 occupation lists and 8 trait lists
(Gardener, Angler, Hiker, Hunter, Bushcrafter, Vehicle Knowledge, Outdoorsy,
Short Sighted). A list with only a female version serves both genders. Where
lists share a location, the player may pick from the pooled items. A random
dressing rolls the default list, then the occupation list, then each trait list
in order. Each location is rolled against that list's own chance and takes one
of that list's items; a later success replaces an earlier pick. About 130
clothes are in the catalog for these lists, each with its own insulation, wind
and water resistance, weight, scratch and bite defence, condition and coverage.

Occupation lists: burgerflipper, burglar, carpenter, chef, constructionworker, doctor, electrician, engineer, farmer, fireofficer, fisherman, fitnessinstructor, lumberjack, mechanics, metalworker, nurse, parkranger, policeofficer, repairman, securityguard, veteran.

Trait lists: fishing, gardener, hiker, hunter, mechanics, outdoorsman, shortsighted, wildernessknowledge.

A preset's outfit may include items outside the lists (Orton's hoodie), and a
submitted build may use them too.

## Presets

A preset is a complete, legal build. **Orton**:

| Part | Value |
| --- | --- |
| Name | Orton, no surname |
| Gender | male |
| Occupation | Custom Occupation, titled "Software Developer" (+8) |
| Traits | Fear of Blood (−5), Short Sighted (−2), Fast Reader (2), Fast Learner (6) |
| Points left | 8 + 5 + 2 − 2 − 6 = **7** |
| Outfit | T-shirt, hoodie, jeans, ankle socks, trainers |
| Backstory | "Just moved into apartment 3B in Portland." |

`GameManager()` with no player starts as the Orton preset.

## Components

- `CharacterBuild` is a frozen record of the choices: appearance, occupation id,
  job title, chosen trait ids and outfit item ids. It holds no granted traits and
  no derived values.
- `validate(build)` returns plain sentences, empty when the build is legal. It
  checks the occupation id, trait ids (unknown, duplicate, occupation-only),
  exclusions (including with granted traits), points, field lengths, skin tone,
  hair and beard words, beards for male characters only, and that each outfit
  item is allowed and no two share a location.
- `resolve(build)` returns granted traits, the full trait list (granted first),
  skill levels, skill boosts and the points left.
- `randomize(rng)` picks a random occupation, 1 to 5 random good traits and 1 to
  5 random bad ones, then for up to 1,000 rounds removes or adds a trait until
  0 to 3 points are left. It adds a random forename of the character's gender, a
  surname, looks, and an outfit: each list location has its own `chance`, and the lists roll in
  order (default, occupation, then each trait), a later success replacing the
  earlier pick at that location. It retries with
  another occupation if the rounds run out.
- `new_player(build)` returns the `PlayerEntity`: name (forename and surname),
  appearance, occupation, job title, trait ids, skills, boosts, the outfit worn
  and the apartment key carried.

`PlayerAttribute`, `PlayerPerk` and the old trait and perk catalogs are gone.

## Flow and routes

1. With no save, or after `/reset`, the page shows the creation screen.
   `/reset` deletes the save and starts nothing.
2. `GET /creation` returns occupations, traits (good, bad, granted) with
   exclusions, skill names, appearance word lists, outfit lists, every clothing
   item with its location, and the presets with their points left.
3. The page shows the points and skills live. That is a convenience only.
4. `POST /creation` takes a build. A malformed body or a build that fails
   `validate` returns 400 with the messages and starts nothing. A valid build
   starts a new game on day 1 at 08:00, saves it, and returns the first
   snapshot.
5. Picking a preset fills the form; the player can change anything.

`POST /play` and `GET /save/export` return 409 while there is no game.
`GET /state` returns `{"needs_creation": true}`. The server's check is the one
that counts: the browser's point count is never trusted.

## What the narrator and the parser see

- **Narrator.** The `[CHARACTER]` block gives name, pronouns, occupation (or job
  title), appearance in words, backstory, and each trait by name with its
  one-line description. It never shows costs, points or skill numbers.
- **Parser.** Its prompt names the character and pronouns, and says to use them.
- **Engine facts** ("Mara waits 10 minutes.", "Mara keeps her keys on her.") use
  the forename and pronouns.
- **The player.** The `/play` and `/state` payloads gain
  `character: {name, occupation, traits}`; `traits` lists names.

No prompt contains "Orton" unless the character is named Orton.

## Saves

Schema version 10 stores appearance, occupation id, job title, trait ids,
skills and boosts. The build itself isn't kept. A save from another version is
discarded. Unknown trait ids in a save are dropped with a log line.

## Edge cases

- **Occupation swap drops a chosen trait.** Choosing Veteran while Brave is
  chosen removes Brave and refunds its 4 points.
- **Granted and chosen versions of a trait** (Keen Cook) exclude each other, so a
  Chef can't also buy Keen Cook.
- **A trait-granted trait clashes with a chosen one.** Slow Metabolism grants
  High Weight, so Fit and Athletic are refused with it, in either order.
- **Negative points after a swap** are allowed while editing; only submitting
  needs `points ≥ 0`.
- **Unknown ids** in a submitted build fail validation with a message naming the
  id. **Duplicate traits** fail too.
- **The same forename as an NPC** is allowed; the narrator gets the full name.
