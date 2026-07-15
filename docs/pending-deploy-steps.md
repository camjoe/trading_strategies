# Pending One-Time DB Steps

Type: notes
Status: Active
Created: 2026-07-12
Last Reviewed: 2026-07-15
Purpose: Single tracker for the pending one-time database steps, their required order, and the operator actions still needed for existing databases.
Related: [Overview](overview.md), [DB Migration System](reference/db-migration-system.md), [Database Cleanup Roadmap](reference/database-cleanup-roadmap.md)

## Purpose

Use this as the top-level deployment checklist for existing SQLite databases. The detailed
procedures live in the linked references; this page owns the order, backup expectations, and the
"what remains" status.

Windows: use `.venv\Scripts\python.exe` in place of `.venv/bin/python`.
Run data-ops while scheduler jobs are not mid-run.

Completed and retired from this tracker: the sleeve-retirement and book-rotation cutovers, and
the Step 0 FK cascade rebuilds (all known databases have been opened with that code and carry
the target FK actions).

## Current Sequence

| Order | Step | Status | How it runs | Required before deploy? |
|---|---|---|---|---|
| 1 | Reconcile schema to `0001` | Built — action required | One-time SQL per database | Yes — precedes baseline |
| 2 | Alembic baseline transition | Built — action required | One-time operator command per database | Yes — the app refuses unversioned databases |

Both steps are one-time per database and become dead once every database has crossed over.

## Step 1 — Reconcile Schema to `0001`

**Why:** the retired probe system never dropped tables or columns from existing databases, so live
databases still carry probe-era leftovers that revision `0001` (the current clean schema) does not
have: the superseded `broker_orders` and sleeve/rotation-episode tables, plus the retired
`strategy_param_sets` store and the unused `book_strategy_assignments.param_set_id` column. A
database that still has these cannot baseline (or pass `verify`) against `0001`, so shed them
first.

**Per existing database:**

1. Stop scheduler jobs.
2. Reconcile (backs up first, drops the leftovers, rebuilds `book_strategy_assignments` to the
   clean shape, and runs a foreign-key check):
   ```bash
   .venv/bin/python -m scripts.data_ops.reconcile_to_0001
   ```
   The script drops whichever leftovers a given database happens to carry, so the same command
   converges dev, prod, and staging alike. `broker_orders` holds historical order data superseded
   by the `orders` table — it is dropped and preserved only in the backup. The rebuild (rather
   than `DROP COLUMN param_set_id`) is needed because a plain drop fails when the legacy foreign
   key is present, which some databases carry and some do not. Requires SQLite ≥ 3.35 (Python 3.14
   bundles 3.50+).

Then proceed to Step 2. Validate the whole sequence on a **copy** of each database first
(reconcile → `baseline` → `verify` go green) before running against the live file — confirmed
against dev, prod, and staging copies.

**Cleanup:** `scripts/data_ops/reconcile_to_0001.py` (and its test) are transitional — delete them
once every database has crossed over.

## Step 2 — Alembic Baseline Transition

**What changed:** schema initialization moved from the automatic probe system to numbered Alembic
revisions (`docs/reference/db-migration-system.md`). Runtime no longer creates or migrates
schema: `ensure_db()` refuses any database that is not stamped at the expected head, so every
existing database needs a one-time `baseline` stamp before the app, scheduler, CLI, or web
backend will open it.

**Per existing database (after Step 1):**

1. Install dependencies (Alembic ships in `requirements-dev.txt`):
   ```bash
   .venv/bin/pip install -r requirements-dev.txt
   ```
2. Adopt and verify:
   ```bash
   .venv/bin/python -m scripts.data_ops.manage_db_migrations status
   .venv/bin/python -m scripts.data_ops.manage_db_migrations baseline
   .venv/bin/python -m scripts.data_ops.manage_db_migrations verify
   ```
   `baseline` validates the schema against revision `0001` and stamps it without running DDL;
   mismatches are reported object-by-object and nothing is stamped.
3. Restart jobs and confirm a health check passes.

Fresh databases skip both steps and run `python -m scripts.data_ops.manage_db_migrations upgrade`,
which creates a missing or empty database at head.

**Rollback:** `baseline` only writes the `alembic_version` table; restoring the pre-transition
backup (or dropping that table) returns the database to its previous state. The Step 1 drops are
recovered only from the backup.
