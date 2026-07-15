# Architecture Notes: Database Migration System

Type: notes
Status: Active
Created: 2026-03-31
Last Reviewed: 2026-07-14
Purpose: Reference for the numbered Alembic migration system — key files, operator commands, revision-authoring rules, and runtime verification.
Related: [Numbered Migration Plan](../numbered-database-migration-plan.md), [Python Style](../conventions/python-style.md), [Architecture Conventions](../architecture/architecture-conventions.md)

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
| `src/infrastructure/database/migration_runner.py` | Programmatic runner: `upgrade`/`downgrade`/`stamp`, `repository_head()`, `revision_chain()`, `build_reference_connection()` — ops-only |
| `src/infrastructure/database/schema_version.py` | `EXPECTED_HEAD_REVISION` constant + plain-SQL `read_database_revisions()` (runtime-safe) |
| `src/infrastructure/database/schema_compare.py` | Normalized schema comparator shared by `baseline` and `verify` |
| `src/infrastructure/database/init.py` | `ensure_db()` (verify-only) and `db_session()` |
| `src/infrastructure/database/backend.py` | `DatabaseBackend` ABC, `SQLiteBackend`, `get_backend()` / `set_backend()` |
| `src/infrastructure/database/config.py` | DB path resolution: env var → config file → default `local/paper_trading.db` |
| `scripts/data_ops/manage_db_migrations.py` | Lifecycle command: status/upgrade/downgrade/baseline/verify/history |
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
| `baseline` | One-time adoption of a pre-Alembic database: validates it against the `0001` schema with the shared comparator, then stamps `0001` without running DDL. Mismatches name the differing object and nothing is stamped. |
| `verify` | Compares the database against a temporary reference built at the database's own revision — catches manual drift even when `alembic_version` claims current. |
| `history` | Ordered revision chain with the current revision marked. |

### Runtime verification

`ensure_db()` fails fast (before any application query) whenever the database's recorded revision
is not exactly the expected head — missing, unversioned, behind, ahead, and branched databases all
raise the same `SchemaVersionError` pointing at `manage_db_migrations status`, which owns the
diagnosis. The expected head comes from `schema_version.EXPECTED_HEAD_REVISION`; the
`migration_check` repo check fails CI when that constant does not match the migration directory.

---

## Schema Comparison Semantics

`baseline` and `verify` share one normalized comparator (`schema_compare.py`). "Matches revision
X" means equality under these rules, never byte-identical DDL:

- Tables, columns, FKs (with actions), unique/PK constraints, CHECK clauses, and named indexes
  compared as **sets** — physical column order is ignored (ALTER-built legacy databases order
  columns differently than fresh CREATEs).
- Whitespace and `IF NOT EXISTS` normalized out of compared SQL.
- SQLite internals (`sqlite_*`) and `alembic_version` itself are ignored.
- `accounts.rotation_overlay_watchlist`: the DEFAULT literal was frozen per database when the
  legacy probe migration ran, so its **value** is not compared — only its presence.

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
7. Run `python -m scripts.checks.repo.migration_check` and the database test suites.

For task-oriented guidance (risk estimation, validation, rollback planning) use the
`db-migration` skill (`.ai/skills/db-migration/`).

---

## Tests

- Runtime states (missing/empty, unversioned, behind, at-head, ahead, branched):
  `tests/src/infrastructure/database/test_db.py`
- Runner + revision integrity (round-trips, FK actions, no-op at head):
  `tests/src/infrastructure/database/test_migration_runner.py`
- Comparator semantics: `tests/src/infrastructure/database/test_schema_compare.py`
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
2. `db_path` value in `local/db_config.json` (or `TRADING_DB_CONFIG` env var path)
3. Default: `local/paper_trading.db`

If `db_path` in the config file is relative, it is resolved from the repository root. All paths
use `pathlib` — never hardcode slash direction.

---

## Backup System

Backup logic lives in `src/trading/interfaces/runtime/data_ops/admin.py`
(`backup_database(destination=None) -> Path`, default destination
`local/db_backups/<db_stem>_<YYYYMMDD_HHMMSS>.db`). `manage_db_migrations upgrade`/`downgrade`
call it automatically before changing a database. Backups remain the recovery mechanism for data
discarded by lossy downgrades.

---

## Relevant Architecture Conventions

- Schema and migration logic → `src/infrastructure/database/` only.
- Operator data-ops (backup, export, delete) → `src/trading/interfaces/runtime/data_ops/`.
- Migration revisions are exempt from normal layering by design — they import nothing from the
  application.
- SQL stays in repositories, not in services or interfaces.
- See `docs/architecture/architecture-conventions.md` for the full dependency-direction rules.
