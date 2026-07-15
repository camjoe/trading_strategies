---
name: validate-migration
description: Validates a proposed Alembic revision for correctness, safety, and reversibility before it is applied.
---

# Validate Migration

## Checklist

Run through each item in order. Any ❌ is a blocker — stop and report before proceeding.

### 1. Chain integrity
`python -m scripts.checks.repo.migration_check` passes: 4-digit numeric id, single linear head,
`down_revision` points at the previous head, `EXPECTED_HEAD_REVISION` bumped in the same change.

### 2. Self-contained
No application imports; every value the DDL needs is a literal in the file.

### 3. `NOT NULL` has `DEFAULT`
Any `NOT NULL` column added to a populated table must carry a `DEFAULT`, or SQLite rejects the
ALTER at upgrade time.

### 4. `downgrade()` is real
It restores the prior schema shape (not a `pass`), and lossy downgrades are called out —
backups, not downgrades, recover discarded data.

### 5. Structural changes use batch operations
FK-action, constraint, and column-drop changes go through `op.batch_alter_table` with indexes
and constraints preserved — see [sqlite-table-rebuild.md](sqlite-table-rebuild.md).

### 6. Data-mutation safety
If the revision runs `UPDATE`/`DELETE` on existing rows, flag for explicit human review — do not
apply automatically.

### 7. Round-trip proven
Upgrade → downgrade one step → upgrade again succeeds on a representative database (the
migration-runner test suite covers this pattern; extend it for the new revision).

## Validation commands

```
python -m scripts.checks.repo.migration_check
python -m scripts.checks.run_suite src/infrastructure/database tests/scripts/test_manage_db_migrations.py --no-cov
python -m scripts.checks.python.mypy_check
```

## Output

Return the checklist with ✅ / ❌ / N/A per item, plus a final verdict:

```
Chain integrity:            ✅
Self-contained:             ✅
NOT NULL has DEFAULT:       ✅ / N/A
downgrade() is real:        ✅
Batch ops for structure:    ✅ / N/A
Data-mutation safety:       ✅ / 🟡 Needs review / N/A
Round-trip proven:          ✅

Verdict: ✅ Safe to apply / 🟡 Apply with caution / ❌ Block
```

## Repo references

- `src/infrastructure/database/alembic/versions/`
- `scripts/checks/repo/migration_check.py`
- `docs/reference/db-migration-system.md`
