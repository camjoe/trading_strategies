from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trading.database.code.db_backend import get_backend

# Type alias — the concrete type depends on the active DatabaseBackend.
DBConnection = Any

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "paper_trading.db"

ACCOUNTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    strategy TEXT NOT NULL,
    initial_cash REAL NOT NULL,
    created_at TEXT NOT NULL,
    benchmark_ticker TEXT NOT NULL DEFAULT 'SPY',
    descriptive_name TEXT NOT NULL DEFAULT '',
    goal_min_return_pct REAL,
    goal_max_return_pct REAL,
    goal_period TEXT NOT NULL DEFAULT 'monthly',
    learning_enabled INTEGER NOT NULL DEFAULT 0,
    risk_policy TEXT NOT NULL DEFAULT 'none',
    stop_loss_pct REAL,
    take_profit_pct REAL,
    instrument_mode TEXT NOT NULL DEFAULT 'equity',
    option_strike_offset_pct REAL,
    option_min_dte INTEGER,
    option_max_dte INTEGER,
    option_type TEXT,
    target_delta_min REAL,
    target_delta_max REAL,
    max_premium_per_trade REAL,
    max_contracts_per_trade INTEGER,
    iv_rank_min REAL,
    iv_rank_max REAL,
    roll_dte_threshold INTEGER,
    profit_take_pct REAL,
    max_loss_pct REAL
);
"""

TRADES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    qty REAL NOT NULL,
    price REAL NOT NULL,
    fee REAL NOT NULL DEFAULT 0,
    trade_time TEXT NOT NULL,
    note TEXT,
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
"""

EQUITY_SNAPSHOTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS equity_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    snapshot_time TEXT NOT NULL,
    cash REAL NOT NULL,
    market_value REAL NOT NULL,
    equity REAL NOT NULL,
    realized_pnl REAL NOT NULL,
    unrealized_pnl REAL NOT NULL,
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
"""

BACKTEST_RUNS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS backtest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    run_name TEXT,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    slippage_bps REAL NOT NULL DEFAULT 0,
    fee_per_trade REAL NOT NULL DEFAULT 0,
    tickers_file TEXT,
    notes TEXT,
    warnings TEXT,
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
"""

BACKTEST_TRADES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS backtest_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    trade_time TEXT NOT NULL,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    qty REAL NOT NULL,
    price REAL NOT NULL,
    fee REAL NOT NULL DEFAULT 0,
    slippage_bps REAL NOT NULL DEFAULT 0,
    note TEXT,
    FOREIGN KEY (run_id) REFERENCES backtest_runs(id)
);
"""

BACKTEST_EQUITY_SNAPSHOTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS backtest_equity_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    snapshot_time TEXT NOT NULL,
    cash REAL NOT NULL,
    market_value REAL NOT NULL,
    equity REAL NOT NULL,
    realized_pnl REAL NOT NULL,
    unrealized_pnl REAL NOT NULL,
    FOREIGN KEY (run_id) REFERENCES backtest_runs(id)
);
"""

