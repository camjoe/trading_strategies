# Architecture Notes: Database Migration System

Type: notes
Status: Active
Created: 2026-03-31
Last Reviewed: 2026-07-17
Purpose: Reference for the numbered Alembic migration system — key files, operator commands, revision-authoring rules, and runtime verification.
Related: [ADR 015 Numbered Alembic Migrations](../adr/015-numbered-alembic-migrations.md), [Python Style](../conventions/python-style.md), [Architecture Conventions](../architecture/architecture-conventions.md)

---

## Overview

Schema evolution is managed by a **linear, numbered Alembic revision history** under
`src/infrastructure/database/alembic/versions/`. The migration history is the sole schema source
of truth: fresh databases are created by replaying revisions base → head, and existing databases
move between revisions with the operator commands below.

Runtime never migrates. `ensure_db()` opens the connection and verifies (with plain SQL) that the
database's `alembic_version` equals the expected head; any other state raises
`SchemaVersionError` with the exact remediation command. Alembic and SQLAlchemy are **ops-only
dependencies** (`requirements-dev.txt`) — application code never imports them.

The previous probe-based system (`SCHEMA_SQL` + `ColumnMigration` + table rebuilds, applied
automatically at startup) is retired; revision `0001` reproduces its final schema exactly.

---

## Key Files

| File | Role |
|------|------|
| `src/infrastructure/database/alembic/versions/` | Immutable numbered revisions (`0001_current_schema.py`, …) |
| `src/infrastructure/database/alembic/env.py` | Repository-owned Alembic environment (connection-mode only) |
| `src/infrastructure/database/migration_runner.py` | Programmatic runner: `upgrade`/`downgrade`, `repository_head()`, `revision_chain()`, `build_reference_connection()` — ops-only |
| `src/infrastructure/database/schema_version.py` | `EXPECTED_HEAD_REVISION` constant + plain-SQL `read_database_revisions()` (runtime-safe) |
| `src/infrastructure/database/connection.py` | `ensure_db()` (verify-only) and `db_session()` |
| `src/infrastructure/database/backend.py` | `DatabaseBackend` ABC, `SQLiteBackend`, `get_backend()` / `set_backend()` |
| `src/infrastructure/database/config.py` | DB path resolution: env var → config file → default `local/paper_trading.db` |
| `scripts/data_ops/manage_db_migrations.py` | Lifecycle command: status/upgrade/downgrade/history |
| `scripts/checks/repo/migration_check.py` | CI gate: `EXPECTED_HEAD_REVISION` matches the migration directory head |
| `src/trading/interfaces/runtime/data_ops/admin.py` | `backup_database()`, reused for pre-upgrade/downgrade backups |

For a readable schema snapshot, run `python -m scripts.data_ops.describe_db_schema` (builds the
code-defined schema from the migration chain) or `--source live` for the configured database.

---

## Operator Commands

```text
python -m scripts.data_ops.manage_db_migrations <command>
```

| Command | Behavior |
|---|---|
| `status` | Database revision, repository head, pending revisions, state classification + remediation. Exit 0 only at head. |
| `upgrade [revision]` | Apply revisions (default `head`). Creates a missing/empty database at head (fresh setup); backs up an existing database first; no-op without backup when already at target. Never seeds data — seeding stays `python -m trading.interfaces.runtime.data_ops.seed_clean_schema`. |
| `downgrade <revision\|-1>` | Revert to an explicit target. Backs up first. Restores schema *shape* only — restore the backup to recover data. |
| `history` | Ordered revision chain with the current revision marked. |

> The one-time `baseline`/`verify` commands, the `reconcile_to_0001` script, and the
> `schema_compare` comparator were removed after the Alembic transition completed (all deployed
> databases baselined). See git history if adopting another pre-Alembic database.

### Runtime verification

