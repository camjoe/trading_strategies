# Database Infrastructure

## Purpose

DB connection, configuration, and the schema-migration machinery. Imported only by
`src/trading/repositories/` (and the documented `runtime_loader.py` exception) — see
`docs/maps/infrastructure-map.md`.

## Golden rules

- **The schema lives in `alembic/versions/`.** The numbered Alembic revision chain is the *sole*
  source of truth for the schema — there is no `SCHEMA_SQL` mirror. Revision `0001` holds the full
  current schema; later revisions are deltas. Change the schema only by adding a new immutable
  revision (use the `db-migration` skill).
- **Runtime never migrates.** `ensure_db()` (in `connection.py`) opens a connection and *verifies* that
  the database's recorded revision equals `schema_version.EXPECTED_HEAD_REVISION`, raising
  `SchemaVersionError` otherwise. It never creates or alters schema. Operators apply migrations
  with `python -m scripts.data_ops.manage_db_migrations`.
- **Alembic and SQLAlchemy are ops-only.** Application code must not import them. `migration_runner.py`
  is the single module that does, and it is imported only by operator scripts and tests — never by
  runtime code. Runtime learns the expected head from the plain-Python `schema_version.py`.

## Modules

| Module | Role |
|---|---|
| `connection.py` | `ensure_db()` (verify-only connection gate) and `db_session()` |
| `backend.py` | `DatabaseBackend` ABC, `SQLiteBackend`, `get_backend()` / `set_backend()` |
| `config.py` | DB path resolution: `TRADING_DB_PATH` → config file → `local/paper_trading.db` |
| `schema_version.py` | `EXPECTED_HEAD_REVISION` constant + plain-SQL revision reader (runtime-safe) |
| `migration_runner.py` | Programmatic Alembic runner (upgrade/downgrade, reference builds) — **ops-only** |
| `sql_helpers.py` | Low-level SQL utilities (`in_placeholders`, coercion helpers) |
| `alembic/env.py` | Repository-owned Alembic environment (connection-mode only) |
| `alembic/versions/` | Immutable numbered revisions (`0001_current_schema.py`, …) |

## Commands

- Manage schema migrations: `python -m scripts.data_ops.manage_db_migrations`
- Inspect the configured database schema: `python -m scripts.data_ops.describe_db_schema`
- Inspect the live database schema: `python -m scripts.data_ops.describe_db_schema --source live`

## Where to go next

- How the migration system works, operator commands, and authoring rules:
  `docs/reference/db-migration-system.md`
- Why it is built this way (decision record): `docs/adr/015-numbered-alembic-migrations.md`
- Current table inventory: `docs/reference/db-schema.md` or `python -m scripts.data_ops.describe_db_schema`
