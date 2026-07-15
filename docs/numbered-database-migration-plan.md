# Numbered Alembic Migration System

Type: notes
Status: Active
Created: 2026-07-13
Last Reviewed: 2026-07-15
Purpose: Historical implementation plan (now delivered) for replacing probe-based schema initialization with a linear numbered Alembic revision history.

> **Historical.** This plan is fully implemented. The current system is documented in
> [db-migration-system.md](reference/db-migration-system.md); this page is kept for the design
> rationale. Note that the one-time transition tooling described below — the `baseline`/`verify`
> commands, the schema comparator, and the `reconcile_to_0001` script — was **removed after the
> transition completed** (all deployed databases reconciled and baselined, 2026-07-15). The
> `strategy_param_sets` removal was folded into revision `0001` rather than a later `0002`.

## Summary

Replace the current probe-based schema initialization with a linear Alembic revision history.
Fresh setup, existing-database migration, and data seeding remain three separate operator
processes.

Alembic is appropriate because it provides revision tracking and downgrade support, while its
batch operations implement SQLite's required copy-and-rebuild workflow for structural changes.

## Implementation Changes

- Add pinned Alembic and SQLAlchemy as dev/ops-only dependencies (decided — Option B) used by
  the schema-setup and migration commands, plus a repository-owned Alembic environment
  configured from the existing `TRADING_DB_PATH`/DB config resolution. The application never
  imports Alembic: `ensure_db()` reads `alembic_version` with plain SQL and compares it to a
  checked-in expected-head constant, and CI fails when that constant does not match the
  migration directory's head. Switching to runtime dependencies (Option A) later only replaces
  the constant with a script-directory lookup.
- Create immutable, numeric, single-head revisions:
  - `0001_current_schema` creates the complete current schema.
  - Rationale — the initial revision owns the full schema instead of a separate init-schema
    artifact so the revision chain is the *only* schema source: fresh setup is replay from
    base, `verify` can build any revision from scratch, and there is no second DDL artifact
    that must be hand-synced with every revision (the dual-source drift burden `SCHEMA_SQL`
    plus probe migrations carry today).
  - Its downgrade drops that schema in reverse dependency order.
  - `0001` is the clean current schema: it omits the retired `strategy_param_sets` store and the
    unused `book_strategy_assignments.param_set_id` column/FK (folded in during review rather
    than deferred to a `0002` — see Transition Preconditions).
- Make migration files self-contained:
  - No imports from changing application constants or configuration.
  - Seed/default values required by DDL are literal revision data.
  - Every revision implements both `upgrade()` and `downgrade()`.
  - Destructive downgrades restore the prior schema shape, not deleted data.
  - SQLite table changes use reviewed batch rebuilds with complete constraint/index preservation.

Remove `SCHEMA_SQL`, `ColumnMigration`, table-rebuild dispatch, and schema mutation from
`ensure_db()`. Migration history becomes the sole schema source of truth.

## Transition Preconditions

- Reality check (2026-07-15): the first baseline dry-run against the real dev database showed it
  does **not** match a fresh `0001` — the retired probe system never dropped tables/columns from
  existing databases, so it still carried `broker_orders` (219 rows), the empty
  `sleeve_*`/`rotation_episodes` tables, the `strategy_param_sets` store, and the unused
  `param_set_id` column. The comparator caught this before any stamp, which is exactly why
  `baseline` validation was kept.
- Decision (Package B): `0001` is the genuinely clean schema (no `strategy_param_sets`, no
  `param_set_id`), and each existing database is brought to it by the one-time reconciliation in
  `docs/pending-deploy-steps.md` Step 1 (drop the leftovers) before Step 2 baselines it. This
  absorbs what would have been a deferred `0002`; the accounts-table shrink becomes the next
  revision instead.
- Every real database that will be baselined must be dry-run first (reconcile → baseline →
  verify on a copy) so `0001` is confirmed to match it before merge freezes `0001`.
- Freeze other schema churn until `0001` and the baseline transition land. Follow-on rework
  (e.g. the accounts-table reduction) proceeds afterward as ordinary numbered revisions.

## Schema Comparison Semantics

`baseline` and `verify` share one normalized schema comparator; "matches the `0001` schema"
always means equality under these rules, never byte-identical DDL:

- Compare tables, columns, indexes, foreign keys, unique constraints, and check constraints as
  sets — physical column order is ignored, because databases built additively via
  `ALTER TABLE ADD COLUMN` order columns differently than a fresh `CREATE TABLE`.
- Normalize whitespace, identifier quoting, keyword case, and literal formatting in default and
  check expressions before comparing.
- Ignore SQLite internals: `sqlite_sequence`, auto-generated `sqlite_autoindex_*` indexes, and
  the `alembic_version` table itself.
- Known drift accommodation — `accounts.rotation_overlay_watchlist`: its `DEFAULT` literal is a
  JSON ticker-list blob frozen per database at the moment the column migration ran, so deployed
  databases can legitimately disagree with each other and with `0001`. The comparator requires
  the column and the presence of a default but does not compare that default's value. Revision
  `0001` freezes one literal snapshot for fresh databases.
