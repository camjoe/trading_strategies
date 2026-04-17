# Architecture Notes: Database Migration System

Status: Active reference  
Date: 2026-03-31  
Audience: Developers, DB Migration Steward bot, Code Review bot

---

## Overview

This project uses a **hand-rolled SQLite migration system** — there is no Alembic, Django migrations, or other migration framework. Schema evolution is managed in `trading/database/` via a `ColumnMigration` dataclass and is applied automatically at startup.

---

## Key Files

| File | Role |
|------|------|
| `trading/database/db.py` | Stable public facade for DB schema/migration helpers |
| `trading/database/db_common.py` | Shared DB path/type aliases and seeded overlay-watchlist defaults |
| `trading/database/db_schema.py` | Canonical table/index DDL and `SCHEMA_SQL` |
| `trading/database/db_migrations.py` | `ColumnMigration` dataclass and migration tuples |
| `trading/database/db_init.py` | `ensure_db()`, `init_schema()`, and column-guard helpers |
| `trading/database/db_backend.py` | `DatabaseBackend` ABC, `SQLiteBackend`, `get_backend()` / `set_backend()` |
| `trading/database/db_config.py` | DB path resolution: env var → config file → default `local/paper_trading.db` |
| `trading/interfaces/runtime/data_ops/admin.py` | `backup_database()`, CLI for backup and delete operations |
| `trading/interfaces/runtime/data_ops/csv_export.py` | CSV export for accounts and trades |

---

## Database Path Resolution

`trading/database/db_config.get_db_path()` resolves in this order:

1. `TRADING_DB_PATH` environment variable
2. `db_path` value in `local/db_config.json` (or `TRADING_DB_CONFIG` env var path)
3. Default: `local/paper_trading.db`

All paths use `pathlib` — never hardcode slash direction.

---

## Schema Initialization: `init_schema()`

Called from `ensure_db()` on every connection. The public import path remains
`trading.database.db`, while the implementation currently lives in
`trading/database/db_init.py`:

```python
def init_schema(conn: DBConnection) -> None:
    get_backend().run_script(conn, SCHEMA_SQL)           # 1. Create all tables
    for migration in ACCOUNT_MIGRATIONS:                  # 2. Apply account column migrations
        _ensure_column(conn, "accounts", migration)
    for migration in BACKTEST_RUN_MIGRATIONS:             # 3. Apply backtest_runs migrations
        _ensure_column(conn, "backtest_runs", migration)
    conn.commit()
```

**Safe to call on both fresh and migrated databases.** All DDL uses `IF NOT EXISTS` guards.

---

## Migration Mechanism: `ColumnMigration`

```python
@dataclass(frozen=True)
class ColumnMigration:
    column_name: str          # name of column being added (used as idempotency guard)
    ddl: str                  # ALTER TABLE ... ADD COLUMN ... statement
    post_sql: tuple[str, ...] = ()  # optional follow-up SQL (UPDATE, index creation, etc.)
```

`_ensure_column()` checks `PRAGMA table_info(<table>)` before executing the DDL:

```python
def _ensure_column(conn, table_name, migration):
    if migration.column_name in _column_names(conn, table_name):
        return  # already exists — skip silently (idempotent)
    conn.execute(migration.ddl)
    for stmt in migration.post_sql:
        conn.execute(stmt)
    conn.commit()
```

**The `column_name` field is the idempotency key** — it must exactly match the column name in `ddl`.

---

## Migration Tuples

```
ACCOUNT_MIGRATIONS     → applied to the `accounts` table
BACKTEST_RUN_MIGRATIONS → applied to the `backtest_runs` table
```

Both tuples are processed by `init_schema()`. Any new table requiring additive migrations must also be registered in `init_schema()`.

---

## Rules for Adding a New Column Migration

1. **Append only** — add new `ColumnMigration` entries at the end of the relevant tuple. Never insert in the middle (order is not critical for column guards, but middle-inserts cause confusion in code review).

2. **`column_name` must match `ddl`** — the string in `column_name` is compared against `PRAGMA table_info` column names. A mismatch causes silent skip or double-application.

3. **`NOT NULL` columns require a `DEFAULT`** — SQLite's `ALTER TABLE ADD COLUMN` rejects `NOT NULL` without a default value when rows already exist.
   ```python
   # ✅ Correct
   ColumnMigration("risk_policy", "ALTER TABLE accounts ADD COLUMN risk_policy TEXT NOT NULL DEFAULT 'none'")
   # 🔴 Wrong — will fail on non-empty table
   ColumnMigration("risk_policy", "ALTER TABLE accounts ADD COLUMN risk_policy TEXT NOT NULL")
   ```

