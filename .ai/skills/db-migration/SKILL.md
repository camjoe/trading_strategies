---
name: db-migration
description: Manages numbered Alembic schema migrations for the trading database — authoring revisions, validating them, estimating risk, planning rollbacks, and SQLite batch rebuilds. Use when asked to add a column, author or validate a migration revision, assess schema change risk, change foreign-key actions, or plan a downgrade/rollback.
---

# DB Migration

Handles the full lifecycle of a schema change: design → validate → risk check → rollback plan.
For a complete schema change, run all four tasks in order unless asked for a specific one.

The schema is owned by a **linear, numbered Alembic revision chain** in
`src/infrastructure/database/alembic/versions/` (see
`docs/reference/db-migration-system.md`). Runtime never migrates — operators apply revisions
with `scripts.data_ops.manage_db_migrations`.

## Choose a task

| Task | Use when | Reference |
|---|---|---|
| Create migration | Authoring a new numbered revision (column, table, index) | [create-migration.md](create-migration.md) |
| SQLite table rebuild | FK actions, constraints, column drops — anything `ADD COLUMN` cannot express | [sqlite-table-rebuild.md](sqlite-table-rebuild.md) |
| Validate migration | Checking a proposed revision for safety and correctness | [validate-migration.md](validate-migration.md) |
| Estimate risk | Assessing blast radius, index needs, and backtest impact | [estimate-risk.md](estimate-risk.md) |
| Generate rollback | Planning downgrade/backup recovery for a revision | [generate-rollback.md](generate-rollback.md) |

## Hard rules (apply to all tasks)

- Applied revisions are **immutable** — never edit or reorder one; fixes are new revisions.
- Revisions are **self-contained**: no application imports, literal values only
  (enforced by `python -m scripts.checks.repo.migration_check`).
- Every revision implements both `upgrade()` and `downgrade()`, nonempty (enforced).
- Revision ids are 4-digit numeric, strictly increasing, single linear head (enforced).
- Update `schema_version.EXPECTED_HEAD_REVISION` in the same commit as a new revision (enforced).
- Every `NOT NULL` column added to a populated table **must** have a `DEFAULT`.
- FK/constraint changes use Alembic batch operations (`op.batch_alter_table`) — see the
  table-rebuild reference.
- Revisions that `UPDATE`/`DELETE` existing rows require explicit human review.
- Operators back up before any migration (`manage_db_migrations` does this automatically);
  downgrades restore schema shape only, backups recover data.
- Never set `live_trading_enabled = 1` or point broker columns at live endpoints.

## Repo references

- `src/infrastructure/database/alembic/versions/` (revision chain)
- `src/infrastructure/database/migration_runner.py`
- `src/infrastructure/database/schema_version.py`
- `src/infrastructure/database/schema_compare.py`
- `scripts/data_ops/setup_db_schema.py`, `scripts/data_ops/manage_db_migrations.py`
- `scripts/checks/repo/migration_check.py`
- `docs/reference/db-migration-system.md`
- `docs/architecture/architecture-conventions.md`
