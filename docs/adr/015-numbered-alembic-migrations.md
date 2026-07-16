# ADR: Numbered Alembic migrations replace probe-based schema init

Type: adr
Status: Accepted
Created: 2026-07-15
Last Reviewed: 2026-07-15
Purpose: Records why schema management moved to a linear numbered Alembic revision history with verify-only runtime, and the key design choices within it.
Related: [DB Migration System](../reference/db-migration-system.md), [ADR 011 Strategy Catalog](011-strategy-catalog-and-parameter-ownership.md)

## Context

Schema was previously managed by a hand-rolled "probe" system: a canonical `SCHEMA_SQL` string,
additive `ColumnMigration` entries, and idempotent table-rebuild helpers, all applied
automatically inside `ensure_db()` on every connection. Two problems drove the change:

1. **Dual-source drift.** `SCHEMA_SQL` (for fresh databases) and the `ColumnMigration`/rebuild
   lists (for existing databases) were two hand-synced expressions of the same schema, with no
   generator keeping them consistent — a standing correctness hazard.
2. **Runtime auto-mutation.** Any process that opened the database could silently create or alter
   schema, so schema changes were never gated on developer review.

Alternatives considered: keep the probe system (rejected — the two problems are structural); ORM
models with Alembic autogenerate (rejected — the application has no SQLAlchemy model metadata and
we did not want to introduce one).

## Decision

Adopt a linear, numbered Alembic revision history under
`src/infrastructure/database/alembic/versions/` as the **sole** schema source of truth.

- **`0001` owns the complete current schema** rather than a separate init artifact. The revision
  chain is then the only place schema is defined: fresh setup is replay from base, and there is
  no second DDL artifact to hand-sync. `0001` is the *clean* schema (it omits the retired
  `strategy_param_sets` store and `book_strategy_assignments.param_set_id`).
- **Runtime is verify-only.** `ensure_db()` reads `alembic_version` with plain SQL and compares
  it to a checked-in `EXPECTED_HEAD_REVISION` constant; any mismatch fails fast pointing at the
  operator `status` command. Runtime never applies or downgrades migrations.
- **Alembic and SQLAlchemy are ops-only dependencies** (Option B): the application never imports
  them. Switching to runtime dependencies later would only replace the head constant with a
  script-directory lookup.
- **Revisions are immutable, self-contained, and manually authored** — no application imports, no
  autogeneration, both `upgrade()` and `downgrade()` implemented, structural changes via Alembic
  batch operations.
- **CI enforces one thing:** `EXPECTED_HEAD_REVISION` matches the migration directory head (the
  desync review cannot catch). Numeric ordering, linearity, and nonempty up/down are review
  discipline; Alembic itself refuses branched histories.
- **Operators** use `manage_db_migrations` (status/upgrade/downgrade/history); `backup_database()`
  is reused for pre-change backups.

Full mechanics live in [db-migration-system.md](../reference/db-migration-system.md).

## Consequences

- Fresh and migrated databases are structurally identical by construction; drift is not possible
  between a single source.
- Every schema change is a developer-authored, reviewed revision — nothing mutates schema at
  runtime.
- The one-time transition from the probe system (a schema comparator, `baseline`/`verify`
  commands, and a `reconcile_to_0001` script that shed probe-era leftovers) was used to adopt the
  deployed databases and then **removed**; it survives only in feature-branch git history.
- Replaying a growing chain is slower over time; mitigated by the per-session template-copy in
  the test helper, and Alembic history squashing if ever needed.
- Test databases are built at head via `tests/support/db_schema.py`; fixtures never hand-build
  schema.