4. **`post_sql` UPDATE statements** must be deliberate:
   - Targeted `UPDATE … WHERE …` is fine.
   - Full-table `UPDATE` (no WHERE) is acceptable but should be flagged in code review for confirmation.
   - `DELETE` in `post_sql` requires an explicit pre-backup before deployment.

5. **No destructive DDL** — `DROP COLUMN`, `DROP TABLE`, `RENAME COLUMN`, `TRUNCATE` are not permitted without an explicit human decision and a verified backup.

6. **Check `SCHEMA_SQL` first** — if the column is already in `CREATE TABLE IF NOT EXISTS`, adding a migration for it is dead code (the column guard will always skip it on fresh databases).

---

## Tables in `SCHEMA_SQL`

| Table | Purpose |
|-------|---------|
| `accounts` | Account profiles with strategy config, risk policy, and rotation settings |
| `trades` | Live trade records linked to accounts |
| `global_settings` | Singleton row for repo-wide platform policy such as runtime trade throttles |
| `equity_snapshots` | Daily/periodic equity snapshots per account |
| `backtest_runs` | Backtest run metadata |
| `backtest_trades` | Individual trades within a backtest run |
| `backtest_equity_snapshots` | Equity curve for a backtest run |

Indexes: `idx_trades_trade_time`, `idx_backtest_runs_account_id`, `idx_backtest_trades_run_id`, `idx_backtest_equity_run_id`

---

## Backup System

### Trading Database Backups

Backup logic lives in `trading/interfaces/runtime/data_ops/admin.py`:

```python
backup_database(destination=None) -> Path
```

- Default destination: `local/backups/<db_stem>_<YYYYMMDD_HHMMSS>.db`
- Custom destination: pass a directory path (file name auto-generated) or a full `.db` path.
- Uses `shutil.copy2` — preserves metadata.

**Backup-before-delete pattern** (implemented in `_cmd_delete_accounts`):
```bash
python -m trading.interfaces.runtime.data_ops.admin delete-accounts --backup-before --all --yes
```

The `--backup-before` flag calls `backup_database()` before `delete_accounts()`. Any future destructive data-ops flow should follow this same pattern.

### Project Manager DB Backups (separate concern)

The `tools/project_manager/` submodule manages its own backup system:
- Backup location: `tools/project_manager/db_backups/project_db_session_YYYY-MM-DD.json`
- Marker file: `tools/project_manager/db_backups/.session_backup_marker`
- `data/` and `db_backups/` are gitignored in the submodule — changes are local-only.

Do not mix trading DB backup logic with project_manager DB backups.

---

## DatabaseBackend Abstraction

`trading/database/db_backend.py` defines a `DatabaseBackend` ABC with three required methods:

| Method | Purpose |
|--------|---------|
| `open_connection()` | Return an open, configured DB connection |
| `run_script(conn, script)` | Execute a multi-statement SQL script (like `executescript`) |
| `get_table_columns(conn, table)` | Return the set of column names present in a table |

`SQLiteBackend` is the default. Swap it via `set_backend(custom_backend)` — used in tests to inject in-memory or fixture backends.

---

## Adding a New Table (not just a column)

If a new table is needed:

1. Add a `CREATE TABLE IF NOT EXISTS` DDL string to `db_schema.py`.
2. Add it to `SCHEMA_SQL`.
3. If it will need future column migrations, create a new migration tuple (e.g. `NEW_TABLE_MIGRATIONS`) and register it in `init_schema()`.
4. Add any performance indexes as `CREATE INDEX IF NOT EXISTS` in a companion `*_INDEXES_SQL` string.
5. Update this document.

---

## Testing Migrations

Key test patterns:
- Test `init_schema()` on a fresh in-memory SQLite backend: verify all tables and columns exist.
- Test `init_schema()` is idempotent: calling it twice on the same connection produces no errors.
- Test `_ensure_column()` with a pre-existing column: verify no duplicate-column error.
- Test `_ensure_column()` on a fresh table: verify column is added and `post_sql` runs.

Inject a custom backend via `set_backend(SQLiteBackend(db_path=Path(":memory:")))` for isolation.

---

## Relevant Architecture Conventions

- Schema init and migration logic → `trading/database/` only.
- Operator data-ops (backup, export, delete) → `trading/interfaces/runtime/data_ops/`.
- Do not call `init_schema()` from domain modules.
- SQL stays in repositories, not in services or interfaces.
- See `.github/BOT_ARCHITECTURE_CONVENTIONS.md` for the full dependency-direction rules.
