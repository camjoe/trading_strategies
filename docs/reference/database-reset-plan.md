# Database Reset Plan

Type: notes
Status: Complete — code squash landed 2026-09-12; deployed-database rollout is operator work
Created: 2026-07-26
Last Reviewed: 2026-09-12
Purpose: Record the completed migration-chain squash and define the deployed-database rollout — what is dropped, what is recreated, and how.
Related: [Database Schema Reference](db-schema.md), [DB Migration System](db-migration-system.md), [ADR 015 Numbered Alembic Migrations](../adr/015-numbered-alembic-migrations.md)

## Squash outcome (2026-09-12)

The migration-chain squash landed on branch `features/migration-squash`. The new
`0001_current_schema.py` reproduces the former `0031` head shape in one CREATE. A fresh build from
the new baseline matches the captured head column-for-column and FK-for-FK across all 27 tables,
with a clean `PRAGMA foreign_key_check`. Revisions `0002`–`0031` were deleted and
`EXPECTED_HEAD_REVISION` is back to `"0001"`.

Two cleanups were folded in:

- The unused `feature_providers` table was dropped (28 → 27 tables).
- The retired `rolling_window` value was dropped from the `backtest_runs.purpose` CHECK.

The data path is **drop + reseed**. No reconcile-and-stamp helper was built.

## Deployed-database rollout (operator work)

The squash changes the code, not any running database. An existing database is still stamped `0031`
and fails `ensure_db` until it joins the new chain. Dev `local/paper_trading.db` is one such
database. Staging and prod row counts are unconfirmed from this environment — check them first.

Procedure per database:

1. Confirm the revision and row counts: `python -m scripts.data_ops.manage_db_migrations status`.
2. Back up the database file. The backup is the only recovery path for the dropped rows.
3. Drop the file, then `python -m scripts.data_ops.manage_db_migrations upgrade` to build a fresh
   database at the new `0001`.
4. Recreate the strategy catalog and default books:
   `python -m trading.interfaces.runtime.data_ops.seed_clean_schema`.
5. Recreate accounts and their books through the account-create path (account profiles / CLI). No
   seeder reproduces the real accounts — see [Configuration and Catalog](#configuration-and-catalog).
6. Set `live_trading_enabled = 1` by hand only where an account is meant to trade live. The Live
   Trading Safety Guard forbids any seed or script from setting it.

## What is dropped

Every history, audit, research, and operational table is dropped and not recreated: `orders`,
`order_fills`, `ledger`, `positions`, `equity_snapshots`, `daily_metrics`, `risk_snapshots`,
`risk_decisions`, `rotation_decisions`, `promotion_reviews`, `promotion_review_events`,
`book_strategy_history`, `book_universe_history`, the two `*_change_events` audit tables, the
`backtest_*` tables, and the `optimization_*` tables. None is required for the system to run after
the reset. They are recoverable only from the pre-reset backup.

One caveat before dropping on staging or prod: `ledger`, `orders`, and `order_fills` are the
account-accounting source of truth. `AccountState` (cash, positions, realized P&L,
`total_deposited`) is derived by replaying them. Dev holds zero rows in all three, so the loss is
free there; staging and prod may hold real rows, so confirm before you drop.

## Configuration and Catalog

Six configuration tables held the live setup before the squash. The table below records the current
recreation path for each. `feature_providers` was dropped in the squash and is gone.

The `Dev rows` column is the count **still present** in `local/paper_trading.db`, which the squash
did not touch (it remains at revision `0031`). A rollout drops these rows; only then must they be
recreated.

| Table | Dev rows | Recreation path |
|---|---:|---|
| `accounts` | 8 | Manual re-entry through the account-create path (profiles / CLI). No seeder creates real accounts. |
| `books` | 8 | Created with each account; `ensure_default_books` repairs a missing default book for an existing account only. |
| `book_rotation_settings` | 8 | Created with each book; `seed_clean_schema` writes the disabled-rotation defaults. |
| `strategies` | 10 | `seed_strategy_catalog` rebuilds one row per code primitive. No export is needed — see below. |
| `global_settings` | 0 | Optional operator overrides; when the row is absent the system uses code defaults. Set values through the settings CLI if wanted. |
| `feature_providers` | — | Dropped in the squash. Not recreated. |

**`strategies` needs no export.** The earlier plan assumed 11 tuned rows worth exporting. That is no
longer true: the dev catalog now holds 10 rows, all `draft`, all `enabled`, all with empty
`params_json`. Nothing is tuned, so nothing is lost. `seed_strategy_catalog` rebuilds the 8 code
primitives (`trend`, `ma_crossover`, `mean_reversion`, `rsi`, `breakout`, `pullback_trend`,
`bollinger_mean_reversion`, `volatility_filtered_trend`). Two alias rows (`momentum` → `trend`,
`mean reversion` → `rsi`) carry no params; recreate them by hand only if you still want the aliases.

**The real re-onboarding cost is accounts and books, not strategies.** No tracked seeder reproduces
the real 8 accounts, their broker connection, or their book settings. The fixture `sandbox` and
`demo` profiles build synthetic accounts for a test bed, not the live configuration. So plan for
manual account re-entry after the reset.

## Notes worth keeping

- **`total_deposited` is structurally zero by design.** `create_account` sets
  `accounts.initial_cash` and bootstraps the default book's `current_cash` from it; it writes no
  opening `deposit` row. `load_account_state` computes `total_deposited` only from ledger
  `deposit`/`withdrawal` entries, so it reports `0.0` for an account that was never manually funded.
  Cash is still correct, because the replay starts from `initial_cash`. Do not add a synthetic
  opening deposit at reseed — it double-counts the opening balance.
- **Seed through real writers.** A table the seeder cannot populate through application code is a
  finding about the data model, not a reason to hand-write the INSERT. The `sandbox` fixture profile
  is the checked-in seed definition, and a coverage check fails when a new table is neither seeded
  nor listed in `KNOWN_EMPTY_SANDBOX_TABLES`.
- **`book_universe_history` write side is correct; the read side was never built.** Keep the table
  and its writers. Point-in-time membership only exists later if it is recorded now.

## Open follow-up

- **Money representation: `REAL` → integer minor units.** This is now in scope. Cameron intends to
  trade fractional shares, which turns the current float representation into a live bug: the whole-
  units guard in `domain/accounting/account.py` blocks fractional quantities today, and the exact
  float position check would otherwise leave dust — a phantom open position with a stale average
  cost. The conversion touches ~106 monetary and quantity columns plus every read, write, and
  accounting site, and it needs share quantity to carry a defined decimal precision, not only money.
  Plan this change before it is implemented.

## Related Docs

- [Database Schema Reference](db-schema.md) — table purposes, FK relationships, semantic notes
- [DB Migration System](db-migration-system.md) — revision authoring rules, operator commands
- [ADR 015 Numbered Alembic Migrations](../adr/015-numbered-alembic-migrations.md) — why runtime is verify-only
