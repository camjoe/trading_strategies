# Database Cleanup Roadmap

Type: notes
Status: Active
Created: 2026-07-13
Last Reviewed: 2026-07-15
Purpose: Future cleanup ideas for narrowing the database schema after the current deploy steps are complete.
Related: [Database Schema Reference](db-schema.md), [DB Migration System](db-migration-system.md)

## Purpose

This note captures future database cleanup ideas that are not required before deploying the current FK
cascade work. Use it when planning the next schema cleanup branch, especially around the wide
`accounts` table and the remaining legacy account-owned columns.

## Overview

The schema is moving toward a book-owned execution model. `accounts` should become mostly account
identity and custody metadata, while execution behavior belongs on books and typed settings tables.
The current `accounts` table still carries historical settings from earlier account-mode execution:
goals, risk controls, options settings, rotation settings, broker connection fields, and trade
universe defaults.

The preferred cleanup direction is typed one-to-one extension tables or book-owned settings tables,
not generic key/value or category/value tables. Mapping tables should be reserved for true
many-to-many or history relationships.

## Candidate Shape

| Area | Target owner | Notes |
|---|---|---|
| Account identity | `accounts` | Keep `id`, `name`, `account_kind`, `base_ccy`, `initial_cash`, `created_at`, `updated_at`, and possibly `descriptive_name` / `benchmark_ticker`. |
| Broker connection + safety gate | `account_broker_settings` | Candidate 1:1 table keyed by `account_id`; preserve the hard `live_trading_enabled` safety rule. |
| Execution/risk knobs | `book_execution_settings` | Already exists; prefer this over account-level risk/sizing columns once migrations prove all readers use book settings. |
| Options/leaps knobs | `book_option_settings` | Already exists; account-level option columns are cleanup candidates after deploy validation. |
| Rotation config | `book_rotation_settings` | Already exists; account-level rotation columns are cleanup candidates after the book-rotation cutover is run everywhere. |
| Strategy ownership | `book_strategy_assignments` and `strategies` | Keep assignment/history semantics here; avoid reintroducing account-level strategy as runtime source of truth. |
| Goals and trade universes | Decide account default vs book-owned | If they are execution-unit specific, move to `books`; if they are account-wide defaults, use a typed account profile/defaults table. |

## Cleanup Candidates

These are candidates only; do not remove them until code reads, deploy status, and live DB contents are
verified.

### Account-Level Execution Columns

**Status: blocked — live readers remain.** The book trade-intent path still reads
`account.risk_policy`, `stop_loss_pct`, `take_profit_pct`, and `instrument_mode`
(`src/trading/services/books/execution.py`), and trade sizing still reads
`trade_size_pct` / `max_position_pct` (`src/trading/services/auto_trading/execution.py`).
`book_execution_settings` exists but is not yet consumed by the execution path (only the
parameters view and catalog seeding touch it), so this group needs a reader cutover to book
settings before any column removal.

Likely cleanup candidates after book-owned execution is fully deployed:

- `learning_enabled`
- `risk_policy`
- `stop_loss_pct`
- `take_profit_pct`
- `profit_take_pct`
- `max_loss_pct`
- `trade_size_pct`
- `max_position_pct`
- `instrument_mode`

Expected target: `book_execution_settings`.

### Account-Level Option Columns

**Status: blocked — live readers remain.** Option/leaps selection still reads these columns
from the account (`src/trading/domain/auto_trading_policy.py`,
`src/trading/services/auto_trading/execution.py`, `src/trading/services/reporting/presentation.py`,
and the validation in `src/trading/services/accounts/config.py`). `book_option_settings` exists
but the runtime readers have not moved to it.

Likely cleanup candidates after option/leaps readers are confirmed book-owned:

- `option_strike_offset_pct`
- `option_min_dte`
- `option_max_dte`
- `option_type`
- `target_delta_min`
- `target_delta_max`
- `max_premium_per_trade`
- `max_contracts_per_trade`
- `iv_rank_min`
- `iv_rank_max`
- `roll_dte_threshold`

