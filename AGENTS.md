# Local LLM RPG

A text RPG in a zombie apocalypse. A local LLM (LM Studio) parses the player's
intent and narrates; the Python engine owns every rule and every outcome. The
README covers architecture and setup; `docs/00-status.md` says which
architecture docs are real code and which are design intent.

## Commands

```bash
mise run test       # python -m unittest discover -s tests -t . -b  (unittest, not pytest)
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

## Engine authority

The turn is parse → validate → resolve → narrate (`adapters/engine.py`). The
LLM's output changes state only through `modules.action.parse_action_plan`,
`ActionValidator` and `SimulationCore`, never by reading narrator prose back
into state. Outcome facts handed to the narrator describe events in words and
never contain numbers (HP, damage, odds). See `docs/01-engine-authority.md`.

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
- **Logging, not print:** each module uses `logger = logging.getLogger(__name__)`.
  `debug` for per-turn traces, `info` for lifecycle, `warning` for dropped or
  repaired data. Ruff bans `print`.
- **Saves:** while the game is not playable (until spec 12 lands), there is
  no save migration: bump the schema version and discard incompatible saves.
- **Tests:** a test for a spec'd mechanic names the spec and section in its
  class docstring (`"""Spec 16, The arm pain divisor."""`) and asserts the
  spec's numbers. Tests stay offline: the LLM and the embedding model
  are stubbed (`tests/support.py`).
- **Types:** new code type-checks cleanly. Don't add to
  `.basedpyright/baseline.json`; after fixing old errors, shrink it with
  `basedpyright --writebaseline`.
