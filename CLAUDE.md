# CLAUDE.md

Project-level guidance for Claude Code and agents working in this repository.

## Docs Folder Guide

| Folder | Purpose |
|---|---|
| `docs/architecture/` | **How** the system is designed — layers, boundaries, service API |
| `docs/conventions/` | **Rules** this project follows — coding style, doc standards, naming |
| `docs/maps/` | **Where** things live — file/directory maps, updated frequently |
| `docs/reference/` | **Why** decisions were made (ADRs) and deep-dive notes on subsystems |
| `docs/runbooks/` | **How to operate** — step-by-step procedures for humans or agents |

When creating a new doc, pick the folder whose purpose matches — don't put conventions in reference or operational notes in architecture.

## Keeping Docs Fresh

When you add files, rename paths, or add service functions, update the relevant map in `docs/maps/`. For larger sync passes (after a batch of changes), use the `update-documentation` skill located at `bots/skills/update-documentation/`:

- **Docs sync** — actively updates stale docs after code changes; see `docs-sync.md`
- **Docs check** — passive staleness audit; see `docs-check.md`

The `docs/maps/docs-map.md` "Goes stale when" column is your guide for which docs to touch after a given change.

## Key Reference Points

- `docs/maps/docs-map.md` — full documentation inventory and staleness guide
- `docs/architecture/nav-guide.md` — task-oriented "I want to X → edit Y" lookup
- `docs/architecture/service-cookbook.md` — which function to call for common tasks
- `docs/architecture/architecture-conventions.md` — authoritative layering and import boundary rules (agents load this)
