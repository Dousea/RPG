# UI Layout

> **Status: Implemented.** `templates/index.html`, `static/app.js`, `static/style.css`, `static/scene.js`, `adapters/engine.py` `_snapshot`, `adapters/creation_payload.py`. The page, its three layouts, all eight screens and the creation screen exist; fields of mechanics not built yet arrive with those mechanics. See [Implementation Status](../status.md).

The browser page is one HTML template with its script and stylesheet, and it
renders the snapshot the engine returns.
This document says which screen each snapshot field belongs to, how it is
shown, and the rules every screen keeps. Each mechanic says *what* reaches the
player; this document says *where*.

## Rules

**The screens are read-only.** The player acts only by typing. No panel has a
button, toggle or drag that changes game state, and there is no action
endpoint besides `POST /play` and `POST /play/stream`, which runs the same
turn and streams its steps (see `docs/mechanics/llm-contract.md`,
Streaming). The narrator's suggested options are not an
exception: a click fills the input and submits it through `/play`, so the
parser can't tell it from typed text. Three kinds of control are allowed:

- tab switching and other view-only controls;
- the header's file and lifecycle buttons (save to file, load from file,
  reset), which act on the save, not inside the game;
- the creation screen, which runs before a game exists and posts one build.

**The panel obeys the narrator's firewall.** The player sees what the narrator
is told, in the same words: status effect names, wetness words, disposition and trust
bands. A number reaches the screen only when the mechanic that owns the field
allows it. Allowed today: the day, the time of day, the air temperature in °C,
the skill levels on the Character screen, and on the creation screen the
point costs, points left and starting skill levels. Planned: the zombie kill
count (`melee`). Never shown: hit points,
pain, stat values, wetness or temperature of the body, item condition, odds,
affinity or trust scores.

**One field, one home.** Each field is shown on exactly one screen, so two
panels can't disagree. A field that two screens need lives in the header.

**The snapshot is the whole contract.** `/play`, `GET /state`, `POST /reset`,
`POST /save/import` and a successful `POST /creation` all return the same
snapshot from `GameEngine._snapshot`, and `/play/stream` ends with it. The page keeps no game state of its own
except the character's name for the death banner. Before a game exists the
snapshot is `{needs_creation: true}` and the page opens the creation screen.

**Untrusted text goes in as text.** Narrator prose, the player's echoed input,
`current_place`, `death_cause` and NPC names are set with `textContent`, never
`innerHTML`.

## The page

```text
┌ header ─────────────────────────────────────────────────────────┐
│ Title  Day 3  Evening  9 °C  [Outbreak day 2]   Save Load Reset │
├────────────────────────────────────────┬────────────────────────┤
│ Location name                          │ Status Health ...      │
│ place                                  │ ────────────────────── │
│ description                            │ panel                  │
│ scene strip                            │                        │
│ death banner (only after death)        │                        │
│                                        │                        │
│ ▎player input                          │                        │
│ narrator prose                         │                        │
│ ...                                    │                        │
│ [option] [option] [option]             │                        │
│ What do you do?                  [Act] │                        │
└────────────────────────────────────────┴────────────────────────┘
```

