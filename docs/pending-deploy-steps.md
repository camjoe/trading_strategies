# Pending One-Time DB Steps

Type: notes
Status: Active
Created: 2026-07-12
Last Reviewed: 2026-07-13
Purpose: Single tracker for the pending one-time database steps, their required order, and the operator actions still needed for existing databases.
Related: [Overview](overview.md), [Account Deletion Cascade Proposal](reference/account-deletion-cascade-proposal.md), [Database Cleanup Roadmap](reference/database-cleanup-roadmap.md)

## Purpose

Use this as the top-level deployment checklist for existing SQLite databases. The detailed
procedures live in the linked runbooks; this page owns the order, backup expectations, and the
"what remains" status.

Fresh databases need no one-time action for Step 0 because the current DDL already has the target
FK actions. The completed sleeve-retirement and book-rotation cutovers have been retired from this
tracker and their temporary tooling has been removed.

Windows: use `.venv\Scripts\python.exe` in place of `.venv/bin/python`.
Run data-ops while scheduler jobs are not mid-run.

## Current Sequence

| Order | Step | Status | How it runs | Required before deploy? |
|---|---|---|---|---|
| 0 | FK cascade table rebuilds | Built | Automatic on first DB initialization with new code | Back up before first startup/data-op with new code |
| 3 | Drop legacy `strategy_param_sets` store | Not built | Future cleanup branch + data-op | Not needed for current deploy |

## Step 0 — FK Cascade Rebuilds

**What changes:** table rebuild migrations update FK actions for child-owned and account-owned rows.
They run automatically from `init_schema()` through `ensure_table_rebuild_migrations()`.

**Important:** the first process that opens the DB with the new code applies this step. That includes
the app, scheduler, CLI, and data-op commands that call `ensure_db()`.

**Before first startup with the new code:**

1. Stop or avoid scheduler jobs.
2. Back up the SQLite DB while still on old code, or copy the DB file manually before any new-code
   command opens it.
3. Deploy/start the new code.
4. Verify:
   ```bash
   .venv/bin/python -m scripts.data_ops.audit_foreign_keys --source live --scope all
   ```

Expected changed FK actions:

- `order_fills.order_id -> orders.id ON DELETE CASCADE`
- `backtest_trades.run_id -> backtest_runs.id ON DELETE CASCADE`
- `backtest_equity_snapshots.run_id -> backtest_runs.id ON DELETE CASCADE`
- `promotion_review_events.review_id -> promotion_reviews.id ON DELETE CASCADE`
- `walk_forward_group_runs.group_id -> walk_forward_groups.id ON DELETE CASCADE`
- `trades.account_id -> accounts.id ON DELETE CASCADE`
- `orders.account_id -> accounts.id ON DELETE CASCADE`
- `orders.book_id -> books.id ON DELETE CASCADE`
- `backtest_runs.account_id -> accounts.id ON DELETE CASCADE`
- `walk_forward_groups.account_id -> accounts.id ON DELETE CASCADE`
- `promotion_reviews.account_id -> accounts.id ON DELETE CASCADE`
- `risk_snapshots.account_id -> accounts.id ON DELETE CASCADE`
- `risk_decisions.account_id -> accounts.id ON DELETE CASCADE`
- `risk_decisions.book_id -> books.id ON DELETE SET NULL`

Deliberately unchanged: `walk_forward_group_runs.run_id -> backtest_runs.id` stays `NO ACTION`.

**Rollback:** restore the pre-deploy backup. Reverting code alone does not restore old FK actions
after the rebuild has run.

## Step 3 — Drop the Legacy `strategy_param_sets` Store

**Status:** not built; do not run as part of the current deploy.

The strategy-catalog work retired the param-set thread in code, but the physical schema still
contains:

- `strategy_param_sets`
- `idx_strategy_param_sets_strategy_active`
- `book_strategy_assignments.param_set_id`
- the FK from `book_strategy_assignments.param_set_id` to `strategy_param_sets.id`

This cleanup needs a follow-up branch:

1. Remove the table/index/column/FK from fresh DDL and migration registrations.
2. Add a one-time idempotent data-op for existing DBs.
3. Back up before running it.
4. Verify `strategy_param_sets` no longer exists and `book_strategy_assignments` no longer has
   `param_set_id`.
5. Regenerate the DB diagram viewer and update `docs/reference/db-schema.md`.

This is tracked as future cleanup, not current deployment work.
