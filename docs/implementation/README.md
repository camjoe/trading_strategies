# Implementation Guides & Handoff Strategy

Type: index
Status: Active
Created: 2026-07-01
Last Reviewed: 2026-07-01
Purpose: How implementation work is sliced into self-contained work orders and handed off — including
to a lighter/cheaper model — so execution is reliable and stops safely. Indexes the per-initiative
guides.
Related: [Status](../status.md), [Decisions](../decisions.md), [Developer Notes](../developer-notes.md)

## Purpose

Define how implementation work is sliced into bounded work orders and handed off to execution
sessions without expanding scope or weakening validation.

## Usage

Use these guides when preparing or executing one initiative slice. Each work order should name exact
files, stop conditions, and validation commands before it is handed to an execution session.

## Handoff model (two roles)

- **Planner (strong model / operator):** resolves decisions, writes the detailed work order, does any
  design-heavy first slice, and reviews the result.
- **Executor (light model):** takes **one bounded work order**, makes the exact changes, runs the
  checks, and commits **only if green**. It does **not** design, resolve decisions, or expand scope —
  on any ambiguity or red check it **stops and reports**.

## Operating model (running it efficiently)

- **Control tower (one long-lived planning session).** Holds the full plan/decisions/schema context.
  It resolves decisions, writes/refines work orders, does the design-heavy first slice of hard
  initiatives, and reviews results. **It never blocks on PR merges** — it keeps the work-order queue
  full ahead of execution.
- **Execution sessions (short-lived, one per work order).** Light model for mechanical chunks, strong
  for logic-heavy ones. Each is pointed at one self-contained work order, on one branch off the latest
  `develop`. Kick off with: *"Implement `docs/implementation/<file>.md` following this README's
  execution protocol; stop and report on any ambiguity or red check."*
- **Branch/PR unit = one initiative** (may hold several phase-commits — e.g. P3's phases A–E on one
  branch). Not one-commit-per-PR; never a mega-branch (that is what we escaped).
- **Planning-doc changes** batch on their own short-lived docs branch off `develop` — they do **not**
  ride a feature branch's PR.
- **PR flow:** the executor pushes and opens the PR; **the human is the merge gate** (review + merge).
  A light-model executor opens its own PR so the human just reviews.
- **Sequencing:**
  - *Dependent* work (e.g. P4 needs P3) — merge the prerequisite, then branch. Don't stack.
  - *Independent* work (e.g. P2 and P8; P1 vs P3-planning) — run in parallel off `develop`, bounded by
    the human's review bandwidth (realistically 1–2 concurrent streams for a solo reviewer).
- **Throughput rule:** decouple planning from execution — keep ready work orders queued so execution
  never waits on planning; dependent chains merge in order while independent ones run in parallel.

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

## Completed work orders (archived)

All per-initiative work orders written to date are complete and archived under
[`../history/implementation/`](../history/README.md): P1 (execution loop), P2/1c (decision-score
contract tests), P3 (DB schema rewrite, phases A–E), P4/2a+2c (shared submission/accounting), and
P4/2b (unified rotation + the `Rotation*` naming pass). No work order is currently active — see
[`../status.md`](../status.md) for what's next.

**The pattern:** the Planner resolves decisions and builds the design-heavy first slice; the light
model does the mechanical fan-out (per-table models/repos, tests, seeds, mechanical refactors).

## Writing a work order (template)

Copy the structure of
[p2-evaluation-contract-tests.md](../history/implementation/p2-evaluation-contract-tests.md) (sections
marked _(template)_ generalize). For a light-model handoff specifically, make §6 (steps) exact —
prefer concrete code or exact file paths over descriptions, and make the stop conditions explicit.