| Region | Shows | Fields |
| --- | --- | --- |
| Header chips | when and what the sky is doing | `day`, `time_of_day`, `weather`, `outbreak_day` (`llm-contract`) |
| Scene strip | a picture of where the player stands, the sky, who is with them and what is coming; decorative | `scene`, `time_of_day`, `barriers`, `threats`, `npcs`, `corpses`, `game_over` ([The scene](#the-scene)) |
| Death banner | the character's death and its cause | `game_over`, `death_cause`, `character.name` |
| Story log | each turn's input echo and prose, appended; on load, the last scene's prose with no echo and no options (the options aren't saved) | `story_text` |
| Location | where the player stands | `current_location`, `current_place`, `location_description` |
| Tabs | the screens below | everything else |
| Plan screen | in place of a story when a plan has an open choice: each step in words (done ones ticked), a picker with each candidate's name and description under a step that waits on an answer, a default target beside a step that has one (the steps after a zone change give way to one line saying the rest is worked out on arrival), Go (enabled once every picker has a choice) and Cancel | `plan` ([Which one](entity-resolution.md#which-one)) |
| Input | suggestions, then the free-text input; `@` opens a list of what is in reach, grouped by kind and filtered as the player types, and a pick stays in the text as a chip, one unit that deletes whole | `options`, `mentions` ([Mentions](entity-resolution.md#mentions)) |

The story column holds the scene: where the player stands, what happened and
what they do next, kept to a readable measure. The tabs take the full height
beside it.

A reload or a return to the tab shows the last scene's prose from `/state`
(`memory.last_story`, already in the save), and so does a loaded save file
after its "Save loaded." line, so the story area is never blank in a running
game; a new game shows nothing.

Once `game_over` is set the input and option buttons are disabled; only reset
and load bring the page back.

## The scene

A strip under the location heading and above the story log, the column's full width
and about 180 px tall (120 px on the narrow layout), with the story scrolling beneath
it. It is drawn by `static/scene.js` from the snapshot alone: a fixed set of
hand-made SVG pieces, picked and placed by words. There is no LLM, no image model and
nothing to download.

The strip keeps four rules:

- **Decorative.** The picture is `aria-hidden`; every fact in it is already on a
  screen in words.
- **Drawn from the snapshot only.** The engine chose each fact and sent it as a word.
  The strip can't show what the snapshot doesn't hold, and the narrator's prose never
  reaches it.
- **Words only.** `scene` holds no number. A word the page has no drawing for draws the
  table's default and logs a console warning once. The defaults: afternoon, a clear sky, no
  fog, no falling weather, a steady fall, a person standing with hands in pockets.
- **Local damage comes from state only.** Doors, windows and planks come from
  `barriers`, bodies and their blood from `corpses`, and zombie wounds from the zombie.
  The outbreak stage draws only generic background and never an event the engine owns.

| Layer | Drawn from |
| --- | --- |
| Sky and light | `time_of_day` (a palette for each; indoors the window shows it, and a night room is dim, never black) |
| Cloud, falling weather, fog | `scene.sky`, `scene.falling` and `falling_strength`, `scene.fog` |
| Setting | `scene.setting`: apartment, hallway, street, neighborhood, store or clinic, dressed by `scene.stage` |
| Scenery by stage | `scene.stage` ([Outbreak stages](../mechanics/llm-contract.md#outbreak-stages)): grime and film grain from the panic stage on, and a colour grade that loses colour as the city falls |
| Doors, windows | `barriers`: drawn by `state_word`, planks nailed across, a thumping one shakes. A setting has a few fixed spots, so a thumping barrier takes a spot first, then a broken, smashed or planked one, then the rest, ties broken by the barrier's id. The hallway has four door spots, a store one window or door spot (a door when the worst-off barrier is a door), and the street and the neighborhood put them, shrunk, on their buildings' own doors and windows in the middle of the frame |
| Zombies | `threats`: one figure per visible zombie, its look fixed by its id, size and height by `distance_word`, posture by `state_word`; a heard-only threat draws no figure and closes the strip's edges in with a dark red tint; a zombie behind a barrier draws none |
| People | `npcs`: a plain silhouette fixed by the NPC's `id`, stance by the disposition band; a follower stands larger at the frame's edge |
| Bodies | `corpses`: at most three |
| Game over | `game_over`: the strip turns grey and its motion stops |

Everyone is drawn in one depth order, far zombies first and the one on you last, at
most eight zombies. The strip is a 1000 by 200 view scaled to cover, so a phone shows
about x 200 to 800; whatever carries a fact sits in that band. Motion is slow and
small and stops under `prefers-reduced-motion`.

Two view-only controls sit in the strip's corner: one hides the strip, and one sets
blood to `full` or `reduced` (reduced drops blood smears, the handprint, pools,
running blood, ribs, bone, teeth and gore trails; eyes keep their red). Both choices
are kept in `localStorage` and change the drawing only: no game state, no request, no
narrator change. They are the only state the page keeps for the scene.

## The colour code

Every screen speaks one colour code, the four colours of a triage tag: green
is fine, yellow needs watching, red is urgent, black is grave. A tag's colour
carries severity, so a status effect, a wound flag, a threat or a disposition
never needs a number to say how bad it is. Status effects are yellow below
level 3, red at 3 and black at 4; a positive one is green. Yellow is also the
colour of the player's own hand: the focus ring, the input and its echo in the
log.

## Screens

There are eight screens. On a wide window each is its own tab; narrower
windows merge them into fewer tabs (see [Screen sizes](#screen-sizes)). A
screen whose fields don't exist yet stays hidden until its first field lands.

| Screen | Sections | Fields | Exists |
| --- | --- | --- | --- |
| Status | status effects, conditions, goals | `effects`, `conditions`, `sneaking` (`zombies`), `goals` | yes |
| Health | per body part: wounds, bleeding, bandaged, dirty, infected | `body` (`health` and `injuries`) | yes, without `injuries`'s flags |
| Inventory | held item, equipped slots, carried items, load and bags | `held` (`melee` and `weapon-upkeep`), `equipment`, `inventory`, `carry` (`carrying-and-loot`) | yes |
| Clothing | worn items, outer to inner, by body location | `worn` | yes |
| Character | name, occupation, traits, skills, kills | `character`, `skills` (`skills`), `zombie_kills` (`melee`) | yes |
| People | NPCs here: disposition, trust, following | `npcs` | yes |
| Nearby | threats, corpses, rooms, doors and windows | `threats` (`zombies`), `corpses` (`zombie-lifecycle`), `rooms` (`carrying-and-loot`), `barriers` (`doors`) | yes |
| Quests | active quests and their objectives | `quests` | yes |

### Status

The status effect strip lists active status effects strongest first, by name; level 3 and up
are marked severe by colour, never by a number. Conditions and the narrator's
status effects follow as tags, then goals, short-term before long-term.
`sneaking` is a tag here while it is on.

There is no health bar and no health number.

### Health

One row per body part that has something to show, in head-to-feet order. Each
row lists its wound words (`health` and `injuries`'s kinds) and the flags as words:
bleeding, bandaged, dirty, infected, stitched, splinted. An infected wound stays
"infected" under a bandage, since only disinfectant, an alcohol bandage or
antibiotics bring it down (`health`, Wound infection). No times, no pain
level, no healing progress.

### Inventory

The held item first, with its condition word (sharpness and head words come
with `weapon-upkeep`). Then the equipped slots, empty ones marked empty; an
item that fills both hands is one "Both Hands" row reading "Two-handed grip"
(the payload's `both_hands`), not its name and condition again. Then
carried items by name. The carried weight shows against what the
character can carry, in kilograms, with a gap before the first carried row, and each bag shows its place and contents
(`carry`, see `mechanics/carrying-and-loot.md`).

### Clothing

Worn items outer to inner, each with its body location as words
(`upper body`, not `base:torso`) and its wetness word once it is damp or wetter.

### Character

The name, the occupation (or the job title the player wrote) and the trait
names with their descriptions. Skills: a row per trained skill, grouped by
category, with the level number and a bar for `progress` toward the next level, and the
zombie kill count. The appearance chosen at
creation is not shown: the narrator describes it.

### People

One row per NPC in the zone: name, trust band, and a disposition tag coloured
by tone (friendly and loyal good, wary warning, hostile, terrified and hated
bad). `llm-contract` adds `following` as a tag. `npcs_present` is a plain roster kept
for other callers; the page doesn't read it.

### Nearby

Threats by distance word and state word, closest first; each zombie and body
under the name the `@` list gives it (its looks, numbered `#1`, `#2` where two
look alike), a threat that is only heard as "Something unseen", the body the
player carries as "The body you carry"; corpses by distance
and rot words, with their contents once searched; doors and windows by name
with their state words, plank counts on each side and a thumping tag; rooms
of the building, the one the player is in marked, each with its containers
(not opened, or opened with what they held). A
threat's id is used only to keep rows stable between turns, never shown.

### Quests

Each active quest's title, then its objectives as checked or unchecked rows.

## Screen sizes

The page is responsive like any website: it fits from a phone to a wide
monitor, with no horizontal scrolling and no feature lost at any width. Three
layouts, by window width:

| Layout | Width | Arrangement | Tabs |
| --- | --- | --- | --- |
| Wide | 1200 px and up | story log and sidebar side by side | 8: Status, Health, Inventory, Clothing, Character, People, Nearby, Quests |
| Medium | 861–1199 px | side by side, narrower sidebar | 5: Status (+ Health), Gear (Inventory + Clothing), Character, Around (People + Nearby), Quests |
| Narrow | 860 px and below | one column; the sidebar becomes a sheet over the story | 4: You (Status + Health + Character), Gear, Around, Quests |

How the merging works:

- **Screens are the unit.** A merged tab stacks its screens' sections in the
  order the [Screens](#screens) table gives them, each under its own heading.
  A screen is never split across tabs, so each field still has one home at
  every width.
- **Hidden screens drop out.** A merged tab shows only the screens that have
  fields; a tab with none of them is hidden too.
- **The open tab survives a resize.** When the layout changes, the tab that
  holds the screen the player was looking at opens.

What else changes on a narrow window:

- The header chips wrap onto a second line. Save, load and reset move into
  one menu button.
- The story log fills the screen. The location heading stays above it, and a
  button beside the input opens the sidebar sheet; the sheet closes by the same
  button, Escape, or a swipe down that starts on its handle or tab bar.
- The option buttons scroll sideways in one row above the input, which stays
  pinned to the bottom. The input's placeholder is shorter (still saying `@`
  picks things) so it isn't cut; the input stays one line at every width.
- The creation screen's trait columns stack into one, and its fieldsets
  stack full width.

The layouts are CSS breakpoints plus a small script that re-groups the tab
buttons; the screens' markup is written once.

## The creation screen

Shown instead of the game whenever the snapshot says `needs_creation`. It reads
`GET /creation` once and posts the build to `POST /creation`.

| Section | Contents |
| --- | --- |
| Preset | a picker that fills every field below, which stay editable |
| Who they are | forename, surname, gender, skin tone, hair style and colour, beard (male only), backstory |
| Occupation | the occupation, its free traits and skill boosts; a job-title field for the custom occupation |
| Traits | the points left, live; positive and negative traits in two columns, each with its cost and description; a trait that clashes with a chosen one is disabled |
| Starting skills | each skill above zero with its starting level, recomputed live |
| Starting outfit | one choice per body location from the lists the occupation, traits and gender allow |
| Start | posts the build; refusals come back as `errors` and are listed above the button |

Points and skills are recomputed in the page for feedback only; the server
validates the build again and its answer wins. A refused build starts nothing.

## Adding a field

A mechanic that adds or changes a snapshot field:

1. renders it on the screen the [Screens](#screens) table names for it, or
   adds a row there if the table has none;
2. removes whatever still reads a field it drops;
3. shows words, plus only the numbers its own document allows;
4. lists the field under its screen in the page's `SCREEN_FIELDS`, which is
   what un-hides a screen;
5. updates the table's *Exists* column.

The scene reads `scene` (`stage`, `setting`, `sky`, `falling`, `falling_strength`,
`fog`) and the `id` of each `npcs` entry; both are computed per snapshot and never
saved. A new zone needs a row in `data/world/scenes.py`.

--- | --- |
| Header shows the outbreak stage | now `outbreak_day` (`llm-contract`): "Before the outbreak" or "Outbreak day N" |
| Inventory and equipment show item condition as `n/max` | condition word with `melee` |

## Known limitations

- **A failed Go hides the plan.** The page hides the plan screen before Go's
  request goes out; if the request fails, the kept plan stays hidden until the
  next turn's snapshot brings it back. *Fix:* hide it only once the response
  starts, or show it again on a failed request.
- **A plan candidate sends a field the page never shows.** Each candidate
  in `plan` carries `pinned_as`, which only the engine uses. *Fix:* leave it
  out of the payload, so the plan's fields are the ones the screen renders.

---

[Index](../README.md)
