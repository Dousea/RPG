# Runtime, Configuration, and Persistence

> **Status: Implemented.** `config.py`, `adapters/persistence.py`, `adapters/engine.py`, `app.py`. See [Implementation Status](00-status.md).

[Document 16](16-determinism-and-versioning.md) says to version anything that
affects a persistent world. [Document 12](12-data-model.md) says to persist
mutations rather than regenerated data. Neither says what to do when a save no
longer matches the code, what happens when two turns overlap, or where tuning
values live. This document records those operational answers.

## Concurrency

Not addressed anywhere in documents 01–21, and unavoidable in practice: Flask's
development server is threaded, so two overlapping `POST /play` requests would
interleave mutations of the same `GameManager` and race on the save file.

**One lock covers the whole turn.** `GameEngine` holds a `threading.Lock`, and
`play`, `reset` and `state` each take it for their entire body. Turns are
therefore strictly serialized: recall, prompt, LLM call, action application,
reindex, summarize and save all happen with no other turn in flight.

The lock is held across the LLM call, which can take minutes. That is
deliberate — a second player action mid-turn has no coherent meaning when the
first turn's state changes have not landed — but it means the server handles
exactly one turn at a time. A multi-session deployment would need a manager per
session rather than a finer-grained lock.

`GameEngine` is built lazily by `app.get_engine()` rather than at import, so
loading a save and warming the embedding model do not run during
`flask --app app` startup or when a tool merely imports the module. Running
`app.py` directly builds it up front instead, so the cost is paid before the
first request rather than during it.

## Configuration

`config.py` loads `config.yml` once at import and exposes it as nested,
attribute-accessible sections: `config.llm.base_url`,
`config.memory.default_recall`, `config.game.max_recent_events`,
`config.persistence.save_file_name`, `config.server.port`.

Every value has a hardcoded fallback in `_DEFAULTS`, deep-merged under the
file's contents. A missing `config.yml`, an unreadable one, or a missing key
degrades to the built-in default with a log line — it never crashes. The
defaults are the values that were previously hardcoded across `adapters/` and
`managers/`, so behaviour with no config file is identical to before the file
existed.

Config is read at **import time**, not per use. Changing `config.yml` requires a
restart.

## What is persisted

Only *dynamic* state. Static definitions — item stats, location names and
connections, trait and perk effect callables — stay in `data/` and are looked up
by id on load.

```text
SAVED                              LOOKED UP BY ID ON LOAD
player position, condition,        item definitions (data/items.py)
  inventory, equipment,            location names, descriptions,
  attributes, XP, level             connections (data/locations.py)
trait ids, perk ids                trait and perk effects
NPC position, status, notes,        (data/traits.py, data/perks.py)
  condition
relationships (affinity,
  trust, reputation)
narrative state (day, time,
  goals, flags, stage)
all three memory tiers
```

This is the spirit of [document 12](12-data-model.md)'s *base definition +
persisted mutations*, applied at the level of whole objects rather than as an
event log. Content can be rebalanced — a sharper crowbar, a renamed room —
without invalidating existing saves, because the save never stored those
numbers. It is **not** the event-oriented model that document proposes: there is
no mutation log, so there is no replay, no rollback, and no world history.

Trait and perk effects are *callables*. They could not be serialized even if we
wanted to, which is what forces the by-id split rather than merely recommending
it.

## Compatibility policy

Three rules, in order of severity:

**Schema mismatch discards the save — except v2.** `SCHEMA_VERSION` (now 3)
is written into every save. On load, a v2 save is first upgraded by
`migrate_v2_to_v3` (old rooms remapped onto zones; see
[Implementation Status](00-status.md) for exactly what it rewrites). Any other
`version` that does not match causes the save to be dropped and a new game
started, with a log line. A half-understood save is worse than a fresh one;
v2→v3 is the only migration path, and there is no partial load.

**Unknown ids are dropped, not fatal.** An item id, location id, trait or perk
id in the save that no longer exists in `data/` is skipped with a log line. A
deleted item vanishes from the inventory and the rest of the save loads. This is
what makes content deletion safe between schema versions.

**A corrupt or unreadable file starts a new game.** `load()` returns `None` and
`GameEngine` falls back to `GameManager()`.

`SCHEMA_VERSION` is the only version in the codebase. Document 16 asks for
`generator_version`, `rules_version`, `combat_version` and `loot_version` as
well; none exist, because none of those systems do.

## Writing

`save()` writes atomically — temp file, then replace — after every turn, so an
interrupted write cannot leave a truncated save. The whole state goes out each
time; there is no incremental or append mode.

All dynamic state lives in one file, `gamedata/engine_state.json`. The older
per-file `gamedata/*.json` (`character.json`, `world.json`, `npcs.json`)
belonged to the previous engine and are neither read nor written.

---

[← Traits, Perks, Effects, Modifiers](23-traits-perks-modifiers.md) · [Index](README.md)
