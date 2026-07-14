# Numbered Alembic Migration System

## Summary

Replace the current probe-based schema initialization with a linear Alembic revision history.
Fresh setup, existing-database migration, and data seeding remain three separate operator
processes.

Alembic is appropriate because it provides revision tracking and downgrade support, while its
batch operations implement SQLite's required copy-and-rebuild workflow for structural changes.

## Implementation Changes

- Add pinned Alembic and SQLAlchemy runtime dependencies and a repository-owned Alembic
  environment configured from the existing `TRADING_DB_PATH`/DB config resolution.
- Create immutable, numeric, single-head revisions:
  - `0001_current_schema` creates the complete current schema.
  - Its downgrade drops that schema in reverse dependency order.
  - The still-pending `strategy_param_sets` removal remains unimplemented and becomes a later
    revision, likely `0002`.
- Make migration files self-contained:
  - No imports from changing application constants or configuration.
  - Seed/default values required by DDL are literal revision data.
  - Every revision implements both `upgrade()` and `downgrade()`.
  - Destructive downgrades restore the prior schema shape, not deleted data.
  - SQLite table changes use reviewed batch rebuilds with complete constraint/index preservation.

Remove `SCHEMA_SQL`, `ColumnMigration`, table-rebuild dispatch, and schema mutation from
`ensure_db()`. Migration history becomes the sole schema source of truth.

## Operator Interfaces

Provide three distinct workflows.

### Fresh schema setup

```text
python -m scripts.data_ops.setup_db_schema
```

- Creates a missing or empty configured database.
- Applies revisions from base through `head`.
- Refuses a populated, unversioned database and directs the operator to baseline it.
- Does not seed application data.

### Schema migrations

```text
python -m scripts.data_ops.manage_db_migrations <command>
```

Commands:

- `status`: show database revision, repository head, and pending revisions.
- `upgrade [revision]`: default to `head`; create a timestamped backup before changing a nonempty
  database.
- `downgrade <revision|-1>`: require an explicit target and create a backup first.
- `baseline`: validate an unversioned database against the semantic `0001` schema, then stamp it
  without replaying DDL.
- `verify`: compare revision state and normalized tables, columns, indexes, foreign keys, and checks
  against a temporary database built at the same revision.
- `history`: display the ordered revision chain.

### Data seeding

Keep the following command separate and idempotent:

```text
python -m trading.interfaces.runtime.data_ops.seed_clean_schema
```

It must require a database already migrated to `head`.

## Runtime and Deployment Safety

- `ensure_db()` opens the SQLite connection and verifies that its Alembic revision equals the
  single repository head.
- Missing, unversioned, outdated, newer, branched, or structurally invalid databases fail before
  application queries or jobs run, with the exact remediation command.
- Runtime startup never applies or downgrades migrations.
- Production deployment becomes: stop jobs, back up, install dependencies, run migration `status`,
  run `upgrade`, run `verify`, then restart and perform health checks.
- Existing environments transition once with `baseline`; schema mismatches refuse stamping without
  changing the database.
- CI enforces numeric ordering, one linear head, immutable ancestry, and nonempty upgrade/downgrade
  functions.
- Update architecture guidance, the DB migration reference, deployment runbook, maps, schema
  inspection tooling, and the repository `db-migration` skill to use the new workflow.

## Test Plan

- Fresh setup reaches `head`, produces the expected current schema, and leaves application data
  unseeded.
- Setup is idempotently rejected for populated/existing databases rather than silently stamping
  them.
- Baseline succeeds only for the exact current semantic schema and leaves user data unchanged.
- Baseline mismatch reports the differing table/column/index/FK and does not create
  `alembic_version`.
- Upgrade applies revisions in order; repeated upgrade at `head` is a no-op.
- Every revision can upgrade, downgrade one step, and upgrade again on representative data.
- Lossy downgrade restores schema shape while tests document that backup restore is required for
  discarded values.
- Failed migrations do not advance the recorded revision and report the automatic backup path.
- Runtime connection tests cover missing, unversioned, behind, at-head, ahead, drifted, and
  multiple-head states.
- `verify` detects manual schema drift even when `alembic_version` says the database is current.
- Existing database, repository, web, CLI, and runtime suites run against databases created through
  Alembic rather than `init_schema()`.

## Assumptions

- All known deployed databases currently match the schema represented by revision `0001`.
- Migration revisions are manually authored and reviewed; ORM autogeneration is not introduced
  because the application has no SQLAlchemy model metadata.
- Downgrades guarantee schema reversal only. Backups remain the recovery mechanism for deleted rows
  or column values.
- Schema setup, migration execution, and seeding remain intentionally separate commands.

## Reference

- [Alembic SQLite batch migrations](https://alembic.sqlalchemy.org/en/latest/batch.html)
