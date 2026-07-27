# Database Reset Plan

Type: notes
Status: Draft
Created: 2026-07-26
Last Reviewed: 2026-07-26
Purpose: Track the planned migration-chain squash and data reset — what gets dropped, what needs investigation first, and what should be rebuilt differently for stability.
Related: [Database Schema Reference](db-schema.md), [DB Migration System](db-migration-system.md), [ADR 015 Numbered Alembic Migrations](../adr/015-numbered-alembic-migrations.md)

## Purpose

The Alembic chain has grown to 26 revisions (`0001`–`0026`) since the probe-system transition, and
the data in the deployed databases has drifted far enough that it is no longer worth carrying
forward. This document tracks the plan to collapse the revision history back to a single clean
`0001` baseline and reset the data, deciding table by table what is dropped, what needs a look
first, and what should come back in a different shape.

This is a working plan, not a completed record. Items move from `Open` to `Decided` as decisions
are made, and the document becomes a completion record when the work lands.

## Goals

1. **Single clean baseline** — one `0001_current_schema.py` reproducing the current head shape;
   revisions `0002`–`0026` deleted, `EXPECTED_HEAD_REVISION` back to `"0001"`.
2. **Deliberate data loss, not incidental** — every table has an explicit decision recorded here
   before anything is dropped. Nothing disappears because it was overlooked.
3. **Rebuild what was fragile** — where a table's shape or lifecycle caused problems, use the
   reset as the opportunity to change it rather than reproducing it faithfully.
4. **No surprise re-onboarding** — configuration that has to be recreated by hand after the reset
   is identified in advance, with a recreation path (seed script, export/reimport, or accepted
   manual re-entry).

## Status Legend

| Status | Meaning |
|---|---|
| `Drop` | Decided: data is discarded at reset, no export |
| `Investigate` | Needs a look before deciding — value, volume, or downstream dependency unclear |
| `Open` | Not yet classified |
| `Preserve` | Decided: must survive the reset (export/reimport or seed path required) |

## Current Data Inventory

