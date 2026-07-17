# Generate Rollback

## The two rollback mechanisms

1. **`downgrade()`** — restores the previous schema *shape*. Every revision must implement it,
   and `manage_db_migrations downgrade <revision|-1>` applies it. An existing database is backed up
   before an actual downgrade.
2. **Backup restore** — the only mechanism that recovers *data* discarded by a lossy revision
   (dropped columns/tables, destructive `UPDATE`s). `manage_db_migrations upgrade` creates a
   timestamped backup in `local/db_backups/` before changing an existing database; fresh creation
   and no-op targets are exceptions.

## Strategy by case

### Case 1: Additive revision, no data written to the new column yet
Run `.venv/Scripts/python.exe -m scripts.data_ops.manage_db_migrations downgrade -1`. Nothing is lost; the
downgrade drops the empty column via a batch rebuild.

### Case 2: Additive revision with backfill, or data already written
Downgrade drops the column *and its data*. Decide first whether the data matters:
- Data disposable → downgrade is sufficient.
- Data matters → restore the pre-upgrade backup instead, accepting the loss of rows written
  since the upgrade, or export the column before downgrading.

### Case 3: Destructive revision (column/table dropped by `upgrade()`)
`downgrade()` recreates the shape but the values are gone. Recovery is the pre-upgrade backup.
State this explicitly in the rollback plan.

## Before generating a rollback plan

1. Run `.venv/Scripts/python.exe -m scripts.data_ops.manage_db_migrations status` — confirm the
   database revision.
2. Confirm the pre-upgrade backup exists in `local/db_backups/` and note its timestamp.
3. Identify code paths that read/write the affected columns — application code must be reverted
   to the matching revision's expectations before or alongside the schema rollback.
4. Stop every database writer for the rollback window, including scheduler jobs, web services, and
   operator commands.

## Output

Provide:
1. Which case applies and the chosen mechanism (downgrade vs backup restore).
2. The exact downgrade command, or a backup-restore procedure that first verifies the resolved live
   database and backup paths. The repository has no dedicated restore command; do not invent one.
3. The application code changes required.
4. Verification: `manage_db_migrations status` shows the target revision, and
   `describe_db_schema --source live` reflects the expected shape.

## Repo references

- `scripts/data_ops/manage_db_migrations.py`
- `src/trading/interfaces/runtime/data_ops/admin.py` (backup tooling)
- `docs/reference/db-migration-system.md`
