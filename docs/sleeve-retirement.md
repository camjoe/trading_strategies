# Sleeve Retirement — Tracker

Type: plan
Status: Active
Created: 2026-07-08
Last Reviewed: 2026-07-08
Purpose: The single home for the sleeve-retirement workstream — verdict, evidence, decisions,
phased plan, and progress — until the work completes. Everything about this task lives here.
Related: [Status](status.md), [ADR 003 — Sleeve Virtualization](adr/003-sleeve-virtualization-architecture.md)
(superseded by this work at completion), [Architecture Conventions](architecture/architecture-conventions.md)

> **Verdict (investigated 2026-07-08): sleeves are redundant — remove, don't rename.**
> Accounts + books become the one terminology and code flow for trading and strategy analysis.
> Branch: `features/sleeve-retirement`.

## Evidence for the verdict

1. **The data model is fully duplicated.** `strategy_sleeves` is a column-for-column subset of
   `books` (account_id, name, status, balances, trade_universes). `sleeve_strategy_assignments`
   duplicates `book_strategy_assignments` (same one-open-assignment-per-book invariant; both exist).
2. **Sleeve balances are dead.** Frozen since the P4 cutover; book balances are authoritative.
   Every sleeve is mapped to its bridging book (`book_bridge.book_id_for_sleeve`) before anything
   real happens — the sleeve row is a lookup indirection.
3. **Nothing creates sleeves.** No CLI, no UI, no service writes `strategy_sleeves`. Sleeves are a
   static registry answering "which books exist and what strategy does each run" — exactly what
   `books` + `book_strategy_assignments` model.
4. **A live drift bug.** Sleeve rotation writes `sleeve_strategy_assignments` on rotate, but
   `book_strategy_assignments` is written only at seeding — the book-native record silently goes
   stale after every rotation. Retiring sleeves makes book assignments the single live record.

## Current consumer map (what must migrate)

| Consumer | Reads/writes | Migrates to |
|---|---|---|
| `services/sleeves/execution.py` (intent generation) | sleeve rows + active assignment + trade_universes | enumerate account books + open book assignment |
| `services/auto_trading/runtime.py` sleeve-mode branch | sleeve enumeration → bridging books | iterate books directly (no bridge) |
| `services/sleeves/rotation.py` applier | **writes** sleeve assignments on rotate | **writes** book assignments (fixes the drift bug) |
| `services/sleeves/shadow_evaluation.py` + daily challenger job | sleeve enumeration + assignments | book enumeration + assignments |
| `services/sleeves/daily_report.py`, `reconciliation.py`, `universe_config.py` | sleeve rows (partly book-native already) | books |
| `services/ibkr_paper_monitor/queries.py` (3 sites) + monitor UI labels | sleeve summaries | book summaries |
| Governance jobs ×5 (`w1_leaderboard`, `w2_promotion_review`, `w3_allocation_review`, `m2_parameter_governance`, `m3_performance_audit`) | `SleeveRepository` reads | book reads |
| `sleeve_risk_decisions` table + `runtime_sleeve_risk.py` | sleeve_id FK audit rows | book-keyed audit (greenfield swap) |
| `models/sleeves/` (11 files), `domain/sleeve_accounting.py`, `domain/sleeve_risk_gate.py` | sleeve-named contracts/policy | book-named (rename/move; `SleeveFillTransition` already book-agnostic) |
| `repositories/sleeves.py`, `book_bridge.book_id_for_sleeve` | the sleeve store + bridge | retired |
| Tables `strategy_sleeves`, `sleeve_strategy_assignments` | storage | dropped (greenfield) |

## Decisions

### Resolved

- **Remove, don't rename (2026-07-08).** Sleeves retain no functionality books lack; see evidence.
- **Book assignments become the single strategy-assignment record.** The rotation applier writes
  `book_strategy_assignments`; `sleeve_strategy_assignments` retires. This is the drift-bug fix and
  lands first (SR-1).

### Open (resolve in-phase; stop and report if bigger)

- **D-SR1 — param_set carry.** `sleeve_strategy_assignments` carries `param_set_id`; intent
  generation reads it. `book_strategy_assignments` has no such column. Options: (a) add
  `param_set_id` column (append-only add; faithful migration), or (b) resolve the active param set
  by strategy at read time (`StrategyParamSetRepository.fetch_active`). **Lean: (a)** — preserves
  per-assignment pinning that rotation sets today; (b) changes behavior when multiple param sets exist.
- **D-SR2 — risk-audit keying.** `sleeve_risk_decisions.sleeve_id` FKs `strategy_sleeves`. Options:
  greenfield-swap to a book-keyed table, or keep account-keyed with a `book_id` column. Decide at SR-5;
  pre-live data is droppable per the P3/P4 stance.
- **D-SR3 — execution-mode collapse.** With books first-class, "account mode" = trade the default
  book; "sleeve mode" = trade all assigned books. Possibly one mode: *trade every active book with an
  open assignment* (default book is just a book). Attractive (kills the mode branch) but
  behavior-affecting — decide at SR-2, not before.
- **D-SR4 — package naming.** `services/sleeves/` → `services/books/` (or fold pieces into
  `execution`/`auto_trading`). Decide at SR-6 with the rename table in hand.

## Phased plan (each phase = one green commit; `run_checks ci` gates)

| Phase | Scope | Size |
|---|---|---|
| **SR-1** | Assignment unification: rotation applier + intent generation write/read `book_strategy_assignments` via the bridging book (D-SR1 resolved here; label→`strategy_id` via existing bridge helper). `sleeve_strategy_assignments` becomes unwritten/unread. | M |
| **SR-2** | Enumeration migration: runtime sleeve-mode + shadow evaluation + daily challenger job enumerate account **books** (D-SR3 decided here); `book_id_for_sleeve` callers eliminated. | M |
| **SR-3** | Reporting/monitor: daily_report, reconciliation, universe_config, ibkr_paper_monitor (+ UI labels) onto books. | M |
| **SR-4** | Governance jobs ×5 onto book reads. | S |
| **SR-5** | Risk audit re-keyed to books (D-SR2); `runtime_sleeve_risk` renamed. | S–M |
| **SR-6** | Code retirement + renames: `repositories/sleeves.py`, `models/sleeves/` moves, `domain/sleeve_*` renames, `services/sleeves/` package rename (D-SR4), bridge mapping removal. | M |
| **SR-7** | Drop `strategy_sleeves` + `sleeve_strategy_assignments` (+ old risk table per D-SR2); docs/maps sync; supersede note on ADR 003; close this tracker (fold outcome into status.md, delete this file). | S |

Estimated total: **L** (~2b-sized; 7 ordered green commits, multiple sessions).

## Guardrails

- Safety only strengthens: no kill switch, gate, or audit weakens to ease a migration step.
- Behavior-affecting steps (SR-1, SR-2) get regression tests proving rotation/trading behavior is
  unchanged (or the intended fix, for the drift bug) before/after.
- Append-only column rules apply to `accounts`; the clean book tables follow the greenfield pattern.
- If a step surfaces functionality sleeves provide that books cannot — stop, record it here, decide.

## Validation

```
.venv\Scripts\python.exe -m scripts.checks.run_suite src/trading/services/sleeves src/trading/services/auto_trading --no-cov
.venv\Scripts\python.exe -m scripts.run_checks ci     # per phase, before commit
```

## Progress log (append one line per phase)

- 2026-07-08 — Investigation + verdict recorded; branch `features/sleeve-retirement` created; plan written.
