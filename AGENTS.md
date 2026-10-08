# Over the River

A text RPG in a zombie apocalypse. A local LLM (LM Studio) parses the player's
intent and narrates; the Python engine owns every rule and every outcome. The
README covers architecture and setup; `docs/status.md` says which
architecture docs are real code and which are design intent.

## Commands

```bash
mise run test       # unittest-parallel -s tests -t . -b  (unittest, not pytest; one module per core)
mise run test-serial  # the same tests in one process
mise run fmt        # ruff format + autofix
mise run lint       # ruff, format check, import-linter layer contracts
mise run typecheck  # basedpyright against .basedpyright/baseline.json
mise run check      # all of the above; run before calling work done
```

`config.yml` may hold a machine-specific `llm.base_url`; don't commit that
change.

## Layers

`modules/` (pure game model) → `data/` (static content) → `managers/` (game
logic) → `adapters/` (LLM, FAISS, saves, turn orchestration) → `app.py` (HTTP
only). A layer imports only from layers to its left. `modules/`, `data/` and
`managers/` never import Flask, requests, FAISS, numpy or YAML, and `modules/`
and `data/` never read `config`. `mise run lint` enforces this; fix the design,
not the contract.

## Mechanics and domains

A game rule's definition is `docs/mechanics/<id>.md`, and its numbers win
over code comments. Code cites a mechanic by its id (`ROT_HOURS = 72  #
zombie-lifecycle`), never by a number. How the system is built is in
`docs/architecture/`; `docs/design/` is intent that is not built. A fact lives
in one doc; the others point to it.

| Domain | Mechanics | Logic |
| --- | --- | --- |
| world | `clock`, `weather`, `doors`, `carrying-and-loot` (rooms) | `managers/world/` |
| body | `survival-stats`, `status-effects`, `body-temperature`, `health` | `managers/body/` |
| clothing | `clothing` | `data/clothing/`, `managers/simulation.py` |
| character | `character-creation`, `skills` | `managers/character/` |
| zombies, corpses | `zombies`, `zombie-lifecycle` | `managers/zombies/`, `managers/corpses/` |
| combat | `melee` | `managers/combat/` |
| loot, carry | `carrying-and-loot` | `managers/world/containers.py`, `managers/carry.py` |
| story | `llm-contract`, `world-lore` | `managers/story/`, `adapters/llm.py` |

`data/zombies/{clothing,outfits,loot}.py` and `data/loot/tables.py` are
generated: change the generator's output, not the file by hand.

## Engine authority

The turn is parse → validate → resolve → narrate (`adapters/engine.py`). The
LLM's output changes state only through `modules.action.parser.parse_action_plan`,
`ActionValidator` and `SimulationCore`, never by reading narrator prose back
into state. Outcome facts handed to the narrator describe events in words and
never contain numbers (HP, damage, odds). See `docs/architecture/engine-authority.md`.

## Code conventions

- **Randomness:** every roll goes through an injected `random.Random`
  (`SimulationCore(..., rng=...)`); never the module-level `random.*`
  functions. Tests pass a seeded `random.Random`. Ruff bans the module
  functions.
- **Time:** game logic runs on the game clock, never the wall clock. Ruff
  bans `time.time`, `datetime.now` and friends outside `adapters/` and
  `app.py`. Every action states its cost in in-game minutes.
- **Constants:** tuning numbers live in `data/` as named constants, with the
  unit in rate names (`_per_min`, `_per_hour`, `_per_day`). Unit conversions
  go through one shared helper module, never inline factors.
- **Comments:** code that reads clearly gets no comment. A comment says *why*
  when the code can't: a non-obvious constraint, a source citation, a
  quirk kept on purpose. Don't write comments that restate the code,
  narrate history or post-mortems ("previously…", "fixed the bug where…",
  "now uses…", "was never invoked"), refer to a past conversation or review,
  or leave commented-out code; that belongs in the commit message. Docstrings
  state what a function guarantees, briefly. When editing a file, delete such
  comments in the code you touch.
- **Blank lines:** a function body reads in paragraphs. Put a blank line
  between its steps: after the guard clauses that return early, between
  gathering what it needs and acting on it, before a loop or a block that
  starts the next step, before the final return when steps come before it.
  Lines that do one thing together stay together; don't space every line.
  Ruff's formatter only sets the blank lines between definitions and never
  adds one inside a body, so this is on the writer. When editing a function
  that stacks its steps, space the code you touch.
- **Modules:** one module, one job. Split a module once it holds two jobs
  that can be read apart (types and their parser, a save format and its file
  I/O, a stat engine and its drivers), and group a family of two or more such
  modules as a package (`managers/body/stats/`, `modules/action/`, `adapters/save/`).
  A package's `__init__.py` holds only a docstring: import from the submodule
  (`from managers.body.stats.engine import StatsEngine`), never re-export. Don't
  split a cohesive module just for its length, don't make a one-module
  package, and don't name a module you'd import bare after a builtin
  (`from adapters.save import format` hides `format()`). A new file goes into
  its domain's package (`world`, `zombies`, `corpses`, `loot`, `body`,
  `clothing`, `character`, `combat`, `story`, `events`, the same names in every
  layer), dropping a prefix the package already says (`data/zombies/outfits.py`,
  not `data/zombie_outfits.py`); only what every domain uses sits at a layer's
  top. Tests split along the same lines, one file per area, in the same
  packages.
- **Imports:** call a function through its module (`from modules import
  units`, then `units.per_hour_from_frame(...)`), so a call says where it comes
  from; import classes and constants by name, or a data module whole. A module
  imported whole has one name in every file: a data module `<name>_k`
  (`from data.character import traits as trait_k`), a zombie data module
  `zombie_<name>` (`lore as zombie_lore`), and a code module whose short name
  is unclear outside its package a name that says its domain
  (`from managers.corpses import bodies as corpses`). `typing`,
  `collections.abc` and `dataclasses` are imported by name. Ruff (ICN003)
  enforces this for the modules listed under `banned-from` in
  `pyproject.toml`; add a module there once it holds plain functions. Source:
  [Google's Python style guide, Imports](https://google.github.io/styleguide/pyguide.html#22-imports).
- **Logging, not print:** each module uses `logger = logging.getLogger(__name__)`.
  `debug` for per-turn traces, `info` for lifecycle, `warning` for dropped or
  repaired data. Ruff bans `print`.
- **Saves:** no save migration: a change to saved state bumps
  `SCHEMA_VERSION` (`adapters/save/codec.py`) and old saves are discarded.
- **Tests:** a test for a mechanic names its id and section in the class
  docstring (`"""arm-injuries: The arm pain divisor."""`) and asserts the
  mechanic's numbers. Tests stay offline: the LLM and the embedding model
  are stubbed (`tests/support.py`). Tests ignore `config.yml`
  (`tests/__init__.py` points `RPG_CONFIG` at `/dev/null`) and fix the world
  seed to 1. `mise run test` runs each test module in its own process, so no
  test may rely on another module's state.
- **Types:** new code type-checks cleanly. Don't add to
  `.basedpyright/baseline.json`; after fixing old errors, shrink it with
  `basedpyright --writebaseline`.
