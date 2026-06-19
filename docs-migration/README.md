# Docs Migration — Record & Remaining Work

Record of the documentation consolidation that reorganized `docs/` + the doc/agent/skill content of `.github/` into one source of truth (`docs/` + `bots/` at repo root).

> **Status: Pass 1 complete.** The structural migration (moves, renames, ADR numbering, `bots/`, link rewrite, thin entrypoints, CONTRIBUTING, conventions) is done and committed. What remains is deferred tooling + Pass-2 consolidation — see below.
>
> The execution scaffolding (`execution-runbook.md`, `file-mapping.md`, `proposed-structure.md`, `staged/`) was removed after Pass 1; it's recoverable from git history. This folder now keeps only the durable record.

## Files

| File | Purpose |
|---|---|
| [`decisions.md`](decisions.md) | Numbered decision log — what we decided and why (D-1…D-10, D-OPEN-1…12). The authoritative record. |
| [`consolidation.md`](consolidation.md) | Consolidation Report — overlaps to merge + skills/agents keep-drop triage. Tracks Pass-2 work. |
| [`focus-areas.md`](focus-areas.md) | Candid effort-vs-value scorecard — where the durable value is and where to keep improving. |

## Remaining work (deferred from Pass 1)

- **D-9** — build the `describe_db_schema.py` markdown generator (also gives `docs/reference/db-schema.md` its doc-header).
- **D-OPEN-6** — build `scripts/checks/maps_check.py` (map ⇄ filesystem drift check).
- **Pass 2 consolidation** (see `consolidation.md`): style-guide merge (D-OPEN-9), `update-documentation` rework, `help/` → generated catalog, business-rules JSON → `docs/business-rules/` transfer.
- **Freshen** `trading-package-map.md` / `service-cookbook.md` / `nav-guide.md` for the renamed repository APIs from the develop merge.

Delete this folder once the deferred work is complete (history will retain it).
