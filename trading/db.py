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
            benchmark_ticker TEXT NOT NULL DEFAULT 'SPY'
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
    conn.commit()


def ensure_accounts_benchmark_column(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(accounts)").fetchall()
    names = {str(c[1]) for c in cols}
    if "benchmark_ticker" not in names:
        conn.execute(
            "ALTER TABLE accounts ADD COLUMN benchmark_ticker TEXT NOT NULL DEFAULT 'SPY'"
        )
        conn.commit()
