# Pending One-Time DB Steps

Type: notes
Status: Active
Created: 2026-07-12
Last Reviewed: 2026-07-15
Purpose: Tracker for one-time database deployment steps required outside the normal migration flow.
Related: [Overview](overview.md), [DB Migration System](reference/db-migration-system.md), [Database Cleanup Roadmap](reference/database-cleanup-roadmap.md)

## Status: none pending

No one-time database steps are currently outstanding. Ordinary schema changes ship as numbered
Alembic revisions applied with `python -m scripts.data_ops.manage_db_migrations upgrade` — see
[db-migration-system.md](reference/db-migration-system.md).

## Completed

- **Sleeve-retirement and book-rotation cutovers**, and the **FK cascade rebuilds**.
- **Alembic baseline transition (2026-07-15).** Schema initialization moved from the retired
  probe system to numbered Alembic revisions. Each existing database was reconciled to the clean
  revision `0001` schema (dropping probe-era leftover tables — `broker_orders`, the `sleeve_*` and
  `rotation_episodes` tables — and the retired `strategy_param_sets` store plus the
  `book_strategy_assignments.param_set_id` column) and then stamped at `0001`. The one-time
  reconcile/baseline/verify tooling used for this transition was removed afterward; see git
  history if another pre-Alembic database ever needs adopting.
