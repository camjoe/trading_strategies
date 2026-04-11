from dataclasses import dataclass
from typing import Any

from trading.database.db_backend import get_backend
from trading.database.db_config import get_db_path

# Type alias — the concrete type depends on the active DatabaseBackend.
DBConnection = Any

DB_PATH = get_db_path()

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
    max_loss_pct REAL,
    rotation_enabled INTEGER NOT NULL DEFAULT 0,
    rotation_mode TEXT NOT NULL DEFAULT 'time',
    rotation_optimality_mode TEXT NOT NULL DEFAULT 'previous_period_best',
    rotation_interval_days INTEGER,
    rotation_interval_minutes INTEGER,
    rotation_lookback_days INTEGER,
    rotation_schedule TEXT,
    rotation_regime_strategy_risk_on TEXT,
    rotation_regime_strategy_neutral TEXT,
    rotation_regime_strategy_risk_off TEXT,
    rotation_overlay_mode TEXT NOT NULL DEFAULT 'none',
    rotation_overlay_min_tickers INTEGER,
    rotation_overlay_confidence_threshold REAL,
    rotation_active_index INTEGER NOT NULL DEFAULT 0,
    rotation_last_at TEXT,
    rotation_active_strategy TEXT
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
    strategy_name TEXT,
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

ROTATION_EPISODES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS rotation_episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    strategy_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    starting_equity REAL NOT NULL,
    ending_equity REAL,
    starting_realized_pnl REAL NOT NULL DEFAULT 0,
    ending_realized_pnl REAL,
    realized_pnl_delta REAL,
    snapshot_count INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
"""

ROTATION_EPISODE_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_rotation_episodes_account_started
ON rotation_episodes(account_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_rotation_episodes_account_strategy_ended
ON rotation_episodes(account_id, strategy_name, ended_at DESC);
"""

BROKER_ORDERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS broker_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    broker_order_id TEXT NOT NULL UNIQUE,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    qty REAL NOT NULL,
    order_type TEXT NOT NULL DEFAULT 'market',
    time_in_force TEXT NOT NULL DEFAULT 'day',
    requested_price REAL NOT NULL,
    status TEXT NOT NULL,
    filled_qty REAL NOT NULL DEFAULT 0,
    avg_fill_price REAL,
    commission REAL NOT NULL DEFAULT 0,
    submitted_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
"""

ORDER_FILLS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS order_fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    broker_order_id TEXT NOT NULL,
    filled_qty REAL NOT NULL,
    fill_price REAL NOT NULL,
    fill_time TEXT NOT NULL,
    commission REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (broker_order_id) REFERENCES broker_orders(broker_order_id)
);
"""

