from pathlib import Path

import pytest

from trading.database import db
from trading.database.db_backend import SQLiteBackend, get_backend, set_backend


@pytest.fixture
def backend_file(tmp_path: Path) -> Path:
    return tmp_path / "paper_trading.db"


@pytest.fixture
def sqlite_backend(backend_file: Path):
    original = get_backend()
    backend = SQLiteBackend(backend_file)
    set_backend(backend)
    try:
        yield backend
    finally:
        set_backend(original)


def test_ensure_db_creates_core_tables(sqlite_backend: SQLiteBackend) -> None:
    conn = db.ensure_db()
    try:
        table_rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name ASC"
        ).fetchall()
        names = {str(row["name"]) for row in table_rows}

        assert "accounts" in names
        assert "trades" in names
        assert "equity_snapshots" in names
        assert "backtest_runs" in names
        assert "backtest_trades" in names
        assert "backtest_equity_snapshots" in names
    finally:
        conn.close()


def test_init_schema_migrates_legacy_accounts_and_backtest_runs(
    sqlite_backend: SQLiteBackend,
) -> None:
    conn = sqlite_backend.open_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                strategy TEXT NOT NULL,
                initial_cash REAL NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE backtest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                run_name TEXT,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            INSERT INTO accounts (name, strategy, initial_cash, created_at)
            VALUES ('acct_legacy', 'Trend', 1000, '2026-01-01T00:00:00Z');
            """
        )

        db.init_schema(conn)

        account_columns = db._column_names(conn, "accounts")
        run_columns = db._column_names(conn, "backtest_runs")

        assert "benchmark_ticker" in account_columns
        assert "descriptive_name" in account_columns
        assert "rotation_overlay_watchlist" in account_columns
        assert "rotation_active_strategy" in account_columns
        assert "strategy_name" in run_columns

        row = conn.execute(
            "SELECT name, descriptive_name, benchmark_ticker, rotation_overlay_watchlist FROM accounts WHERE name = 'acct_legacy'"
        ).fetchone()
        assert row is not None
        assert row["descriptive_name"] == "acct_legacy"
        assert row["benchmark_ticker"] == "SPY"
        assert row["rotation_overlay_watchlist"] == db.DEFAULT_ROTATION_OVERLAY_WATCHLIST_JSON
    finally:
        conn.close()

def test_ensure_column_applies_post_sql_for_new_column(sqlite_backend: SQLiteBackend) -> None:
    conn = sqlite_backend.open_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                strategy TEXT NOT NULL,
                initial_cash REAL NOT NULL,
                created_at TEXT NOT NULL
            );

            INSERT INTO accounts (name, strategy, initial_cash, created_at)
            VALUES ('acct_post', 'Trend', 1000, '2026-01-01T00:00:00Z');
            """
        )

        migration = next(
            item for item in db.ACCOUNT_MIGRATIONS if item.column_name == "descriptive_name"
        )
        db._ensure_column(conn, "accounts", migration)

        row = conn.execute("SELECT descriptive_name FROM accounts WHERE name = 'acct_post'").fetchone()
        assert row is not None
        assert row["descriptive_name"] == "acct_post"
    finally:
        conn.close()


def test_overlay_watchlist_migration_backfills_existing_accounts(sqlite_backend: SQLiteBackend) -> None:
    conn = sqlite_backend.open_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                strategy TEXT NOT NULL,
                initial_cash REAL NOT NULL,
                created_at TEXT NOT NULL
            );

            INSERT INTO accounts (name, strategy, initial_cash, created_at)
            VALUES ('acct_watchlist', 'Trend', 1000, '2026-01-01T00:00:00Z');
            """
        )

        migration = next(
            item for item in db.ACCOUNT_MIGRATIONS if item.column_name == "rotation_overlay_watchlist"
        )
        db._ensure_column(conn, "accounts", migration)

        row = conn.execute(
            "SELECT rotation_overlay_watchlist FROM accounts WHERE name = 'acct_watchlist'"
        ).fetchone()
        assert row is not None
        assert row["rotation_overlay_watchlist"] == db.DEFAULT_ROTATION_OVERLAY_WATCHLIST_JSON
    finally:
        conn.close()


def test_ensure_column_is_noop_when_column_exists(sqlite_backend: SQLiteBackend) -> None:
    conn = sqlite_backend.open_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE backtest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                strategy_name TEXT,
                run_name TEXT,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )

        migration = db.BACKTEST_RUN_MIGRATIONS[0]
        db._ensure_column(conn, "backtest_runs", migration)

        columns = db._column_names(conn, "backtest_runs")
        assert "strategy_name" in columns
    finally:
        conn.close()
