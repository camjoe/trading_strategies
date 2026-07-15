---
name: sqlite-table-rebuild
description: Shows the Alembic batch-operation pattern required when SQLite schema changes need table rebuilds, such as changing foreign-key ON DELETE actions or dropping columns.
---

# SQLite Table Rebuild (Alembic Batch Operations)

Use this reference when a schema change cannot be expressed as `ALTER TABLE ... ADD COLUMN`.
SQLite cannot alter FK actions, constraints, or primary keys in place; Alembic's **batch mode**
implements the required copy-and-rebuild workflow (create new table → copy rows → drop old →
rename), so revisions should not hand-roll it.

## When This Applies

- Changing `ON DELETE` / `ON UPDATE` behavior.
- Adding, changing, or removing table constraints (CHECK, UNIQUE, PK).
- Dropping or renaming columns — only after an explicit human decision and backup plan.

## Required Shape

Inside the revision's `upgrade()` (and mirrored in `downgrade()`):

```python
def upgrade() -> None:
    # copy_from lets batch mode rebuild without reflecting server defaults it
    # cannot infer; recreate="always" forces the rebuild even when SQLite could
    # theoretically ALTER in place.
    with op.batch_alter_table("order_fills", recreate="always") as batch:
        batch.drop_constraint("fk_order_fills_order_id", type_="foreignkey")
        batch.create_foreign_key(
            "fk_order_fills_order_id", "orders", ["order_id"], ["id"], ondelete="CASCADE"
        )
```

For complex rebuilds (unnamed constraints in legacy tables, partial indexes), `op.execute` with
explicit literal DDL following the classic pattern is acceptable — create `<table>_new`, copy an
**explicit column list**, drop, rename, recreate every index, then `PRAGMA foreign_key_check`.
Revision `0001` and the retired probe rebuilds (git history of
`src/infrastructure/database/migrations.py`) are the reference DDL shapes.

## Safety Checklist

- Both directions implemented: `downgrade()` restores the previous table shape.
- The copied column list is explicit; no `SELECT *`.
- Every index and unique constraint from the old table is recreated (partial `WHERE` clauses
  included).
- `PRAGMA foreign_key_check` runs before the revision is considered complete.
- Operators run `manage_db_migrations verify` after upgrading — the comparator will surface any
  index/constraint lost in the rebuild.
- Any column/table drop is called out in review with the backup requirement.

## Validation Commands

```sh
.venv\Scripts\python.exe -m scripts.checks.repo.migration_check
.venv\Scripts\python.exe -m scripts.data_ops.audit_foreign_keys --scope all
.venv\Scripts\python.exe -m scripts.checks.run_suite src/infrastructure/database --no-cov
```
