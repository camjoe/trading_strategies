# Pending One-Time DB Steps

Type: notes
Status: Active
Created: 2026-07-12
Last Reviewed: 2026-07-14
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
| 1 | Alembic baseline transition | Built — action required | One-time operator command per database | Yes — the app refuses unversioned databases |
| 2 | Drop legacy `strategy_param_sets` store | Not built | Future revision `0002` + normal `upgrade` | Not needed for current deploy |

## Step 1 — Alembic Baseline Transition

**What changed:** schema initialization moved from the automatic probe system to numbered Alembic
revisions (`docs/reference/db-migration-system.md`). Runtime no longer creates or migrates
schema: `ensure_db()` refuses any database that is not stamped at the expected head, so every
existing database needs a one-time `baseline` stamp before the app, scheduler, CLI, or web
backend will open it.

**Per existing database:**

1. Stop scheduler jobs.
2. Install dependencies (Alembic ships in `requirements-dev.txt`):
   ```bash
   .venv/bin/pip install -r requirements-dev.txt
   ```
3. Inspect, adopt, and verify:
   ```bash
   .venv/bin/python -m scripts.data_ops.manage_db_migrations status
   .venv/bin/python -m scripts.data_ops.manage_db_migrations baseline
   .venv/bin/python -m scripts.data_ops.manage_db_migrations verify
   ```
   `baseline` validates the schema against revision `0001` and stamps it without running DDL;
   mismatches are reported object-by-object and nothing is stamped.
4. Restart jobs and confirm a health check passes.

Fresh databases instead run `python -m scripts.data_ops.setup_db_schema` (no baseline needed).

**Rollback:** `baseline` only writes the `alembic_version` table; restoring the pre-transition
backup (or dropping that table) returns the database to its previous state.

## Step 2 — Drop the Legacy `strategy_param_sets` Store

**Status:** not built; do not run as part of the current deploy.

The strategy-catalog work retired the param-set thread in code, but the physical schema still
contains `strategy_param_sets`, its index, `book_strategy_assignments.param_set_id`, and that
FK. The cleanup is authored as migration revision `0002` on a follow-up branch and applied with
the standard workflow (`status` → `upgrade` → `verify`), which backs up automatically. Afterward,
regenerate the DB diagram viewer and update `docs/reference/db-schema.md`.

This is tracked as future cleanup, not current deployment work.
