# Docs Migration Plan

Working folder for consolidating all project documentation (`docs/` + the doc/agent/skill content in `.github/`) into **one source of truth**. This folder is the human-readable record of our decisions; update it as we go.

> Status: **Planning** — no source files have been moved yet. We are resolving the target structure before migrating.

## Files in this folder

| File | Purpose |
|---|---|
| [`proposed-structure.md`](proposed-structure.md) | The target folder structure. The shape we are migrating toward. Living doc. |
| [`file-mapping.md`](file-mapping.md) | Per-file tracker: source path → destination path + status. The migration log. |
| [`decisions.md`](decisions.md) | Numbered decision log — what we decided and why. Append-only. |
| [`focus-areas.md`](focus-areas.md) | Candid effort-vs-value scorecard — where to spend energy and where you'll need to keep improving. |
| [`consolidation.md`](consolidation.md) | Consolidation Report — overlaps to merge, and skills/agents/docs keep-drop triage. |
| [`execution-runbook.md`](execution-runbook.md) | Ordered Pass-1 procedure: moves, renames, link sweep, verification, rollback. |
| [`staged/`](staged/) | Holding area for files authored/edited now that belong in the final structure (e.g. the real `naming.md`). Grab at migration time. |

## How to use

1. Discuss a structural question → record the outcome in [`decisions.md`](decisions.md).
2. If it changes the shape → update [`proposed-structure.md`](proposed-structure.md).
3. When a file's destination is settled → set its row in [`file-mapping.md`](file-mapping.md) to **Decided**.
4. Only after destinations are **Decided** do we execute moves.

## Ground rules (see decisions.md for detail)

- Moving is preferred over rewriting; rewriting over deleting. Nothing gets deleted.
- Everything is in git — moves are safe and reversible.
- CI config (`.github/workflows/*.yml`, `.github/dependabot.yml`) stays in `.github/`; it is out of scope.
- The scaffold currently lives at `agentswip/`; that name is temporary (see [D-OPEN-1](decisions.md)).