- Baseline mismatch output names the differing table, column, index, FK, or check so the
  operator can diagnose without diffing dumps by hand.

## Operator Interfaces

Provide two distinct workflows (revised during review: fresh setup folded into `upgrade`
instead of a separate command).

### Schema migrations

```text
python -m scripts.data_ops.manage_db_migrations <command>
```

Commands:

- `status`: show database revision, repository head, and pending revisions.
- `upgrade [revision]`: default to `head`. Creates a missing or empty configured database at the
  target (fresh setup, no seeding); creates a timestamped backup before changing a nonempty one;
  refuses a populated, unversioned database and directs the operator to baseline it.
- `downgrade <revision|-1>`: require an explicit target and create a backup first.
- `baseline`: validate an unversioned database against the `0001` schema using the shared
  comparator (see Schema Comparison Semantics), then stamp it without replaying DDL.
- `verify`: compare revision state and schema against a temporary database built at the same
  revision, using the same comparator as `baseline`.
- `history`: display the ordered revision chain.

### Data seeding

Keep the following command separate and idempotent:

```text
python -m trading.interfaces.runtime.data_ops.seed_clean_schema
```

It must require a database already migrated to `head`.

## Runtime and Deployment Safety

- `ensure_db()` opens the SQLite connection and verifies that its Alembic revision equals the
  single repository head (via the checked-in expected-head constant — see Implementation
  Changes).
- Missing, unversioned, outdated, newer, or branched databases fail before application queries
  or jobs run, with one error pointing at the `status` command, which owns the diagnosis
  (revised during review: runtime does not classify states itself).
- Runtime startup never applies or downgrades migrations.
- Production deployment becomes: stop jobs, back up, install dependencies, run migration `status`,
  run `upgrade`, run `verify`, then restart and perform health checks.
- Existing environments transition once with `baseline`; schema mismatches refuse stamping without
  changing the database.
- CI enforces one thing: `EXPECTED_HEAD_REVISION` matches the migration directory head (revised
  during review — numeric ordering, linearity, immutable ancestry, and nonempty
  upgrade/downgrade are developer review discipline; Alembic itself refuses branched histories).
- Update architecture guidance, the DB migration reference, deployment runbook, maps, schema
  inspection tooling, `docs/pending-deploy-steps.md`, and the repository `db-migration` skill to
  use the new workflow.

## Test Plan

### Test fixture migration

This is the largest code-churn item in the plan. Today every fixture gets its schema implicitly
because `ensure_db()` creates it; once `ensure_db()` only verifies, that stops working for
`tests/conftest.py` and roughly thirty other files that call `ensure_db()`/`init_schema()`.

- Provide a shared test-support helper (e.g. `build_db_at_head()`) that runs the Alembic chain
  against the injected backend's database and stamps it at `head`.
- Keep per-test cost flat as revisions accumulate: build the head schema once per session into a
  template database file and copy it per test, extending the existing seed-then-copy pattern in
  `tests/conftest.py`, rather than replaying the migration chain for every test.
- Migrate existing fixtures to the helper; direct `init_schema()` calls are removed with the
  probe system.

### Behavior coverage

- `upgrade` on a missing/empty database reaches `head`, produces the expected current schema,
  and leaves application data unseeded.
- `upgrade` refuses populated, unversioned databases rather than silently stamping them.
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

## Decided Wiring

- Home (decided): `src/infrastructure/database/alembic/` (`env.py`, `versions/`).
  `scripts.checks.repo.layer_check` treats migration files as self-contained by design — no
  application imports allowed, enforcing what this plan already mandates.
- The migration runner and test helper hand Alembic a live connection from the active
  `DatabaseBackend` (Alembic's `connectable`/`connection` mode) rather than a URL, so
  `set_backend()` injection and in-memory databases keep working.
- Pre-`upgrade`/`downgrade` backups reuse `backup_database()` from
  `trading.interfaces.runtime.data_ops.admin` (decided) rather than duplicating backup logic.

## Open Decisions

- `scripts.data_ops.describe_db_schema --source code` and the `db_schema_check` docs drift check
  currently read `SCHEMA_SQL`; the working proposal is to re-point them at a temporary database
  built at `head`, but the exact approach is decided when that work comes up.

## Assumptions

- All known deployed databases have been opened with current code, so they carry the FK cascade
  rebuilds and all additive column migrations and match revision `0001` under the shared
  comparator (see Transition Preconditions).
- Migration revisions are manually authored and reviewed; ORM autogeneration is not introduced
  because the application has no SQLAlchemy model metadata.
- Downgrades guarantee schema reversal only. Backups remain the recovery mechanism for deleted rows
  or column values.
- Schema setup, migration execution, and seeding remain intentionally separate commands.

## Reference

- [Alembic SQLite batch migrations](https://alembic.sqlalchemy.org/en/latest/batch.html)
