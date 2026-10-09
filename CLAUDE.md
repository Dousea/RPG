@AGENTS.md

## Claude Code

- A PostToolUse hook runs `ruff format` and `ruff check --fix` on every `.py`
  file Claude edits; fix what it reports.

## Agent skills

### Issue tracker

Issues are briefs in `.claude/briefs/<slug>/brief.md`, queued in `.claude/briefs/TODO.md`, the input to the implementer pipeline. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default role strings (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`), as a `Status:` line. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one root `CONTEXT.md` plus `docs/adr/`, created lazily. See `docs/agents/domain.md`.
