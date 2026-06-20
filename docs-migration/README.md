# Docs Migration — Record & Remaining Work

One-source-of-truth consolidation of `docs/` + the doc/agent/skill content of `.github/` into `docs/` + `.ai/` at repo root. **Pass 1 (move) is merged to develop; Pass 2 (consolidate/freshen) is nearly done.**

This folder is a temporary record — delete it once the remaining work lands (git retains the history).

## What's left

### Finish this branch (Pass 2)

All Pass 2 work is done. ✅

- **Long-tail broken links** — fixed (20 → 0).
- **`update-documentation` skill rework** — done; `docs-check.md` removed, skill narrowed to semantic rewriting role, detection owned by CI tooling.

### Future branch goals

Each is a self-contained chunk of work for its own later branch — not part of finishing Pass 2.

- **`help/` → generated catalog** — build the catalog from skill/agent `when-to-use` frontmatter so it can't drift. (D-OPEN-11.)
- **business-rules JSON → `docs/business-rules/`** — transfer the JSON content in as authoritative; make the web-app JSON derived. (D-OPEN-5.)
- **scripts discoverability** — enrich `scripts-map` on usage/safety and cross-link scripts ↔ the skills/agents that drive them. (D-OPEN-12.)

## Done

- **Pass 1** — all moves, renames, ADR numbering, `.ai/`, link rewrites, thin entrypoints (`CLAUDE.md`, `.github/copilot-instructions.md`), `CONTRIBUTING.md`. Merged via PRs #131/#132.
- **Pass 2** — `maps_check`, `link_check`, and `db_schema_check` (D-9) built, wired into CI as advisory checks, and tested; style guides split by surface (D-OPEN-9); `trading-package-map` / `service-cookbook` / `nav-guide` freshened for the develop-merge API renames.

## The record

[`decisions.md`](decisions.md) is the authoritative log — the numbered decisions (D-1…D-10, D-OPEN-1…12) with their outcomes, plus the principles worth keeping past this migration.

