---
name: create-migration
description: Creates a new ColumnMigration entry for the trading SQLite database following the additive-only migration pattern.
---

# Create Migration

## What to produce

A `ColumnMigration` entry ready to append to the migrations tuple in `src/infrastructure/database/migrations.py`.

## Workflow

1. **Identify the column** — name, type, nullability, default value.
2. **Write the DDL** — `ALTER TABLE <table> ADD COLUMN <name> <type> [NOT NULL] [DEFAULT <value>]`.
3. **Write the ColumnMigration entry**:
   ```python
   ColumnMigration(
       table_name="<table>",
       column_name="<name>",
       ddl="ALTER TABLE <table> ADD COLUMN <name> <type> DEFAULT <value>",
       post_sql=None,  # or a safe backfill if needed
   )
   ```
4. **Append to the tuple** — never insert mid-tuple.
5. **Verify `column_name` matches the column in `ddl`** exactly.
6. **Check `SCHEMA_SQL`** in `schema.py` — add the column there too so fresh installs include it.

## Rules

- `NOT NULL` without `DEFAULT` is a blocker — SQLite will reject it on existing tables.
- `post_sql` that runs `UPDATE` or `DELETE` on existing rows requires human review before applying.
- Do not use `DROP COLUMN` or `RENAME COLUMN` — these are destructive; use a separate steward review.

## Output

```python
# Append to COLUMN_MIGRATIONS in src/infrastructure/database/migrations.py
ColumnMigration(
    table_name="<table>",
    column_name="<column>",
    ddl="ALTER TABLE <table> ADD COLUMN <column> <type> DEFAULT <default>",
    post_sql=None,
),
```

Plus the matching line in `SCHEMA_SQL` in `schema.py`.

## Repo references

- `src/infrastructure/database/migrations.py`
- `src/infrastructure/database/schema.py`