Expected target: `book_option_settings`.

### Account-Level Rotation Columns

**Status: ready — no remaining readers.** `AccountRecord` no longer materializes any
`rotation_*` field (ADR 014), and no code reads them from `accounts`; rotation scheduling is
book-owned and rotation state lives in `book_strategy_assignments` and `rotation_decisions`.
This is the least risky group and the right first removal: a single numbered Alembic
migration rebuilding `accounts` without these columns, following the migration `0002`
rebuild pattern.

Columns to remove:

- `rotation_enabled`
- `rotation_mode`
- `rotation_optimality_mode`
- `rotation_interval_days`
- `rotation_interval_minutes`
- `rotation_lookback_days`
- `rotation_schedule`
- `rotation_regime_strategy_risk_on`
- `rotation_regime_strategy_neutral`
- `rotation_regime_strategy_risk_off`
- `rotation_overlay_mode`
- `rotation_overlay_min_tickers`
- `rotation_overlay_confidence_threshold`
- `rotation_overlay_watchlist`
- `rotation_active_index`
- `rotation_last_at`
- `rotation_active_strategy`

Expected target: `book_rotation_settings`, `rotation_decisions`, and assignment state as applicable.

### Broker Columns

Consider splitting these into a typed 1:1 `account_broker_settings` table:

- `broker_type`
- `broker_host`
- `broker_port`
- `broker_client_id`
- `live_trading_enabled`

This split is cleaner for diagramming and ownership, but it must preserve the Live Trading Safety
Guard exactly: automated code must never enable live trading or point accounts at live endpoints.

### Goals and Universes

Needs an explicit ownership decision before cleanup:

- `goal_min_return_pct`
- `goal_max_return_pct`
- `goal_period`
- `trade_universes`

If these are defaults for the account, a typed `account_profile` or `account_defaults` table is
reasonable. If they vary by execution unit, keep moving them to `books`.

## Suggested Order

1. ~~Deploy and verify the FK cascade table rebuilds.~~ **Done at code level**
   (`features/database-accounts-split`): migration `0002` rebuilds `rotation_decisions` to
   full CASCADE, account-deletion cascade is covered by tests, and admin deletions back up
   the database by default. Remaining: run `alembic upgrade` against the live database —
   `ensure_db()` refuses to start on a stale revision, so this cannot silently drift.
2. ~~Run the pending sleeve-retirement and book-rotation cutover steps everywhere.~~ **Done**:
   no sleeve code remains in `src/`, and the book-rotation cutover has run everywhere.
3. Confirm no runtime, CLI, UI backend, or reporting path reads legacy account-level execution
   columns as source of truth. (Per-group status is noted on each cleanup group above —
   rotation is clear; execution and option groups still have live readers.)
4. Build a cleanup branch for one ownership group at a time, starting with the least risky group
   (currently the rotation columns).
5. For physical column removal, add a numbered Alembic migration per ownership group following
   the `0002` rebuild pattern: self-contained literal DDL, explicit column copy list, table
   rebuild, `PRAGMA foreign_key_check`, and a reversible downgrade (ADR 015).
6. Regenerate `docs/reference/database-diagram-viewer.html` and update `docs/reference/db-schema.md`
   after each schema cleanup.

## Boundaries

- Do not introduce generic EAV/category/value tables for account settings.
- Do not add mapping tables unless the relationship is genuinely many-to-many or historical.
- Do not remove legacy columns until every target environment has completed the dependent deploy
  steps and code no longer reads those columns.
- Do not weaken the live-trading safety guard while moving broker settings.
- Keep account-level history and retention decisions separate from settings cleanup. Promotion,
  risk, backtest, and walk-forward retention still need explicit product/operator decisions.

## Related Docs

- [Database Schema Reference](db-schema.md)
- [DB Migration System](db-migration-system.md)