`ensure_db()` fails fast (before any application query) whenever the database's recorded revision
is not exactly the expected head — missing, unversioned, behind, ahead, and branched databases all
raise the same `SchemaVersionError` pointing at `manage_db_migrations status`, which owns the
diagnosis. The expected head comes from `schema_version.EXPECTED_HEAD_REVISION`; the
`migration_check` repo check fails CI when that constant does not match the migration directory.

---

## Authoring a New Revision

1. Create the file with an explicit numeric id (next in sequence), named `000N_<slug>.py` in
   `alembic/versions/`. Copy the previous revision's header shape (`revision`, `down_revision`,
   `upgrade()`, `downgrade()`); there is no repo `alembic.ini`, so plain `alembic revision` CLI
   calls are not wired up — hand-authoring from the template is the expected path.
2. Revisions are **immutable and self-contained** (PR-review discipline — CI only enforces the
   head constant):
   - No imports from application code — only `alembic`/`sqlalchemy`/stdlib.
   - Values required by DDL are literals frozen at authoring time.
   - Both `upgrade()` and `downgrade()` implemented and nonempty.
   - Destructive downgrades restore the prior schema *shape*, not deleted data.
3. SQLite structural changes (FK actions, constraint changes, column drops) use Alembic
   **batch operations** (`op.batch_alter_table`) — Alembic implements SQLite's
   copy-and-rebuild workflow. See <https://alembic.sqlalchemy.org/en/latest/batch.html>.
4. Update `schema_version.EXPECTED_HEAD_REVISION` **in the same commit** — CI fails otherwise.
5. Never edit or reorder an applied revision; follow-up fixes are new revisions.
6. Safety rules that carry over from the previous system:
   - `NOT NULL` columns on populated tables require a `DEFAULT`.
   - Data-mutating statements (`UPDATE`/`DELETE`) in a revision require explicit human review.
   - Never set `live_trading_enabled = 1` or point broker columns at live endpoints
     (Live Trading Safety Guard, enforced by `live_safety_check`).
7. For any table rebuild, run `PRAGMA foreign_key_check` and test the intended `ON DELETE` actions.
   Verify that every foreign-key column used by a large cascade or routine filter is covered by an
   index prefix; this index-coverage review is manual until a deterministic repository check exists.
8. After any schema change, regenerate `docs/reference/database-diagram-viewer.html`, synchronize
   `docs/reference/db-schema.md`, and run `python -m scripts.checks.docs.readme_check`.
9. Run `python -m scripts.checks.repo.migration_check` and the database test suites.

For task-oriented guidance (risk estimation, validation, rollback planning) use the
`db-migration` skill (`.ai/skills/db-migration/`).

---

## Tests

- Runtime states (missing/empty, unversioned, behind, at-head, ahead, branched):
  `tests/src/infrastructure/database/test_connection.py`
- Runner + revision integrity (round-trips, FK actions, no-op at head):
  `tests/src/infrastructure/database/test_migration_runner.py`
- Operator commands: `tests/scripts/test_manage_db_migrations.py`
- Head-constant check: `tests/scripts/test_migration_check.py`

Test databases come from `tests/support/db_schema.py`: `build_db_at_head(path)` /
`memory_db_at_head()`. The migration chain is replayed once per process into a template; every
test database is a file copy, so per-test cost stays flat as revisions accumulate. Do not create
schemas by hand in fixtures.

---

## Database Path Resolution

`src/infrastructure/database/config.get_db_path()` resolves in this order:

1. `TRADING_DB_PATH` environment variable
2. Default: `local/paper_trading.db`

To run against a disposable database, use `scripts/launch_sandbox.py` or `scripts/launch_demo.py`
— both set `TRADING_DB_PATH` for you — or export it yourself for the shell session.

A third source, `db_path` in `local/db_config.json`, was removed: the env var already covers the
temp-database case, and a config file persists across terminals, so a stale entry silently
redirects every later command (including `upgrade` and `delete-account`) with nothing on screen to
say so. All paths use `pathlib` — never hardcode slash direction.

---

## Backup System