BROKER_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_broker_orders_account_id ON broker_orders(account_id);
CREATE INDEX IF NOT EXISTS idx_order_fills_broker_order_id ON order_fills(broker_order_id);
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
        ROTATION_EPISODES_TABLE_SQL,
        ROTATION_EPISODE_INDEXES_SQL,
        BROKER_ORDERS_TABLE_SQL,
        ORDER_FILLS_TABLE_SQL,
        BROKER_INDEXES_SQL,
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
    ColumnMigration(
        "rotation_enabled",
        "ALTER TABLE accounts ADD COLUMN rotation_enabled INTEGER NOT NULL DEFAULT 0",
    ),
    ColumnMigration(
        "rotation_mode",
        "ALTER TABLE accounts ADD COLUMN rotation_mode TEXT NOT NULL DEFAULT 'time'",
    ),
    ColumnMigration(
        "rotation_optimality_mode",
        "ALTER TABLE accounts ADD COLUMN rotation_optimality_mode TEXT NOT NULL DEFAULT 'previous_period_best'",
    ),
    ColumnMigration(
        "rotation_interval_days",
        "ALTER TABLE accounts ADD COLUMN rotation_interval_days INTEGER",
    ),
    ColumnMigration(
        "rotation_interval_minutes",
        "ALTER TABLE accounts ADD COLUMN rotation_interval_minutes INTEGER",
    ),
    ColumnMigration(
        "rotation_lookback_days",
        "ALTER TABLE accounts ADD COLUMN rotation_lookback_days INTEGER",
    ),
    ColumnMigration(
        "rotation_schedule",
        "ALTER TABLE accounts ADD COLUMN rotation_schedule TEXT",
    ),
    ColumnMigration(
        "rotation_regime_strategy_risk_on",
        "ALTER TABLE accounts ADD COLUMN rotation_regime_strategy_risk_on TEXT",
    ),
    ColumnMigration(
        "rotation_regime_strategy_neutral",
        "ALTER TABLE accounts ADD COLUMN rotation_regime_strategy_neutral TEXT",
    ),
    ColumnMigration(
        "rotation_regime_strategy_risk_off",
        "ALTER TABLE accounts ADD COLUMN rotation_regime_strategy_risk_off TEXT",
    ),
    ColumnMigration(
        "rotation_overlay_mode",
        "ALTER TABLE accounts ADD COLUMN rotation_overlay_mode TEXT NOT NULL DEFAULT 'none'",
    ),
    ColumnMigration(
        "rotation_overlay_min_tickers",
        "ALTER TABLE accounts ADD COLUMN rotation_overlay_min_tickers INTEGER",
    ),
    ColumnMigration(
        "rotation_overlay_confidence_threshold",
        "ALTER TABLE accounts ADD COLUMN rotation_overlay_confidence_threshold REAL",
    ),
    ColumnMigration(
        "rotation_active_index",
        "ALTER TABLE accounts ADD COLUMN rotation_active_index INTEGER NOT NULL DEFAULT 0",
    ),
    ColumnMigration(
        "rotation_last_at",
        "ALTER TABLE accounts ADD COLUMN rotation_last_at TEXT",
    ),
    ColumnMigration(
        "rotation_active_strategy",
        "ALTER TABLE accounts ADD COLUMN rotation_active_strategy TEXT",
    ),
)

BACKTEST_RUN_MIGRATIONS = (
    ColumnMigration(
        "strategy_name",
        "ALTER TABLE backtest_runs ADD COLUMN strategy_name TEXT",
    ),
)

# Broker-related columns added to accounts to support live broker connectivity.
ACCOUNT_BROKER_MIGRATIONS = (
    ColumnMigration(
        "broker_type",
        "ALTER TABLE accounts ADD COLUMN broker_type TEXT NOT NULL DEFAULT 'paper'",
    ),
    ColumnMigration(
        "broker_host",
        "ALTER TABLE accounts ADD COLUMN broker_host TEXT",
    ),
    ColumnMigration(
        "broker_port",
        "ALTER TABLE accounts ADD COLUMN broker_port INTEGER",
    ),
    ColumnMigration(
        "broker_client_id",
        "ALTER TABLE accounts ADD COLUMN broker_client_id INTEGER",
    ),
    # Guard flag — must be explicitly set to 1 before live orders are submitted.
    ColumnMigration(
        "live_trading_enabled",
        "ALTER TABLE accounts ADD COLUMN live_trading_enabled INTEGER NOT NULL DEFAULT 0",
    ),
)

# Migrations for the order_fills table.
# Uses post_sql to add a partial unique index that deduplicates IB execution reports
# on repeated reconciliation calls.  Paper fills (exec_id IS NULL) are excluded
# from the constraint since they are never reconciled.
ORDER_FILL_MIGRATIONS = (
    ColumnMigration(
        "exec_id",
        "ALTER TABLE order_fills ADD COLUMN exec_id TEXT",
        post_sql=(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_order_fills_exec_id "
            "ON order_fills(broker_order_id, exec_id) WHERE exec_id IS NOT NULL",
        ),
    ),
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
    for migration in BACKTEST_RUN_MIGRATIONS:
        _ensure_column(conn, "backtest_runs", migration)
    for migration in ACCOUNT_BROKER_MIGRATIONS:
        _ensure_column(conn, "accounts", migration)
    for migration in ORDER_FILL_MIGRATIONS:
        _ensure_column(conn, "order_fills", migration)
    conn.commit()
