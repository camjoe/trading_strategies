from trading.database.db_common import DEFAULT_ROTATION_OVERLAY_WATCHLIST_JSON

ACCOUNTS_TABLE_SQL = f"""
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
    trade_size_pct REAL,
    max_position_pct REAL,
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
    rotation_overlay_watchlist TEXT NOT NULL DEFAULT '{DEFAULT_ROTATION_OVERLAY_WATCHLIST_JSON}',
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

WALK_FORWARD_GROUPS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS walk_forward_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    grouping_key TEXT NOT NULL UNIQUE,
    account_id INTEGER NOT NULL,
    strategy_name TEXT NOT NULL,
    run_name_prefix TEXT,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    test_months INTEGER NOT NULL,
    step_months INTEGER NOT NULL,
    window_count INTEGER NOT NULL,
    average_return_pct REAL NOT NULL,
    median_return_pct REAL NOT NULL,
    best_return_pct REAL NOT NULL,
    worst_return_pct REAL NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
"""

WALK_FORWARD_GROUP_RUNS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS walk_forward_group_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    run_id INTEGER NOT NULL UNIQUE,
    window_index INTEGER NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    total_return_pct REAL NOT NULL,
    FOREIGN KEY (group_id) REFERENCES walk_forward_groups(id),
    FOREIGN KEY (run_id) REFERENCES backtest_runs(id),
    UNIQUE(group_id, window_index)
);
"""

WALK_FORWARD_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_walk_forward_groups_account_strategy_created
ON walk_forward_groups(account_id, strategy_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_walk_forward_group_runs_group_window
ON walk_forward_group_runs(group_id, window_index ASC);
"""

PROMOTION_REVIEWS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS promotion_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    account_name_snapshot TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    review_state TEXT NOT NULL DEFAULT 'requested',
    assessment_stage TEXT NOT NULL,
    assessment_status TEXT NOT NULL,
    ready_for_live INTEGER NOT NULL DEFAULT 0,
    overall_confidence REAL NOT NULL DEFAULT 0,
    live_trading_enabled_snapshot INTEGER NOT NULL DEFAULT 0,
    promotion_assessment_version TEXT NOT NULL,
    evaluation_artifact_version TEXT NOT NULL,
    frozen_assessment_payload TEXT NOT NULL,
    frozen_evaluation_payload TEXT NOT NULL,
    requested_by TEXT,
    reviewed_by TEXT,
    operator_summary_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT,
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
"""

PROMOTION_REVIEW_EVENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS promotion_review_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id INTEGER NOT NULL,
    event_seq INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    actor_type TEXT NOT NULL DEFAULT 'operator',
    actor_name TEXT,
    from_review_state TEXT,
    to_review_state TEXT,
    note TEXT,
    event_payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (review_id) REFERENCES promotion_reviews(id),
    UNIQUE(review_id, event_seq)
);
"""

PROMOTION_REVIEW_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_promotion_reviews_account_strategy_created
ON promotion_reviews(account_id, strategy_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_promotion_reviews_state_updated
ON promotion_reviews(review_state, updated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_promotion_reviews_open_requested
ON promotion_reviews(account_id, strategy_name)
WHERE review_state = 'requested';
CREATE INDEX IF NOT EXISTS idx_promotion_review_events_review_seq
ON promotion_review_events(review_id, event_seq ASC);
CREATE INDEX IF NOT EXISTS idx_promotion_review_events_review_created
ON promotion_review_events(review_id, created_at ASC);
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
        WALK_FORWARD_GROUPS_TABLE_SQL,
        WALK_FORWARD_GROUP_RUNS_TABLE_SQL,
        WALK_FORWARD_INDEXES_SQL,
        PROMOTION_REVIEWS_TABLE_SQL,
        PROMOTION_REVIEW_EVENTS_TABLE_SQL,
        PROMOTION_REVIEW_INDEXES_SQL,
    )
)
