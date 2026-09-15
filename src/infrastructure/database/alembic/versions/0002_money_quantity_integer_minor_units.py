"""Change live money and quantity columns from REAL to INTEGER minor units.

Revision ID: 0002
Revises: 0001

Type-only change (money-representation plan, Stage 3). Every affected table is
empty at migration time — staging, prod, and dev are reset — so no value is
converted; the columns change affinity from REAL to INTEGER and the persistence
encoder writes and reads integer minor units.

Scope is the live trading tables only. The backtest and optimizer tables keep
REAL: the backtest computes in float, and its stored metrics are approximate.

SQLite cannot change a column's type in place, so each table is rebuilt with the
documented create-new / copy / drop / rename procedure (self-contained literal
DDL, so partial indexes and CHECK constraints are preserved exactly rather than
reflected). The migration connection runs with foreign keys disabled, and only
the ``_new`` table is ever renamed, so no child foreign-key reference is
rewritten.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Parent tables first, then children. Ordering is not required while foreign keys
# are disabled during the rebuild, but parent-first keeps the intent readable.
_REBUILD_ORDER: tuple[str, ...] = (
    "accounts",
    "books",
    "orders",
    "order_fills",
    "positions",
    "ledger",
    "equity_snapshots",
    "daily_metrics",
    "risk_snapshots",
    "risk_decisions",
)

# The explicit column list copied for each table (no SELECT *), in creation order.
_COPY_COLUMNS: dict[str, str] = {
    "accounts": (
        "id, name, base_ccy, initial_cash, created_at, updated_at, benchmark_ticker, "
        "descriptive_name, broker_type, broker_host, broker_port, broker_client_id, live_trading_enabled"
    ),
    "books": (
        "id, account_id, name, status, is_default, start_equity, current_cash, current_equity, "
        "trade_symbols, goal_min_return_pct, goal_max_return_pct, goal_period, created_at, updated_at, "
        "learning_enabled, risk_policy, stop_loss_pct, take_profit_pct, option_profit_take_pct, "
        "option_max_loss_pct, trade_size_pct, max_position_pct, max_trades_per_run, instrument_mode, "
        "option_strike_offset_pct, option_min_dte, option_max_dte, option_type, target_delta_min, "
        "target_delta_max, max_premium_per_trade, max_contracts_per_trade, iv_rank_min, iv_rank_max, "
        "roll_dte_threshold"
    ),
    "orders": (
        "id, book_id, account_id, strategy_id, rotation_decision_id, broker_order_id, client_order_id, "
        "symbol, side, qty, order_type, time_in_force, requested_price, status, filled_qty, "
        "avg_fill_price, commission, submitted_at, updated_at, status_reason, realized_pnl_delta"
    ),
    "order_fills": "id, order_id, exec_id, filled_qty, fill_price, commission, fill_time",
    "positions": "book_id, symbol, qty, avg_cost, market_value, unrealized_pnl, updated_at",
    "ledger": "id, book_id, entry_type, amount, reference_type, reference_id, entry_time, created_at",
    "equity_snapshots": "id, book_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl",
    "daily_metrics": (
        "id, book_id, metric_date, return_pct, drawdown_pct, turnover_pct, slippage_bps, hit_rate, "
        "expectancy, risk_adjusted_score, trade_count, fees_total, created_at, updated_at"
    ),
    "risk_snapshots": (
        "id, account_id, snapshot_time, gross_exposure, net_exposure, max_symbol_concentration_pct, "
        "max_sector_concentration_pct, drawdown_pct, leverage_proxy, daily_loss_pct, "
        "kill_switch_triggered, risk_payload_json"
    ),
    "risk_decisions": (
        "id, account_id, book_id, decision_time, symbol, side, action, reason_code, requested_qty, "
        "approved_qty, requested_notional, approved_notional, risk_payload_json, created_at"
    ),
}

# Indexes to recreate after each table is rebuilt (dropping a table drops its
# indexes). Inline UNIQUE constraints ride the CREATE statements and are not here.
_TABLE_INDEXES: dict[str, tuple[str, ...]] = {
    "accounts": (),
    "books": (
        "CREATE INDEX idx_books_account_status ON books(account_id, status)",
        "CREATE UNIQUE INDEX idx_books_default_per_account ON books(account_id) WHERE is_default = 1",
        "CREATE UNIQUE INDEX idx_books_id_account ON books(id, account_id)",
    ),
    "orders": (
        (
            "CREATE UNIQUE INDEX idx_orders_account_broker_order_id "
            "ON orders(account_id, broker_order_id) WHERE broker_order_id IS NOT NULL"
        ),
        (
            "CREATE UNIQUE INDEX idx_orders_account_client_order_id "
            "ON orders(account_id, client_order_id) WHERE client_order_id IS NOT NULL"
        ),
        "CREATE INDEX idx_orders_account_status_submitted ON orders(account_id, status, submitted_at DESC)",
        "CREATE INDEX idx_orders_book_submitted ON orders(book_id, submitted_at DESC)",
    ),
    "order_fills": ("CREATE INDEX idx_order_fills_order_id ON order_fills(order_id)",),
    "positions": ("CREATE INDEX idx_positions_symbol_updated ON positions(symbol, updated_at DESC)",),
    "ledger": (
        "CREATE INDEX idx_ledger_book_entry_time ON ledger(book_id, entry_time DESC)",
        "CREATE INDEX idx_ledger_reference ON ledger(reference_type, reference_id)",
    ),
    "equity_snapshots": (
        "CREATE INDEX idx_equity_snapshots_book_time ON equity_snapshots(book_id, snapshot_time DESC)",
    ),
    "daily_metrics": ("CREATE INDEX idx_daily_metrics_book_date ON daily_metrics(book_id, metric_date DESC)",),
    "risk_snapshots": (
        "CREATE INDEX idx_risk_snapshots_account_time ON risk_snapshots(account_id, snapshot_time DESC)",
    ),
    "risk_decisions": (
        "CREATE INDEX idx_risk_decisions_account_time ON risk_decisions(account_id, decision_time DESC)",
        "CREATE INDEX idx_risk_decisions_book_time ON risk_decisions(book_id, decision_time DESC)",
    ),
}

# The rebuilt table shape with money/quantity columns as INTEGER (upgrade target).
_INTEGER_CREATE: dict[str, str] = {
    "accounts": """
        CREATE TABLE accounts_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            base_ccy TEXT NOT NULL DEFAULT 'USD',
            initial_cash INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            benchmark_ticker TEXT NOT NULL DEFAULT 'SPY',
            descriptive_name TEXT NOT NULL DEFAULT '',
            broker_type TEXT NOT NULL DEFAULT 'paper',
            broker_host TEXT,
            broker_port INTEGER,
            broker_client_id INTEGER,
            live_trading_enabled INTEGER NOT NULL DEFAULT 0
        )
    """,
    "books": """
        CREATE TABLE books_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'closed')),
            is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
            start_equity INTEGER NOT NULL,
            current_cash INTEGER NOT NULL,
            current_equity INTEGER NOT NULL,
            trade_symbols TEXT NOT NULL,
            goal_min_return_pct REAL,
            goal_max_return_pct REAL,
            goal_period TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            learning_enabled INTEGER NOT NULL DEFAULT 0 CHECK (learning_enabled IN (0, 1)),
            risk_policy TEXT NOT NULL DEFAULT 'none' CHECK (
                risk_policy IN ('none', 'fixed_stop', 'take_profit', 'stop_and_target')
            ),
            stop_loss_pct REAL,
            take_profit_pct REAL,
            option_profit_take_pct REAL,
            option_max_loss_pct REAL,
            trade_size_pct REAL,
            max_position_pct REAL,
            max_trades_per_run INTEGER CHECK (max_trades_per_run IS NULL OR max_trades_per_run >= 1),
            instrument_mode TEXT NOT NULL DEFAULT 'equity' CHECK (instrument_mode IN ('equity', 'leaps')),
            option_strike_offset_pct REAL,
            option_min_dte INTEGER,
            option_max_dte INTEGER,
            option_type TEXT CHECK (option_type IS NULL OR option_type IN ('call', 'put', 'both')),
            target_delta_min REAL,
            target_delta_max REAL,
            max_premium_per_trade INTEGER,
            max_contracts_per_trade INTEGER,
            iv_rank_min REAL,
            iv_rank_max REAL,
            roll_dte_threshold INTEGER,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            UNIQUE (account_id, name)
        )
    """,
    "orders": """
        CREATE TABLE orders_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            strategy_id INTEGER,
            rotation_decision_id INTEGER,
            broker_order_id TEXT,
            client_order_id TEXT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
            qty INTEGER NOT NULL,
            order_type TEXT NOT NULL DEFAULT 'market' CHECK (order_type IN ('market', 'limit')),
            time_in_force TEXT NOT NULL DEFAULT 'day' CHECK (time_in_force IN ('day', 'gtc')),
            requested_price INTEGER,
            status TEXT NOT NULL CHECK (
                status IN ('pending', 'submitted', 'partially_filled', 'filled', 'rejected', 'cancelled')
            ),
            filled_qty INTEGER NOT NULL DEFAULT 0,
            avg_fill_price INTEGER,
            commission INTEGER NOT NULL DEFAULT 0,
            submitted_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            status_reason TEXT,
            realized_pnl_delta INTEGER,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY (strategy_id) REFERENCES strategies(id),
            FOREIGN KEY (rotation_decision_id) REFERENCES rotation_decisions(id)
        )
    """,
    "order_fills": """
        CREATE TABLE order_fills_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            exec_id TEXT,
            filled_qty INTEGER NOT NULL,
            fill_price INTEGER NOT NULL,
            commission INTEGER NOT NULL DEFAULT 0,
            fill_time TEXT NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
            UNIQUE (order_id, exec_id)
        )
    """,
    "positions": """
        CREATE TABLE positions_new (
            book_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            qty INTEGER NOT NULL,
            avg_cost INTEGER NOT NULL,
            market_value INTEGER NOT NULL,
            unrealized_pnl INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (book_id, symbol),
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
        )
    """,
    "ledger": """
        CREATE TABLE ledger_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            entry_type TEXT NOT NULL CHECK (
                entry_type IN ('trade', 'fee', 'deposit', 'withdrawal', 'adjustment')
            ),
            amount INTEGER NOT NULL,
            reference_type TEXT,
            reference_id TEXT,
            entry_time TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
        )
    """,
    "equity_snapshots": """
        CREATE TABLE equity_snapshots_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            snapshot_time TEXT NOT NULL,
            cash INTEGER NOT NULL,
            market_value INTEGER NOT NULL,
            equity INTEGER NOT NULL,
            realized_pnl INTEGER NOT NULL,
            unrealized_pnl INTEGER NOT NULL,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
            UNIQUE (book_id, snapshot_time)
        )
    """,
    "daily_metrics": """
        CREATE TABLE daily_metrics_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            metric_date TEXT NOT NULL,
            return_pct REAL,
            drawdown_pct REAL,
            turnover_pct REAL,
            slippage_bps REAL,
            hit_rate REAL,
            expectancy INTEGER,
            risk_adjusted_score REAL,
            trade_count INTEGER,
            fees_total INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
            UNIQUE (book_id, metric_date)
        )
    """,
    "risk_snapshots": """
        CREATE TABLE risk_snapshots_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            snapshot_time TEXT NOT NULL,
            gross_exposure INTEGER NOT NULL,
            net_exposure INTEGER NOT NULL,
            max_symbol_concentration_pct REAL NOT NULL,
            max_sector_concentration_pct REAL NOT NULL,
            drawdown_pct REAL,
            leverage_proxy REAL,
            daily_loss_pct REAL,
            kill_switch_triggered INTEGER NOT NULL DEFAULT 0 CHECK (kill_switch_triggered IN (0, 1)),
            risk_payload_json TEXT NOT NULL,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            UNIQUE (account_id, snapshot_time)
        )
    """,
    "risk_decisions": """
        CREATE TABLE risk_decisions_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            book_id INTEGER,
            decision_time TEXT NOT NULL,
            symbol TEXT,
            side TEXT CHECK (side IS NULL OR side IN ('buy', 'sell')),
            action TEXT NOT NULL CHECK (action IN ('allow', 'rescale', 'block')),
            reason_code TEXT NOT NULL,
            requested_qty INTEGER,
            approved_qty INTEGER,
            requested_notional INTEGER,
            approved_notional INTEGER,
            risk_payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE SET NULL,
            FOREIGN KEY (book_id, account_id) REFERENCES books(id, account_id)
        )
    """,
}

# The rebuilt table shape with money/quantity columns back as REAL (downgrade
# target = the 0001 baseline shape).
_REAL_CREATE: dict[str, str] = {
    "accounts": _INTEGER_CREATE["accounts"].replace("initial_cash INTEGER", "initial_cash REAL"),
    "books": (
        _INTEGER_CREATE["books"]
        .replace("start_equity INTEGER", "start_equity REAL")
        .replace("current_cash INTEGER", "current_cash REAL")
        .replace("current_equity INTEGER", "current_equity REAL")
        .replace("max_premium_per_trade INTEGER", "max_premium_per_trade REAL")
    ),
    "orders": (
        _INTEGER_CREATE["orders"]
        .replace("qty INTEGER NOT NULL", "qty REAL NOT NULL")
        .replace("requested_price INTEGER", "requested_price REAL")
        .replace("filled_qty INTEGER NOT NULL DEFAULT 0", "filled_qty REAL NOT NULL DEFAULT 0")
        .replace("avg_fill_price INTEGER", "avg_fill_price REAL")
        .replace("commission INTEGER NOT NULL DEFAULT 0", "commission REAL NOT NULL DEFAULT 0")
        .replace("realized_pnl_delta INTEGER", "realized_pnl_delta REAL")
    ),
    "order_fills": (
        _INTEGER_CREATE["order_fills"]
        .replace("filled_qty INTEGER NOT NULL", "filled_qty REAL NOT NULL")
        .replace("fill_price INTEGER NOT NULL", "fill_price REAL NOT NULL")
        .replace("commission INTEGER NOT NULL DEFAULT 0", "commission REAL NOT NULL DEFAULT 0")
    ),
    "positions": (
        _INTEGER_CREATE["positions"]
        .replace("qty INTEGER NOT NULL", "qty REAL NOT NULL")
        .replace("avg_cost INTEGER NOT NULL", "avg_cost REAL NOT NULL")
        .replace("market_value INTEGER NOT NULL", "market_value REAL NOT NULL")
        .replace("unrealized_pnl INTEGER NOT NULL", "unrealized_pnl REAL NOT NULL")
    ),
    "ledger": _INTEGER_CREATE["ledger"].replace("amount INTEGER NOT NULL", "amount REAL NOT NULL"),
    "equity_snapshots": (
        _INTEGER_CREATE["equity_snapshots"]
        .replace("cash INTEGER NOT NULL", "cash REAL NOT NULL")
        .replace("market_value INTEGER NOT NULL", "market_value REAL NOT NULL")
        .replace("equity INTEGER NOT NULL", "equity REAL NOT NULL")
        .replace("realized_pnl INTEGER NOT NULL", "realized_pnl REAL NOT NULL")
        .replace("unrealized_pnl INTEGER NOT NULL", "unrealized_pnl REAL NOT NULL")
    ),
    "daily_metrics": (
        _INTEGER_CREATE["daily_metrics"]
        .replace("expectancy INTEGER", "expectancy REAL")
        .replace("fees_total INTEGER", "fees_total REAL")
    ),
    "risk_snapshots": (
        _INTEGER_CREATE["risk_snapshots"]
        .replace("gross_exposure INTEGER NOT NULL", "gross_exposure REAL NOT NULL")
        .replace("net_exposure INTEGER NOT NULL", "net_exposure REAL NOT NULL")
    ),
    "risk_decisions": (
        _INTEGER_CREATE["risk_decisions"]
        .replace("requested_qty INTEGER", "requested_qty REAL")
        .replace("approved_qty INTEGER", "approved_qty REAL")
        .replace("requested_notional INTEGER", "requested_notional REAL")
        .replace("approved_notional INTEGER", "approved_notional REAL")
    ),
}


def _require_empty(table: str) -> None:
    """Abort the migration if ``table`` holds any row.

    The rebuild copies values verbatim; it changes column affinity without scaling.
    A money value copied that way stores dollars as raw integer minor units (or the
    reverse on downgrade), off by the minor-unit scale, and does so silently. Every
    environment is reset before this revision (money-representation plan, Stage 3),
    so a populated table means that reset did not happen — fail loudly instead of
    corrupting the values.
    """
    count = op.get_bind().execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar()  # noqa: S608
    if count:
        raise RuntimeError(
            f"Revision 0002 requires an empty '{table}' table but found {count} rows. It changes "
            "money and quantity columns from REAL to INTEGER minor units without scaling values, so "
            "it must run on a reset database. See docs/reference/database-reset-plan.md."
        )


def _rebuild(table: str, create_new_sql: str) -> None:
    columns = _COPY_COLUMNS[table]
    _require_empty(table)
    op.execute(create_new_sql)
    op.execute(f"INSERT INTO {table}_new ({columns}) SELECT {columns} FROM {table}")
    op.execute(f"DROP TABLE {table}")
    op.execute(f"ALTER TABLE {table}_new RENAME TO {table}")
    for index_sql in _TABLE_INDEXES[table]:
        op.execute(index_sql)


def upgrade() -> None:
    for table in _REBUILD_ORDER:
        _rebuild(table, _INTEGER_CREATE[table])


def downgrade() -> None:
    for table in _REBUILD_ORDER:
        _rebuild(table, _REAL_CREATE[table])
