# SQLite Table Rebuild (Alembic Batch Operations)

Use this reference when a schema change cannot be expressed as `ALTER TABLE ... ADD COLUMN`.
SQLite cannot alter FK actions, constraints, or primary keys in place. Use Alembic batch mode when
the complete table contract can be represented explicitly; use literal create/copy/drop/rename DDL
when SQLite reflection cannot preserve unnamed constraints, partial indexes, or legacy shapes.

## When This Applies

- Changing `ON DELETE` / `ON UPDATE` behavior.
- Adding, changing, or removing table constraints (CHECK, UNIQUE, PK).
- Dropping or renaming columns — only after an explicit human decision and backup plan.

## Required Shape

Both `upgrade()` and `downgrade()` must reproduce the full intended table contract. For explicit
DDL, create `<table>_new`, copy an **explicit column list**, drop the old table, rename the new one,
recreate every index, and run `PRAGMA foreign_key_check`. For batch mode, provide enough explicit
table metadata (`copy_from` when needed) that Alembic does not guess at SQLite's unnamed objects.

Use revision `0002_rotation_decisions_account_cascade.py` as the focused FK-action rebuild example.
Revisions `0004`, `0005`, and `0008` demonstrate larger explicit rebuilds that preserve data while
changing settings ownership or constraints.

## Safety Checklist

- Both directions implemented: `downgrade()` restores the previous table shape.
- The copied column list is explicit; no `SELECT *`.
- Every index and unique constraint from the old table is recreated (partial `WHERE` clauses
  included).
- `PRAGMA foreign_key_check` runs before the revision is considered complete.
- The upgrade/downgrade/upgrade round-trip test proves no index or constraint is lost in the
  rebuild.
- Any column/table drop is called out in review with the backup requirement.

## Validation Commands

```sh
.venv\Scripts\python.exe -m scripts.checks.repo.migration_check
.venv\Scripts\python.exe -m scripts.data_ops.describe_db_schema
.venv\Scripts\python.exe -m scripts.checks.run_suite src/infrastructure/database --no-cov
```

Review the schema output to confirm the intended FK actions and that foreign-key columns used by
large cascades or routine filters have an index prefix.
