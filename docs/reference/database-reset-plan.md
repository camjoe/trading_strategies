# Database Reset Plan

Type: notes
Status: Draft
Created: 2026-07-26
Last Reviewed: 2026-07-26
Purpose: Track the planned migration-chain squash and data reset — what gets dropped, what needs investigation first, and what should be rebuilt differently for stability.
Related: [Database Schema Reference](db-schema.md), [DB Migration System](db-migration-system.md), [ADR 015 Numbered Alembic Migrations](../adr/015-numbered-alembic-migrations.md)

## Purpose

The Alembic chain has grown to 27 revisions (`0001`–`0027`) since the probe-system transition, and
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
| `Reseed` | Decided: rows are discarded, but the fixture seeder rebuilds equivalent state (no export) |

## Current Data Inventory

Row counts from the dev database (`local/paper_trading.db`) on 2026-07-26, verified at revision
`0026`. Staging and prod counts are **not** captured here — their revision level was last verified
on 2026-07-17 and may differ.
Re-check both before executing (see [Investigate Before Dropping](#investigate-before-dropping)).

The schema is **28 tables** at revision `0027`. The counts below were taken at `0026`, when it was
30: revision `0027` has since dropped `walk_forward_experiments` and `walk_forward_windows` along
with the rolling-window path ([ADR 016](../adr/016-optimizer-experiments-as-research-evidence.md)),
so those two rows are already done rather than pending. Most operational tables are already empty in
dev; the real volume is backtest and optimizer research history.

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
| `walk_forward_experiments` | 0 | Walk-forward experiment methodology + window membership | Dropped in `0027` |
| `walk_forward_windows` | 0 | Individual OOS windows linked to their backtest runs | Dropped in `0027` |
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
  (cash, positions, realized P&L, `total_deposited`) is *derived* by replaying them. Currently
  harmless in dev (all zero rows), but this is the table group to check on staging and prod before
  executing. Note that dropping them does *not* zero out opening balances —
  `accounts.initial_cash` is a surviving column and is what the replay starts from. See
  [`total_deposited` is structurally zero](#total_deposited-is-structurally-zero-and-that-is-the-intended-design).
- **The optimizer research record is the multiple-testing audit trail.** 981 trials across 6
  experiments is the evidence for how many parameter combinations were tried before any winner was
  selected. Dropping it is defensible (no edge was found), but it cannot be reconstructed.

## Fixture and Sandbox Findings

Added 2026-07-26 after auditing the three data sources (test seed, offline demo, dev "live" DB) to
decide what the post-reset seed path should be. These findings shape both the reset and the
`sandbox` fixture profile being built ahead of it.

### The dev database is configuration plus research history, nothing else

Every operational table is empty: `orders`, `order_fills`, `ledger`, `positions`,
`equity_snapshots`, `daily_metrics`, `risk_snapshots`, `risk_decisions`, `rotation_decisions`,
`promotion_reviews`, and `promotion_review_events` are all zero rows. The only volume is research
history — 416 backtest runs (12,788 equity points, 10,280 executions) and 6 optimizer experiments
(981 trials). Nothing in the dev database exercises the execution, accounting, risk, or rotation
paths, so it has no value as a test bed and its loss costs nothing operationally.

This also settles the `ledger`/`orders`/`order_fills` concern raised above *for dev*: there is no
account-accounting history to lose here. It remains an open question for staging and prod.

### The demo fixture covers 14 of 30 tables

`local/demo.db` is rebuilt from scratch on every `scripts/launch_demo.py` run, so the file on disk
is disposable debris (it was found at revision `0019`, well behind head). What matters is the
seeder's coverage. `seed_demo_database` populates `accounts`, `books`, `strategies`,
`book_strategy_history`, `book_universe_history`, `orders`, `order_fills`, `positions`,
`equity_snapshots`, `daily_metrics`, `promotion_reviews`, `backtest_runs`,
`backtest_equity_snapshots`, and `backtest_executions`.

It leaves empty: `ledger`, `global_settings`, `feature_providers`, `book_rotation_settings`,
`risk_snapshots`, `risk_decisions`, `rotation_decisions`, `promotion_review_events`, all four
`optimization_*` tables, and both `*_change_events` tables. Those gaps are the work list for the
`sandbox` profile.

### The fixture bypassed `apply_book_fill`, so book accounting diverged

`DemoSeedRepository` wrote `orders`/`order_fills` with direct INSERTs and then hand-wrote
`positions` and `equity_snapshots` to match. That skipped `apply_book_fill`
(`src/trading/services/execution/submission.py`), which is what normally derives a fill's effects.
The result was a fixture whose tables contradicted each other:

- `books.current_cash` stayed at the bootstrapped `10000.0` / `12000.0` despite ~3,000 of seeded
  buys — and `submission.py` documents `books.current_cash` as *authoritative*.
- `ledger` had no `trade` or `fee` entries for fills that definitely happened.
- `equity_snapshots.cash` was hardcoded to `7500`, while replaying the seeded fills against
  `accounts.initial_cash` yields `7644`.
- Snapshot `equity` came from a synthetic wiggle formula, so it did not equal its own row's
  `cash + market_value`.

Fixed by routing seeded trades through `record_trade`
(`src/trading/services/execution/ledger/mutations.py`) — the real manual-trade path, which writes
the order, its fill, the `trade`/`fee` ledger entries, the position, and the book balances in one
transaction, and enforces the sufficient-cash check the direct INSERTs skipped. Positions, cash,
and ledger are now derived rather than asserted.

**Why this belongs in the reset plan:** it is direct evidence for the "build through real writers"
rule the post-reset seed path must follow. Any table the seeder cannot populate through app code is
a finding about the data model, not a licence to hand-write the INSERT.

### `total_deposited` is structurally zero, and that is the intended design

Worth recording so the reset's reseed does not "fix" it wrongly. `create_account` sets
`accounts.initial_cash` and bootstraps the default book's `current_cash` from it directly. It does
**not** write an opening `deposit` row to the `ledger`. Meanwhile `load_account_state`
(`src/trading/services/execution/ledger/queries.py`) computes `total_deposited` purely from ledger
`deposit`/`withdrawal` entries, so it reports `0.0` for every account that was never manually
funded.

Cash is still correct, because `load_account_state` takes `initial_cash` as its starting balance.
Adding a synthetic opening deposit to make `total_deposited` look right would **double-count** the
opening balance — once through `initial_cash`, once through the deposit row. So the fixture must
not do it, and neither should the post-reset seed.

The consequence for this plan is narrower than the earlier note above suggested: dropping `ledger`
does not reset accounts to their `initial_cash` seed *because* `initial_cash` is a column that
survives. What is lost is any manual funding history recorded after account creation.

### The sandbox golden file is the reset rehearsal

The `sandbox` profile builds `local/sandbox.golden.db` (migrate to head, then seed), fingerprinted
by head revision plus seeder hash, and copies it to a throwaway `local/sandbox.db` on each launch so
changes cannot persist. Building it before the squash is deliberate: it exercises the full
"empty database to fully populated" path against the current schema, which is the same path the
reset needs afterward. Anything the seeder cannot build now is a gap found cheaply, before the
revision history is collapsed and there is no fallback.

Expect to re-verify the seeder after the squash. The cost is re-running it against the new `0001`
baseline, which is exactly the validation the reset wants anyway.

### Delivered coverage

A `sandbox` build at revision `0026` populates **21 of the 30 data tables** in about a second,
producing a 1.4 MB database over four accounts, six books, and two years of history. The nine that
remain empty are recorded, with reasons, in `KNOWN_EMPTY_SANDBOX_TABLES`
(`tests/src/trading/services/fixtures/test_seeding.py`); a coverage test fails when a new table
appears and is neither seeded nor listed:

| Table group | Why still empty |
|---|---|
| `optimization_experiments`, `optimization_run_manifests`, `optimization_trials`, `optimization_windows` | Needs a real optimizer sweep driven during seeding |
| `risk_snapshots`, `risk_decisions` | Needs the risk pass driven during seeding |
| `rotation_decisions` | Needs the rotation engine driven during seeding |

Two tables filled themselves as a side effect of the discipline: `book_rotation_settings_change_events`
and `global_settings_change_events` are written by the real settings writers, so seeding settings
through those writers produced the audit rows without the seeder knowing the tables exist. That is
the argument for the rule in miniature.

Backtest and promotion records remain the one place the seeder writes rows no production writer
produced — synthesizing them means running the real backtest and promotion engines, which is the
same work as the optimizer gap above. They are marked `synthetic:FIXTURE` and `fixture-v1` so a
generated row is never mistaken for a real research result.

## Configuration and Catalog

These six tables hold configuration, not history. Each needs an explicit decision plus, where it
is not preserved, a recreation path.

Classified `Reseed` on 2026-07-26: the fixture seeder being built ahead of the squash (see
[Fixture and Sandbox Findings](#fixture-and-sandbox-findings)) is the recreation path. Its `sandbox`
profile has to construct exactly this configuration surface to be useful as a test bed, so the same
code that builds the sandbox re-establishes dev configuration after the reset. That removes the
"expensive manual re-onboarding" risk that kept these `Open`.

| Table | Dev rows | What it holds | Status |
|---|---:|---|---|
| `accounts` | 8 | Account identity, custody, broker connection, `live_trading_enabled` | Reseed |
| `books` | 8 | Execution/risk/option settings columns, required `trade_symbols` | Reseed |
| `strategies` | 11 | Strategy catalog: code primitive + tuned `params_json`, draft/frozen/retired | Reseed + export `params_json` |
| `book_rotation_settings` | 8 | Sparse per-book rotation scheduling and champion/challenger overrides | Reseed |
| `feature_providers` | 0 | Enabled external feature providers | Reseed |
| `global_settings` | 0 | Singleton row of runtime/evaluation/promotion overrides | Reseed |

`strategies` is the one that most resembles "losing our strategies", and it is the one table that
is only *partly* reseedable. Strategy *logic* is code and is unaffected; `seed_strategy_catalog`
rebuilds the catalog rows from the code primitives. But tuned `params_json` and each row's
draft/frozen/retired lifecycle state are **not** derivable from code — export those 11 rows before
the reset even though the table is otherwise reseedable.

`live_trading_enabled` must come back as `0` on every reseeded account. The seeder is bound by the
Live Trading Safety Guard in `docs/architecture/architecture-conventions.md`: no fixture, seed, or
script may set that flag to `1`. If a post-reset account is meant to trade live, a human operator
sets the flag by hand.

## Investigate Before Dropping

- **Staging and prod revision level and row counts.** Last verified 2026-07-17 as unconfirmed.
  Run `manage_db_migrations status` and a row-count pass on both before assuming they resemble dev.
  Prod in particular may hold real `ledger`/`orders` rows that dev does not.
- **Whether any optimizer or backtest result is still being cited.** If a conclusion in a doc or
  memory note points at a specific `optimization_experiments` row, dropping it orphans the
  citation. Decide whether to export a summary first.
- ~~**What the post-reset seed path actually is.**~~ Resolved 2026-07-26. `seed_clean_schema`
  covers only the code-derived strategy catalog and per-account default books; it cannot reproduce
  accounts, book settings, or tuned strategy parameters. The fixture seeder's `sandbox` profile is
  being built to cover the rest, and is the designated post-reset recreation path — see
  [Fixture and Sandbox Findings](#fixture-and-sandbox-findings). Still to confirm: whether the
  reseeded configuration should mirror today's 8 accounts exactly or be deliberately reshaped.
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
- **Seedability as a design constraint.** Being acted on ahead of the reset rather than discovered
  during it: the fixture seeder's `sandbox` profile is the checked-in seed definition that makes the
  next reset cheap. A `sandbox` build that leaves a table empty is the signal that the seed
  definition has a hole, which is why the build ships with a check asserting no table is empty.
- **Money representation: `REAL` vs integer minor units.** Open, added 2026-08-07. Every monetary
  and quantity value is an IEEE double in a `REAL` column — 106 of them in the `0001` baseline
  (`cash`, `equity`, `avg_cost`, `price`, `commission`, `realized_pnl`, …). Institutional systems
  use fixed-point; SQLite has no decimal type, so the alternative is integer minor units plus
  conversion at every read and write, and in the domain accounting math.

  **Current exposure is low, and worth recording precisely so it is not over- or under-rated.**
  Order quantities are whole numbers (`auto_trading_policy.py` sizes with
  `int(spendable // price)` and `int(position_qty)`), so the exact float comparison in
  `domain/accounting.py` — `if positions[ticker] == 0` — cannot leave dust. Money accumulates
  rounding, but nothing compares money for equality and there is no broker cash reconciliation
  with a tolerance, so the error is invisible at any realistic fill count.

  **What would raise it:** supporting fractional shares (that `== 0` becomes a live bug, leaving
  a phantom open position with a stale average cost), adding a broker balance reconciliation, or
  trading real capital.

  **Why it belongs here:** the conversion is a schema change across ~106 columns. Doing it during
  a squash that is already accepting data loss is roughly the only time the cost is reasonable.
  Decide before authoring the new `0001` baseline, not after.

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
6. Re-seed configuration with the fixture seeder, then re-import the exported `strategies`
   `params_json` and lifecycle state.
7. Regenerate `database-diagram-viewer.html`, sync `db-schema.md`, run
   `python -m scripts.checks.repo.migration_check` and `python -m scripts.checks.docs.readme_check`.
8. Run the database test suites (`tests/src/infrastructure/database/`,
   `tests/scripts/test_manage_db_migrations.py`, `tests/scripts/test_migration_check.py`).

Use the `db-migration` skill (`.ai/skills/db-migration/`) to drive execution.

## Decided

- **Build the fixture seeder before the squash** (2026-07-26). The effort is roughly the same either
  way, and doing it first gives the reset a validated seed path instead of leaving re-onboarding to
  be improvised. Accepted cost: the seeder needs re-verification against the new `0001` baseline.
- **Configuration tables are `Reseed`, not `Preserve`** (2026-07-26) — with an export of the 11
  `strategies` rows for their tuned `params_json` and lifecycle state. See
  [Configuration and Catalog](#configuration-and-catalog).

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