BACKTEST_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_backtest_runs_account_id ON backtest_runs(account_id);
CREATE INDEX IF NOT EXISTS idx_backtest_trades_run_id ON backtest_trades(run_id);
CREATE INDEX IF NOT EXISTS idx_backtest_equity_run_id ON backtest_equity_snapshots(run_id);
"""

SCHEMA_SQL = "\n".join(
    (
        ACCOUNTS_TABLE_SQL,
        TRADES_TABLE_SQL,
        EQUITY_SNAPSHOTS_TABLE_SQL,
        BACKTEST_RUNS_TABLE_SQL,
        BACKTEST_TRADES_TABLE_SQL,
        BACKTEST_EQUITY_SNAPSHOTS_TABLE_SQL,
        BACKTEST_INDEXES_SQL,
    )
)

@dataclass(frozen=True)
class ColumnMigration:
    column_name: str
    ddl: str
    post_sql: tuple[str, ...] = ()

ACCOUNT_MIGRATIONS = (
    ColumnMigration(
        "benchmark_ticker",
        "ALTER TABLE accounts ADD COLUMN benchmark_ticker TEXT NOT NULL DEFAULT 'SPY'",
    ),
    ColumnMigration(
        "descriptive_name",
        "ALTER TABLE accounts ADD COLUMN descriptive_name TEXT NOT NULL DEFAULT ''",
        ("UPDATE accounts SET descriptive_name = name WHERE descriptive_name = ''",),
    ),
    ColumnMigration(
        "goal_min_return_pct",
        "ALTER TABLE accounts ADD COLUMN goal_min_return_pct REAL",
    ),
    ColumnMigration(
        "goal_max_return_pct",
        "ALTER TABLE accounts ADD COLUMN goal_max_return_pct REAL",
    ),
    ColumnMigration(
        "goal_period",
        "ALTER TABLE accounts ADD COLUMN goal_period TEXT NOT NULL DEFAULT 'monthly'",
    ),
    ColumnMigration(
        "learning_enabled",
        "ALTER TABLE accounts ADD COLUMN learning_enabled INTEGER NOT NULL DEFAULT 0",
    ),
    ColumnMigration(
        "risk_policy",
        "ALTER TABLE accounts ADD COLUMN risk_policy TEXT NOT NULL DEFAULT 'none'",
    ),
    ColumnMigration("stop_loss_pct", "ALTER TABLE accounts ADD COLUMN stop_loss_pct REAL"),
    ColumnMigration("take_profit_pct", "ALTER TABLE accounts ADD COLUMN take_profit_pct REAL"),
    ColumnMigration(
        "instrument_mode",
        "ALTER TABLE accounts ADD COLUMN instrument_mode TEXT NOT NULL DEFAULT 'equity'",
    ),
    ColumnMigration(
        "option_strike_offset_pct",
        "ALTER TABLE accounts ADD COLUMN option_strike_offset_pct REAL",
    ),
    ColumnMigration("option_min_dte", "ALTER TABLE accounts ADD COLUMN option_min_dte INTEGER"),
    ColumnMigration("option_max_dte", "ALTER TABLE accounts ADD COLUMN option_max_dte INTEGER"),
    ColumnMigration("option_type", "ALTER TABLE accounts ADD COLUMN option_type TEXT"),
    ColumnMigration("target_delta_min", "ALTER TABLE accounts ADD COLUMN target_delta_min REAL"),
    ColumnMigration("target_delta_max", "ALTER TABLE accounts ADD COLUMN target_delta_max REAL"),
    ColumnMigration(
        "max_premium_per_trade",
        "ALTER TABLE accounts ADD COLUMN max_premium_per_trade REAL",
    ),
    ColumnMigration(
        "max_contracts_per_trade",
        "ALTER TABLE accounts ADD COLUMN max_contracts_per_trade INTEGER",
    ),
    ColumnMigration("iv_rank_min", "ALTER TABLE accounts ADD COLUMN iv_rank_min REAL"),
    ColumnMigration("iv_rank_max", "ALTER TABLE accounts ADD COLUMN iv_rank_max REAL"),
    ColumnMigration(
        "roll_dte_threshold",
        "ALTER TABLE accounts ADD COLUMN roll_dte_threshold INTEGER",
    ),
    ColumnMigration("profit_take_pct", "ALTER TABLE accounts ADD COLUMN profit_take_pct REAL"),
    ColumnMigration("max_loss_pct", "ALTER TABLE accounts ADD COLUMN max_loss_pct REAL"),
)

def ensure_db() -> DBConnection:
    conn = get_backend().open_connection()
    init_schema(conn)
    return conn

def _column_names(conn: DBConnection, table_name: str) -> set[str]:
    return get_backend().get_table_columns(conn, table_name)

def _ensure_column(conn: DBConnection, table_name: str, migration: ColumnMigration) -> None:
    if migration.column_name in _column_names(conn, table_name):
        return
    conn.execute(migration.ddl)
    for stmt in migration.post_sql:
        conn.execute(stmt)
    conn.commit()

def init_schema(conn: DBConnection) -> None:
    get_backend().run_script(conn, SCHEMA_SQL)
    for migration in ACCOUNT_MIGRATIONS:
        _ensure_column(conn, "accounts", migration)
    conn.commit()
