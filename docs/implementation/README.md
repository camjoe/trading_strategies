# Implementation Guides & Handoff Strategy

Type: index
Status: Active
Created: 2026-07-01
Last Reviewed: 2026-07-01
Purpose: How implementation work is sliced into self-contained work orders and handed off — including
to a lighter/cheaper model — so execution is reliable and stops safely. Indexes the per-initiative
guides.
Related: [Plan](../plan.md), [Decisions](../decisions.md), [Developer Notes](../developer-notes.md)

## Handoff model (two roles)

- **Planner (strong model / operator):** resolves decisions, writes the detailed work order, does any
  design-heavy first slice, and reviews the result.
- **Executor (light model):** takes **one bounded work order**, makes the exact changes, runs the
  checks, and commits **only if green**. It does **not** design, resolve decisions, or expand scope —
  on any ambiguity or red check it **stops and reports**.

## Chunk-readiness checklist

A work order may be handed to a light model only if **all** hold:

1. **No open decisions** in scope (every referenced `Dn` is resolved).
2. **Small, single-commit** — S, or a tight M.
3. **Exact files + exact expected change** (or exact code) — no "figure out where/how."
4. **Deterministic self-check** — a command whose pass/fail is unambiguous.
5. **Explicit stop conditions** — "if X, stop and report; do not improvise."
6. **No cross-cutting judgment** — naming, architecture, or trade-offs are pre-decided.

If any fail, a Planner must tighten the work order (or keep the chunk) before handoff.

## Light-model execution protocol

The rules a light model follows for **any** work order here:

1. **Read the whole work order** and confirm every precondition. If a precondition is unmet → stop,
   report which one.
2. **Make only the changes specified**, in the files specified. Do not refactor, rename, or "improve"
   anything out of scope.
3. **Run the validation commands** exactly as written (venv interpreter, repo root).
4. **Green → commit** with the given message format (end with the `Co-Authored-By` line) → push /
   report the result.
5. **Red or ambiguous → STOP.** Report the exact command output or the ambiguity. Do **not** guess,
   change the contract, weaken a test, or expand scope to force green.
6. **Never** set `live_trading_enabled`; never touch broker endpoints; never commit on red.
7. One work order = one focused commit (or the per-phase commits the order specifies).

## Handoff queue (current readiness)

| Work order | Ready for light model? | Notes |
|---|---|---|
| [p2-evaluation-contract-tests.md](p2-evaluation-contract-tests.md) (P2/1c) | ✅ **first handoff** | Test-only; no decisions; exact assertions. |
| [p3-db-schema-rewrite.md](p3-db-schema-rewrite.md) Phase A (DDL) | ❌ Planner | Needs D4 settings-shape; design work. |
| p3 Phases B/C (models, repositories) | ◑ after A | Mechanical **per-table** fan-out — carve one chunk per table. |
| p3 Phase D (seed) | ◑ after A | Mechanical. |
| p3 Phase E (re-point reads) | ❌ Planner | Judgment about consumers. |
| P1 (execution loop) | ❌ needs breakdown | Real logic/wiring; sub-step the guide first. |

**The pattern:** the Planner resolves decisions and builds the design-heavy first slice; the light
model does the mechanical fan-out (per-table models/repos, tests, seeds, mechanical refactors).

## Writing a work order (template)

Copy the structure of [p2-evaluation-contract-tests.md](p2-evaluation-contract-tests.md) (sections
marked _(template)_ generalize). For a light-model handoff specifically, make §6 (steps) exact —
prefer concrete code or exact file paths over descriptions, and make the stop conditions explicit.