Backup logic lives in `src/trading/interfaces/runtime/data_ops/admin.py`
(`backup_database(destination=None) -> Path`, default destination
`local/db_backups/<db_stem>_<YYYYMMDD_HHMMSS>.db`). `manage_db_migrations upgrade`/`downgrade`
call it automatically before changing a database. Backups remain the recovery mechanism for data
discarded by lossy downgrades.

---

## Squash rollout for deployed databases

The migration chain `0001`–`0031` was squashed to a single `0001` baseline on 2026-09-12. The squash
changed the code, not any running database. An existing database is still stamped `0031` and fails
`ensure_db()` until it joins the new chain. The data path is **drop and reseed**; no
reconcile-and-stamp helper exists. Dev `local/paper_trading.db` is one such database. Confirm the
staging and prod row counts first.

**Before you drop, confirm the row counts.** `ledger`, `orders`, and `order_fills` are the
account-accounting source of truth; `AccountState` (cash, positions, realized P&L, `total_deposited`)
is derived by replaying them. Dev holds zero rows in all three, so the loss is free there. Staging and
prod may hold real rows. Every history, audit, research, and operational table is dropped and not
recreated. The pre-drop backup is the only recovery path.

Procedure per database:

1. Confirm the revision and row counts: `python -m scripts.data_ops.manage_db_migrations status`.
2. Back up the database file. The backup is the only recovery path for the dropped rows.
3. Drop the file, then `python -m scripts.data_ops.manage_db_migrations upgrade` to build a fresh
   database at the new `0001`.
4. Recreate the strategy catalog and default books:
   `python -m trading.interfaces.runtime.data_ops.seed_clean_schema`.
5. Recreate accounts and their books through the account-create path (account profiles / CLI). No
   seeder reproduces the real accounts — the `sandbox`/`demo` fixture profiles build synthetic
   accounts for a test bed, not the live configuration.
6. Set `live_trading_enabled = 1` by hand only where an account is meant to trade live. The Live
   Trading Safety Guard forbids any seed or script from setting it.

### Catalog recreation

| Table | Recreation path |
|---|---|
| `accounts` | Manual re-entry through the account-create path (profiles / CLI). No seeder creates real accounts. |
| `books` | Created with each account; `ensure_default_books` repairs a missing default book for an existing account only. |
| `book_rotation_settings` | Created with each book; `seed_clean_schema` writes the disabled-rotation defaults. |
| `strategies` | `seed_strategy_catalog` rebuilds one row per code primitive. Nothing is tuned, so no export is needed. Recreate the alias rows by hand only if you still want the aliases. |
| `global_settings` | Optional operator overrides; when the row is absent the system uses code defaults. Set values through the settings CLI if wanted. |

### Reseed caveats

- **Do not add a synthetic opening deposit.** `create_account` seeds `initial_cash` and bootstraps
  the default book's `current_cash` from it; it writes no opening `deposit` ledger row.
  `load_account_state` computes `total_deposited` only from ledger `deposit`/`withdrawal` entries, so
  it reports `0.0` for an account that was never manually funded. Cash is still correct, because the
  replay starts from `initial_cash`. A synthetic opening deposit at reseed double-counts the opening
  balance.
- **Seed through the real writers.** A table the seeder cannot populate through application code is a
  finding about the data model, not a reason to hand-write the `INSERT`. The `sandbox` fixture profile
  is the checked-in seed definition; a coverage check fails when a new table is neither seeded nor
  listed in `KNOWN_EMPTY_SANDBOX_TABLES`.

## Relevant Architecture Conventions

- Schema and migration logic → `src/infrastructure/database/` only.
- Operator data-ops (backup, export, delete) → `src/trading/interfaces/runtime/data_ops/`.
- Migration revisions are exempt from normal layering by design — they import nothing from the
  application.
- SQL stays in repositories, not in services or interfaces.
- See `docs/architecture/architecture-conventions.md` for the full dependency-direction rules.
