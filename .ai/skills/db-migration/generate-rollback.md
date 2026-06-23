---
name: generate-rollback
description: Generates a rollback strategy for a SQLite schema migration, accounting for SQLite's limited ALTER TABLE support.
---

# Generate Rollback

## SQLite constraints

SQLite does not support `DROP COLUMN` in versions before 3.35.0. Most deployments should be assumed to have an older SQLite unless confirmed otherwise. Rolling back a column addition therefore depends on the version and on whether data was written to the new column.

## Rollback strategies by case

### Case 1: Column added, no data written yet
If the migration was applied but the column is empty (no `post_sql` backfill, no production writes):

**Strategy:** Stop using the column in application code, then recreate the table without it at next opportunity. Immediate rollback is not required.

```sql
-- No immediate SQL needed. Stop reading/writing the column in code.
-- Mark it deprecated; clean up at next scheduled maintenance.
```

### Case 2: Column added with backfill (`post_sql` ran)
Data has been written to the new column. Rolling back means table recreation.

**Strategy:** Create a new table with the old schema, copy data excluding the new column, drop the original, rename the new table.

```sql
-- WARNING: Run inside a transaction. Take a backup first.
BEGIN TRANSACTION;
CREATE TABLE <table>_old AS SELECT <original_columns> FROM <table>;
DROP TABLE <table>;
ALTER TABLE <table>_old RENAME TO <table>;
COMMIT;
```

**Backup required** before executing any table recreation rollback.

### Case 3: SQLite >= 3.35.0 available
```sql
ALTER TABLE <table> DROP COLUMN <column>;
```
Verify SQLite version first: `python -c "import sqlite3; print(sqlite3.sqlite_version)"`

## Before generating a rollback script

1. Confirm whether any production data has been written to the new column.
2. Confirm the SQLite version in the target environment.
3. Confirm a backup exists and is verified.
4. Identify all code paths that read or write the column — they must be reverted before or alongside the schema rollback.

## Output

Provide:
1. The rollback strategy (which case applies)
2. The rollback SQL (with transaction and backup warning if table recreation is needed)
3. The application code changes required (column references to remove)
4. The verification command to confirm the rollback succeeded

## Repo references

- `src/infrastructure/database/schema.py`
- `src/trading/interfaces/runtime/data_ops/` (backup tooling)
