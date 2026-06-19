# Docs Migration — Record & Remaining Work

One-source-of-truth consolidation of `docs/` + the doc/agent/skill content of `.github/` into `docs/` + `bots/` at repo root. **Pass 1 (move) is merged to develop; Pass 2 (consolidate/freshen) is nearly done.**

This folder is a temporary record — delete it once the remaining work lands (git retains the history).

## What's left

- **Long-tail broken links** — ~19 refs flagged by `link_check` (advisory; doesn't block). Fix incrementally.
- **`update-documentation` skill rework** — now that `maps_check`/`readme_check` do the deterministic staleness detection, narrow the skill to the semantic "rewrite the prose/responsibilities" role. (See `decisions.md` D-OPEN-6.)
- **`help/` → generated catalog** — build the catalog from skill/agent `when-to-use` frontmatter so it can't drift. (D-OPEN-11.)
- **business-rules JSON → `docs/business-rules/`** — transfer the JSON content in as authoritative; make the web-app JSON derived. (D-OPEN-5.)
- **scripts discoverability** — enrich `scripts-map` on usage/safety and cross-link scripts ↔ the skills/agents that drive them. (D-OPEN-12, future.)

## Done

- **Pass 1** — all moves, renames, ADR numbering, `bots/`, link rewrites, thin entrypoints (`CLAUDE.md`, `.github/copilot-instructions.md`), `CONTRIBUTING.md`. Merged via PRs #131/#132.
- **Pass 2** — `maps_check`, `link_check`, and `db_schema_check` (D-9) built, wired into CI as advisory checks, and tested; style guides split by surface (D-OPEN-9); `trading-package-map` / `service-cookbook` / `nav-guide` freshened for the develop-merge API renames.

## The record

[`decisions.md`](decisions.md) is the authoritative log — the numbered decisions (D-1…D-10, D-OPEN-1…12) with their outcomes, plus the principles worth keeping past this migration.
