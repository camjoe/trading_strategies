---
name: create-migration
description: Authors a new numbered Alembic revision for the trading SQLite database.
---

# Create Migration

## What to produce

A new revision file in `src/infrastructure/database/alembic/versions/`, named
`000N_<slug>.py` where `000N` is the next number in the chain, plus the matching
`EXPECTED_HEAD_REVISION` bump in `src/infrastructure/database/schema_version.py`.

## Workflow

1. **Find the current head** — `python -m scripts.data_ops.manage_db_migrations history`, or read
   `EXPECTED_HEAD_REVISION`. The new revision is head + 1.
2. **Write the revision file** (copy the previous revision's header shape):
   ```python
   """<what this revision changes>.

   Revision ID: 000N
   Revises: 000M
   """

   from __future__ import annotations

   from alembic import op

   revision = "000N"
   down_revision = "000M"
   branch_labels = None
   depends_on = None


   def upgrade() -> None:
       op.execute("ALTER TABLE <table> ADD COLUMN <name> <type> NOT NULL DEFAULT <value>")


   def downgrade() -> None:
       # Restores schema shape; discarded values come back from backups, not downgrades.
       with op.batch_alter_table("<table>") as batch:
           batch.drop_column("<name>")
   ```
3. **Keep it self-contained** — no application imports; any value the DDL needs is a literal
   frozen in the file.
4. **Bump `EXPECTED_HEAD_REVISION`** to `"000N"` in the same commit.
5. **Validate** — `python -m scripts.checks.repo.migration_check`, then the database suites
   (`python -m scripts.checks.run_suite src/infrastructure/database --no-cov`).

## Rules

- `NOT NULL` without `DEFAULT` is a blocker on populated tables — SQLite rejects the ALTER.
- Structural changes (FK actions, constraints, drops) go through batch operations — see
  [sqlite-table-rebuild.md](sqlite-table-rebuild.md).
- `UPDATE`/`DELETE` of existing rows inside a revision requires human review before applying.
- Never edit an applied revision; a follow-up fix is a new revision.

## Repo references

- `src/infrastructure/database/alembic/versions/0001_current_schema.py` (canonical example)
- `src/infrastructure/database/schema_version.py`
- `docs/reference/db-migration-system.md`
