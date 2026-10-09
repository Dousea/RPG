# Issue tracker: briefs

Work for this repo is tracked as briefs under `.claude/briefs/`, which `.gitignore`
keeps out of git. A brief is what the `implementer` agent builds from, and the
`reviewer` and `test-auditor` agents check against, so an issue written here can go
straight into that pipeline.

## Conventions

- One task per directory: `.claude/briefs/<slug>/`, the slug in kebab case. A task
  too big for one implementer run is split into stages with numbered slugs
  (`<slug>-1`, `<slug>-2`, ...), one brief each, built in order.
- The issue is `.claude/briefs/<slug>/brief.md`, in the shape the existing briefs
  use: a `# <slug> — <title>` heading, a base line (start from `main` HEAD, leave
  `config.yml`, never commit), then `## Why`, `## What to build` (numbered
  behaviours), `## Docs`, `## Out of scope`, `## Done when` (tests that prove it,
  and `mise run check` passes).
- A brief states behaviour and constraints, not code. It names files and line
  ranges as pointers, and uses the words in `CONTEXT.md`.
- Triage state is a `Status:` line under the heading (see `triage-labels.md`).
- The queue is `.claude/briefs/TODO.md`: one `- [ ] N. \`<slug>\`: <one line>`
  per brief, under a dated heading for the effort. When the task is committed, tick
  it and add the commit hash: `- [x] ... (\`abc1234\`)`.
- `TODO.md` holds only open work. Ticked items move to `.claude/briefs/DONE.md`
  under their effort's heading (the heading moves too once nothing under it is
  open), so `TODO.md` stays short. Don't read `DONE.md` unless asked about past
  work; git history holds the same through the commit hashes.
- Brief folders stay where they are when done: they are only ever opened by slug,
  and old reports and findings name those paths.
- The pipeline adds `report.md` (the implementer's hand-off) and `findings.md` (the
  reviewer's and auditor's findings) beside the brief. Discussion goes there or in a
  `## Comments` section at the bottom of the brief.

## When a skill says "publish to the issue tracker"

Write `.claude/briefs/<slug>/brief.md` and add its line to `.claude/briefs/TODO.md`.
A spec or plan that needs several tickets becomes staged briefs, one per ticket.

## When a skill says "list the open issues"

Read `.claude/briefs/TODO.md`. Never scan the brief folders to find open work.

## When a skill says "fetch the relevant ticket"

Read `.claude/briefs/<slug>/brief.md`, and its `report.md` and `findings.md` if
they exist. The user normally gives the slug.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a file with one **child** brief per ticket.

- **Map**: `.claude/briefs/<effort>/map.md` (the Notes / Decisions-so-far / Fog body).
- **Child ticket**: `.claude/briefs/<effort>-NN-<slug>/brief.md`, numbered from `01`,
  with the question in the body. A `Type:` line records the ticket type
  (`research`/`prototype`/`grilling`/`task`); a `Status:` line records
  `claimed`/`resolved`.
- **Blocking**: a `Blocked by: NN, NN` line near the top. A ticket is unblocked when
  every brief it lists is `resolved`.
- **Frontier**: scan `.claude/briefs/<effort>-*/` for briefs that are open,
  unblocked and unclaimed; first by number wins.
- **Claim**: set `Status: claimed` and save before any work.
- **Resolve**: append the answer under an `## Answer` heading, set
  `Status: resolved`, then append a context pointer (gist + link) to the map's
  Decisions-so-far.