Row counts from the dev database (`local/paper_trading.db`) on 2026-07-26. Staging and prod counts
are **not** captured here — their revision level was last verified on 2026-07-17 and may differ.
Re-check both before executing (see [Investigate Before Dropping](#investigate-before-dropping)).

The schema is **30 tables** at revision `0026`. Most operational tables are already empty in dev;
the real volume is backtest and optimizer research history.

## Drop List — Audit and History

These tables hold records of what happened, not configuration needed to run. All are classified
`Drop`: they are recoverable only from a pre-reset database backup, and none is required for the
system to operate after the reset.

| Table | Dev rows | What is lost | Status |
|---|---:|---|---|
| `orders` | 0 | Clean-schema order records (book-keyed execution history) | Drop |
| `order_fills` | 0 | Individual fill events; part of the account-state replay source | Drop |
| `ledger` | 0 | Cash/trade/fee entries incl. deposits — the account-accounting spine | Drop |
| `positions` | 0 | Current open positions per book | Drop |
| `equity_snapshots` | 0 | Point-in-time cash/equity/P&L snapshots | Drop |
| `daily_metrics` | 0 | Per-day return/drawdown/hit-rate per book | Drop |
| `risk_snapshots` | 0 | Account-level risk metric snapshots | Drop |
| `risk_decisions` | 0 | Allow/rescale/block risk decision history | Drop |
| `rotation_decisions` | 0 | Hold/rotate decision records per book | Drop |
| `promotion_reviews` | 0 | Strategy promotion review cases | Drop |
| `promotion_review_events` | 0 | State transitions and notes within a review | Drop |
| `book_strategy_history` | 8 | Effective-dated strategy assignment history | Drop |
| `book_universe_history` | 8 | Which universes a book traded, and when | Drop |
| `book_rotation_settings_change_events` | 0 | Rotation-settings change audit (revision `0025`) | Drop |
| `global_settings_change_events` | 0 | Global-settings change audit (revision `0025`) | Drop |
| `backtest_runs` | 416 | Backtest run metadata (dates, fees, slippage, purpose) | Drop |
| `backtest_equity_snapshots` | 12,788 | Equity curve points within backtest runs | Drop |
| `backtest_executions` | 10,280 | Simulated buy/sell executions within backtest runs | Drop |
| `walk_forward_experiments` | 0 | Walk-forward experiment methodology + window membership | Drop |
| `walk_forward_windows` | 0 | Individual OOS windows linked to their backtest runs | Drop |
| `optimization_experiments` | 6 | Optimizer runs: config, winner params, OOS + holdout summaries | Drop |
| `optimization_windows` | 102 | Per-window train/test boundaries and winner run links | Drop |
| `optimization_trials` | 981 | Every evaluated grid candidate — the multiple-testing audit record | Drop |
| `optimization_run_manifests` | 6 | Frozen provenance per optimizer run (economics, universe, engine revision) | Drop |

### Consequences worth naming

- **`book_strategy_history` and `book_universe_history` are not purely historical.** The *open*
  row in each is current state: which strategy a book is running now, and which universes it
  trades. Dropping them means the post-reset seed must re-establish the open assignment, not just
  the history.
- **`ledger` + `orders`/`order_fills` are the account-accounting source of truth.** `AccountState`
  (cash, positions, realized P&L, `total_deposited`) is *derived* by replaying them. Dropping them
  resets every account to its `initial_cash` seed. Currently harmless in dev (all zero rows), but
  this is the table group to check on staging and prod before executing.
- **The optimizer research record is the multiple-testing audit trail.** 981 trials across 6
  experiments is the evidence for how many parameter combinations were tried before any winner was
  selected. Dropping it is defensible (no edge was found), but it cannot be reconstructed.

## Not Yet Classified — Configuration and Catalog

These six tables hold configuration, not history. Each needs an explicit decision plus, where it
is `Drop`, a recreation path.

| Table | Dev rows | What it holds | Status |
|---|---:|---|---|
| `accounts` | 8 | Account identity, custody, broker connection, `live_trading_enabled` | Open |
| `books` | 8 | Execution/risk/option settings columns, required `trade_universes` | Open |
| `strategies` | 11 | Strategy catalog: code primitive + tuned `params_json`, draft/frozen/retired | Open |
| `book_rotation_settings` | 8 | Sparse per-book rotation scheduling and champion/challenger overrides | Open |
| `feature_providers` | 0 | Enabled external feature providers | Open |
| `global_settings` | 0 | Singleton row of runtime/evaluation/promotion overrides | Open |

`strategies` is the one that most resembles "losing our strategies": strategy *logic* is code and
is unaffected, but the catalog of configured instances, their tuned parameters, and their
draft/frozen/retired lifecycle state lives here.

## Investigate Before Dropping

- **Staging and prod revision level and row counts.** Last verified 2026-07-17 as unconfirmed.
  Run `manage_db_migrations status` and a row-count pass on both before assuming they resemble dev.
  Prod in particular may hold real `ledger`/`orders` rows that dev does not.
- **Whether any optimizer or backtest result is still being cited.** If a conclusion in a doc or
  memory note points at a specific `optimization_experiments` row, dropping it orphans the
  citation. Decide whether to export a summary first.
- **What the post-reset seed path actually is.** `seed_clean_schema` exists, but whether it can
  reproduce the current 8 accounts / 8 books / 11 strategies — or whether that is manual re-entry —
  is unverified and gates how expensive the reset is.
- **Backup retention.** Backups are the only recovery path for everything in the drop list. Confirm
  where the pre-reset backups land and that they are kept, not rotated away.

## Stability and Redesign Candidates

Things the reset is an opportunity to change rather than faithfully reproduce.

- **History retention policy.** Promotion, risk, backtest, and walk-forward history have no
  age-based retention — rows accumulate until their account is deleted. Carried over as an open
  follow-up from the 2026-07 cleanup. Worth deciding now, since the tables are about to be empty.
- **Universe membership snapshots.** `book_universe_history` records universe *names*, not
  membership; definitions stay file-backed, so historical evaluation cannot reconstruct what a
  universe contained. Known accepted gap — revisit if universe definitions have stabilized.
- **Seedability as a design constraint.** If the reset shows that recreating accounts/books/
  strategies is painful manual work, that is an argument for a checked-in seed definition so the
  next reset is cheap.
- **`db-schema.md` table count drift.** The quick-reference header says 27 tables; the schema has
  30. Fix as part of the doc regeneration step.

## Procedure (Draft)

Not final — refine once the classification decisions above are closed.

1. Capture the head schema: `python -m scripts.data_ops.describe_db_schema`.
2. Author a new `0001_current_schema.py` reproducing that shape, with a drop-all `downgrade()`.
3. Delete revisions `0002`–`0026`.
4. Set `EXPECTED_HEAD_REVISION = "0001"` in `src/infrastructure/database/schema_version.py`.
5. Back up, then drop and recreate each database; `manage_db_migrations upgrade` creates a fresh
   one at head.
6. Re-seed the `Preserve` configuration.
7. Regenerate `database-diagram-viewer.html`, sync `db-schema.md`, run
   `python -m scripts.checks.repo.migration_check` and `python -m scripts.checks.docs.readme_check`.
8. Run the database test suites (`tests/src/infrastructure/database/`,
   `tests/scripts/test_manage_db_migrations.py`, `tests/scripts/test_migration_check.py`).

Use the `db-migration` skill (`.ai/skills/db-migration/`) to drive execution.

## Open Questions

- Squash from `main`, or fold in-flight branch work (including the uncommitted
  `0026_drop_rotation_cost_penalty_weight.py`) into the new baseline first?
- Is dropping data actually required? The 2026-07 probe→Alembic transition squashed the chain while
  *keeping* rows via reconcile-and-stamp. Keeping configuration while still getting a clean history
  is a viable middle path if the configuration classification lands on `Preserve`.
- Do staging and prod get the same treatment on the same day, or does dev go first as a rehearsal?

## Related Docs

- [Database Schema Reference](db-schema.md) — table purposes, FK relationships, semantic notes
- [DB Migration System](db-migration-system.md) — revision authoring rules, operator commands
- [ADR 015 Numbered Alembic Migrations](../adr/015-numbered-alembic-migrations.md) — why runtime is verify-only
