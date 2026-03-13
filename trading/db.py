import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "database" / "paper_trading.db"


def ensure_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
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
    )
    ensure_accounts_benchmark_column(conn)
    ensure_accounts_descriptive_name_column(conn)
    ensure_accounts_goal_min_return_pct_column(conn)
    ensure_accounts_goal_max_return_pct_column(conn)
    ensure_accounts_goal_period_column(conn)
    ensure_accounts_learning_enabled_column(conn)
    ensure_accounts_risk_policy_column(conn)
    ensure_accounts_stop_loss_pct_column(conn)
    ensure_accounts_take_profit_pct_column(conn)
    ensure_accounts_instrument_mode_column(conn)
    ensure_accounts_option_strike_offset_pct_column(conn)
    ensure_accounts_option_min_dte_column(conn)
    ensure_accounts_option_max_dte_column(conn)
    ensure_accounts_option_type_column(conn)
    ensure_accounts_target_delta_min_column(conn)
    ensure_accounts_target_delta_max_column(conn)
    ensure_accounts_max_premium_per_trade_column(conn)
    ensure_accounts_max_contracts_per_trade_column(conn)
    ensure_accounts_iv_rank_min_column(conn)
    ensure_accounts_iv_rank_max_column(conn)
    ensure_accounts_roll_dte_threshold_column(conn)
    ensure_accounts_profit_take_pct_column(conn)
    ensure_accounts_max_loss_pct_column(conn)
    conn.commit()


