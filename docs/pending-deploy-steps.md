# Pending One-Time DB Steps

Type: notes
Status: Active
Created: 2026-07-12
Last Reviewed: 2026-07-13
Purpose: Single tracker for the pending one-time database steps, their required order, and the operator actions still needed for existing databases.
Related: [Overview](overview.md), [Sleeve-Retirement DB Migration](runbooks/sleeve-retirement-db-migration.md), [Book-Rotation Cutover](runbooks/book-rotation-cutover.md), [Account Deletion Cascade Proposal](reference/account-deletion-cascade-proposal.md), [Database Cleanup Roadmap](reference/database-cleanup-roadmap.md), [ADR 014](adr/014-execution-mode-collapse.md)

## Purpose

Use this as the top-level deployment checklist for existing SQLite databases. The detailed
procedures live in the linked runbooks; this page owns the order, backup expectations, and the
"what remains" status.

Fresh databases need no one-time action for Steps 0-2 because the current DDL and create flows
already produce the target shape.

Windows: use `.venv\Scripts\python.exe` in place of `.venv/bin/python`.
Run data-ops while scheduler jobs are not mid-run.

## Current Sequence

| Order | Step | Status | How it runs | Required before deploy? |
|---|---|---|---|---|
| 0 | FK cascade table rebuilds | Built | Automatic on first DB initialization with new code | Back up before first startup/data-op with new code |
| 1 | Sleeve-retirement DB migration | Built | Operator data-op | Run after deploy on existing DBs |
| 2 | Book-rotation cutover | Built | Operator data-op | Run after Step 1 on existing DBs |
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

## Step 1 — Sleeve-Retirement DB Migration

**Status:** built; run once per existing DB after the sleeve-retirement code is deployed.

**Command:**

```bash
.venv/bin/python -m trading.interfaces.runtime.data_ops.migrate_sleeve_books
```

**What it does:** ensures legacy sleeve rows are represented as books and open
`book_strategy_assignments`. It is idempotent.

**Operator checklist:**

1. Back up the DB.
2. Run the command above.
3. Use the verification query in
   [sleeve-retirement-db-migration.md](runbooks/sleeve-retirement-db-migration.md).
4. Drop the four orphaned legacy sleeve/risk tables only after explicit sign-off:
   `sleeve_strategy_assignments`, `strategy_sleeves`, `sleeve_risk_decisions`,
   `portfolio_risk_snapshots`.
5. Confirm the next daily job evaluates/trades the expected books.

**Rollback:** before dropping tables, restore the backup only if needed; the data-op itself only
adds book rows/assignments. After dropping tables, restore the pre-drop backup.

Full procedure: [Sleeve-Retirement DB Migration](runbooks/sleeve-retirement-db-migration.md).

## Step 2 — Book-Rotation Cutover

**Status:** built; run once per existing DB after Step 1.

**Command:**

```bash
.venv/bin/python -m trading.interfaces.runtime.data_ops.migrate_book_rotation
```

**What it does:** syncs retained account-level rotation scheduling into `book_rotation_settings`
and opens missing default-book assignments. It is idempotent.

**Operator checklist:**

1. Back up the DB.
2. Run the command above.
3. Use the two verification queries in [book-rotation-cutover.md](runbooks/book-rotation-cutover.md).
4. Spot-check `.venv/bin/python -m trading.interfaces.cli.main parameters`.
5. Confirm the next daily job trades expected default books and writes rotation/risk rows.

**Rollback:** restore the pre-cutover backup. The data-op only adds/updates rotation-settings rows
and opens assignments.

Full procedure: [Book-Rotation Cutover](runbooks/book-rotation-cutover.md).

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

## After All Existing DBs Are Migrated

Once every environment has completed Steps 1 and 2:

- Remove `migrate_sleeve_books.py`, its tests, and
  [sleeve-retirement-db-migration.md](runbooks/sleeve-retirement-db-migration.md).
- Remove `migrate_book_rotation.py`, its tests, and
  [book-rotation-cutover.md](runbooks/book-rotation-cutover.md).
- Remove the corresponding rows from `docs/runbooks/README.md`, `docs/maps/trading-package-map.md`,
  and this file.
- Start the future schema cleanup from
  [database-cleanup-roadmap.md](reference/database-cleanup-roadmap.md), if desired.
