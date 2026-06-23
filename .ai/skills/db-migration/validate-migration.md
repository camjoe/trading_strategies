---
name: validate-migration
description: Validates a proposed ColumnMigration for correctness, safety, and idempotency before it is applied.
---

# Validate Migration

## Checklist

Run through each item in order. Any ❌ is a blocker — stop and report before proceeding.

### 1. `column_name` matches DDL
The `column_name` field must exactly match the column name in the `ddl` string.
```
ColumnMigration(column_name="foo", ddl="... ADD COLUMN foo ...")  ✅
ColumnMigration(column_name="foo", ddl="... ADD COLUMN bar ...")  ❌
```

### 2. `NOT NULL` has `DEFAULT`
Any `NOT NULL` column must have a `DEFAULT` value. Without it, SQLite rejects the `ALTER TABLE` on a populated table.

### 3. Not already in `SCHEMA_SQL`
If the column already exists in `schema.py`'s `SCHEMA_SQL`, a migration is not needed. Check before adding.

### 4. Appended to end of tuple
New entries must come after all existing entries. Do not insert mid-tuple.

### 5. `_ensure_column` guard is present
Verify that `migrations.py` uses `_ensure_column` (or equivalent idempotency guard) so re-running migrations on an already-upgraded DB is safe.

### 6. `post_sql` safety
If `post_sql` is not `None`, check whether it runs `UPDATE` or `DELETE` on existing rows. If so, flag for explicit human review — do not apply automatically.

## Validation command

```
python -m pytest tests/ -k "db or migration or schema" -x --no-cov
python -m mypy src/infrastructure/database/ --ignore-missing-imports
```

## Output

Return the checklist with ✅ / ❌ / N/A per item, plus a final verdict:

```
column_name matches DDL:      ✅
NOT NULL has DEFAULT:          ✅ / N/A
Not already in SCHEMA_SQL:    ✅
Appended to end of tuple:     ✅
Idempotency guard present:    ✅
post_sql safety:              ✅ / 🟡 Needs review / N/A

Verdict: ✅ Safe to apply / 🟡 Apply with caution / ❌ Block
```

## Repo references

- `src/infrastructure/database/migrations.py`
- `src/infrastructure/database/schema.py`
- `src/infrastructure/database/init.py`
