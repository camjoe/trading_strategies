# Docs Migration — Record & Remaining Work

Record of the documentation consolidation that reorganized `docs/` + the doc/agent/skill content of `.github/` into one source of truth (`docs/` + `bots/` at repo root).

> **Status: Pass 1 complete (merged); Pass 2 in progress.** For the live, current state see the **Execution status** section at the top of [`decisions.md`](decisions.md) — it tracks what's built, committed, in progress, and pending.
>
> The execution scaffolding (`execution-runbook.md`, `file-mapping.md`, `proposed-structure.md`, `staged/`) was removed after Pass 1; it's recoverable from git history. This folder now keeps only the durable record.

## Files

| File | Purpose |
|---|---|
| [`decisions.md`](decisions.md) | Numbered decision log — what we decided and why (D-1…D-10, D-OPEN-1…12). The authoritative record. |
| [`consolidation.md`](consolidation.md) | Consolidation Report — overlaps to merge + skills/agents keep-drop triage. Tracks Pass-2 work. |
| [`focus-areas.md`](focus-areas.md) | Candid effort-vs-value scorecard — where the durable value is and where to keep improving. |

## Remaining work

Done in Pass 2: maps/cookbook/nav-guide freshened; `maps_check` + `link_check` built; D-OPEN-9 (style-guide rename). See `decisions.md` Execution status for detail. Remaining:

- **Finish D-9** — `db_schema_check.py` + the `db-schema.md` Quick Reference exist (uncommitted); add a test, a `scripts-map.md` entry, and commit.
- **Cleanup** — add `link_check.py` + `db_schema_check.py` to `scripts-map.md`; remove the stray `project_structure.txt` / `trading_structure.txt`; the ~19 long-tail broken links.
- **D-OPEN-9 sub-decision** — accept `style-guide.md`, or do the split into AGENTS + `coding-style.md`.
- **Pass 2 consolidation** (see `consolidation.md`): `update-documentation` rework, `help/` → generated catalog, business-rules JSON → `docs/business-rules/` transfer.

Delete this folder once the deferred work is complete (history will retain it).