def ensure_accounts_benchmark_column(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(accounts)").fetchall()
    names = {str(c[1]) for c in cols}
    if "benchmark_ticker" not in names:
        conn.execute(
            "ALTER TABLE accounts ADD COLUMN benchmark_ticker TEXT NOT NULL DEFAULT 'SPY'"
        )
        conn.commit()


def ensure_accounts_descriptive_name_column(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(accounts)").fetchall()
    names = {str(c[1]) for c in cols}
    if "descriptive_name" not in names:
        conn.execute("ALTER TABLE accounts ADD COLUMN descriptive_name TEXT NOT NULL DEFAULT ''")
        conn.execute("UPDATE accounts SET descriptive_name = name WHERE descriptive_name = ''")
        conn.commit()


def ensure_accounts_goal_min_return_pct_column(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(accounts)").fetchall()
    names = {str(c[1]) for c in cols}
    if "goal_min_return_pct" not in names:
        conn.execute("ALTER TABLE accounts ADD COLUMN goal_min_return_pct REAL")
        conn.commit()


def ensure_accounts_goal_max_return_pct_column(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(accounts)").fetchall()
    names = {str(c[1]) for c in cols}
    if "goal_max_return_pct" not in names:
        conn.execute("ALTER TABLE accounts ADD COLUMN goal_max_return_pct REAL")
        conn.commit()


def ensure_accounts_goal_period_column(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(accounts)").fetchall()
    names = {str(c[1]) for c in cols}
    if "goal_period" not in names:
        conn.execute("ALTER TABLE accounts ADD COLUMN goal_period TEXT NOT NULL DEFAULT 'monthly'")
        conn.commit()


def ensure_accounts_learning_enabled_column(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(accounts)").fetchall()
    names = {str(c[1]) for c in cols}
    if "learning_enabled" not in names:
        conn.execute("ALTER TABLE accounts ADD COLUMN learning_enabled INTEGER NOT NULL DEFAULT 0")
        conn.commit()


def ensure_accounts_risk_policy_column(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(accounts)").fetchall()
    names = {str(c[1]) for c in cols}
    if "risk_policy" not in names:
        conn.execute("ALTER TABLE accounts ADD COLUMN risk_policy TEXT NOT NULL DEFAULT 'none'")
        conn.commit()


def ensure_accounts_stop_loss_pct_column(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(accounts)").fetchall()
    names = {str(c[1]) for c in cols}
    if "stop_loss_pct" not in names:
        conn.execute("ALTER TABLE accounts ADD COLUMN stop_loss_pct REAL")
        conn.commit()


def ensure_accounts_take_profit_pct_column(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(accounts)").fetchall()
    names = {str(c[1]) for c in cols}
    if "take_profit_pct" not in names:
        conn.execute("ALTER TABLE accounts ADD COLUMN take_profit_pct REAL")
        conn.commit()


def ensure_accounts_instrument_mode_column(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(accounts)").fetchall()
    names = {str(c[1]) for c in cols}
    if "instrument_mode" not in names:
        conn.execute("ALTER TABLE accounts ADD COLUMN instrument_mode TEXT NOT NULL DEFAULT 'equity'")
        conn.commit()


def ensure_accounts_option_strike_offset_pct_column(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(accounts)").fetchall()
    names = {str(c[1]) for c in cols}
    if "option_strike_offset_pct" not in names:
        conn.execute("ALTER TABLE accounts ADD COLUMN option_strike_offset_pct REAL")
        conn.commit()


def ensure_accounts_option_min_dte_column(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(accounts)").fetchall()
    names = {str(c[1]) for c in cols}
    if "option_min_dte" not in names:
        conn.execute("ALTER TABLE accounts ADD COLUMN option_min_dte INTEGER")
        conn.commit()


def ensure_accounts_option_max_dte_column(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(accounts)").fetchall()
    names = {str(c[1]) for c in cols}
    if "option_max_dte" not in names:
        conn.execute("ALTER TABLE accounts ADD COLUMN option_max_dte INTEGER")
        conn.commit()


def ensure_accounts_option_type_column(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(accounts)").fetchall()
    names = {str(c[1]) for c in cols}
    if "option_type" not in names:
        conn.execute("ALTER TABLE accounts ADD COLUMN option_type TEXT")
        conn.commit()


def ensure_accounts_target_delta_min_column(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(accounts)").fetchall()
    names = {str(c[1]) for c in cols}
    if "target_delta_min" not in names:
        conn.execute("ALTER TABLE accounts ADD COLUMN target_delta_min REAL")
        conn.commit()


def ensure_accounts_target_delta_max_column(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(accounts)").fetchall()
    names = {str(c[1]) for c in cols}
    if "target_delta_max" not in names:
        conn.execute("ALTER TABLE accounts ADD COLUMN target_delta_max REAL")
        conn.commit()


def ensure_accounts_max_premium_per_trade_column(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(accounts)").fetchall()
    names = {str(c[1]) for c in cols}
    if "max_premium_per_trade" not in names:
        conn.execute("ALTER TABLE accounts ADD COLUMN max_premium_per_trade REAL")
        conn.commit()


def ensure_accounts_max_contracts_per_trade_column(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(accounts)").fetchall()
    names = {str(c[1]) for c in cols}
    if "max_contracts_per_trade" not in names:
        conn.execute("ALTER TABLE accounts ADD COLUMN max_contracts_per_trade INTEGER")
        conn.commit()


def ensure_accounts_iv_rank_min_column(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(accounts)").fetchall()
    names = {str(c[1]) for c in cols}
    if "iv_rank_min" not in names:
        conn.execute("ALTER TABLE accounts ADD COLUMN iv_rank_min REAL")
        conn.commit()


def ensure_accounts_iv_rank_max_column(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(accounts)").fetchall()
    names = {str(c[1]) for c in cols}
    if "iv_rank_max" not in names:
        conn.execute("ALTER TABLE accounts ADD COLUMN iv_rank_max REAL")
        conn.commit()


def ensure_accounts_roll_dte_threshold_column(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(accounts)").fetchall()
    names = {str(c[1]) for c in cols}
    if "roll_dte_threshold" not in names:
        conn.execute("ALTER TABLE accounts ADD COLUMN roll_dte_threshold INTEGER")
        conn.commit()


def ensure_accounts_profit_take_pct_column(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(accounts)").fetchall()
    names = {str(c[1]) for c in cols}
    if "profit_take_pct" not in names:
        conn.execute("ALTER TABLE accounts ADD COLUMN profit_take_pct REAL")
        conn.commit()


def ensure_accounts_max_loss_pct_column(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(accounts)").fetchall()
    names = {str(c[1]) for c in cols}
    if "max_loss_pct" not in names:
        conn.execute("ALTER TABLE accounts ADD COLUMN max_loss_pct REAL")
        conn.commit()
