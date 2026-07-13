from __future__ import annotations
from infrastructure.database.migrations import DEFAULT_ROTATION_OVERLAY_WATCHLIST_JSON

ACCOUNTS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    account_kind TEXT NOT NULL DEFAULT 'managed',
    strategy TEXT NOT NULL,
    base_ccy TEXT NOT NULL DEFAULT 'USD',
    initial_cash REAL NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT,
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
    rotation_active_strategy TEXT,
    trade_universes TEXT
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

TRADES_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_trades_trade_time ON trades(trade_time);
"""

GLOBAL_SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS global_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    runtime_max_trades_per_day INTEGER CHECK (
        runtime_max_trades_per_day IS NULL OR runtime_max_trades_per_day >= 1
    ),
    runtime_max_trades_per_minute INTEGER CHECK (
        runtime_max_trades_per_minute IS NULL OR runtime_max_trades_per_minute >= 1
    ),
    evaluation_backtest_trade_count_for_full_confidence INTEGER NOT NULL DEFAULT 50 CHECK (
        evaluation_backtest_trade_count_for_full_confidence >= 1
    ),
    evaluation_backtest_snapshot_count_for_full_confidence INTEGER NOT NULL DEFAULT 60 CHECK (
        evaluation_backtest_snapshot_count_for_full_confidence >= 1
    ),
    evaluation_paper_live_snapshot_count_for_full_confidence INTEGER NOT NULL DEFAULT 30 CHECK (
        evaluation_paper_live_snapshot_count_for_full_confidence >= 1
    ),
    evaluation_backtest_trade_confidence_weight REAL NOT NULL DEFAULT 0.7 CHECK (
        evaluation_backtest_trade_confidence_weight >= 0 AND evaluation_backtest_trade_confidence_weight <= 1
    ),
    evaluation_backtest_snapshot_confidence_weight REAL NOT NULL DEFAULT 0.3 CHECK (
        evaluation_backtest_snapshot_confidence_weight >= 0 AND evaluation_backtest_snapshot_confidence_weight <= 1
    ),
    evaluation_backtest_evidence_weight REAL NOT NULL DEFAULT 0.6 CHECK (
        evaluation_backtest_evidence_weight >= 0 AND evaluation_backtest_evidence_weight <= 1
    ),
    evaluation_paper_live_evidence_weight REAL NOT NULL DEFAULT 0.4 CHECK (
        evaluation_paper_live_evidence_weight >= 0 AND evaluation_paper_live_evidence_weight <= 1
    ),
    promotion_min_research_backtest_trade_count INTEGER NOT NULL DEFAULT 10 CHECK (
        promotion_min_research_backtest_trade_count >= 1
    ),
    promotion_min_research_backtest_snapshot_count INTEGER NOT NULL DEFAULT 20 CHECK (
        promotion_min_research_backtest_snapshot_count >= 1
    ),
    promotion_min_research_backtest_return_pct REAL NOT NULL DEFAULT 0.0,
    promotion_min_research_max_drawdown_pct REAL NOT NULL DEFAULT -25.0,
    promotion_min_research_walk_forward_average_return_pct REAL NOT NULL DEFAULT 0.0,
    promotion_min_live_paper_snapshot_count INTEGER NOT NULL DEFAULT 10 CHECK (
        promotion_min_live_paper_snapshot_count >= 1
    ),
    promotion_min_live_overall_confidence REAL NOT NULL DEFAULT 0.6 CHECK (
        promotion_min_live_overall_confidence >= 0 AND promotion_min_live_overall_confidence <= 1
    ),
    updated_at TEXT
);
"""

# Snapshots are book-keyed; the account view is the roll-up across the
# account's books.
EQUITY_SNAPSHOTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS equity_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    snapshot_time TEXT NOT NULL,
    cash REAL NOT NULL,
    market_value REAL NOT NULL,
    equity REAL NOT NULL,
    realized_pnl REAL NOT NULL,
    unrealized_pnl REAL NOT NULL,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
    UNIQUE (book_id, snapshot_time)
);
"""

EQUITY_SNAPSHOTS_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_equity_snapshots_book_time
ON equity_snapshots(book_id, snapshot_time DESC);
"""

# The backtested strategy is a strategies FK, not a
# name string. Nullable — reads fall back to the account strategy when unset.
BACKTEST_RUNS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS backtest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    strategy_id INTEGER,
    run_name TEXT,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    slippage_bps REAL NOT NULL DEFAULT 0,
    fee_per_trade REAL NOT NULL DEFAULT 0,
    tickers_file TEXT,
    notes TEXT,
    warnings TEXT,
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    FOREIGN KEY (strategy_id) REFERENCES strategies(id)
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

# Fills key on the orders table; the shared submission + reconciliation paths
# write orders/order_fills (the legacy broker_orders table was dropped).
ORDER_FILLS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS order_fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    broker_fill_id TEXT,
    exec_id TEXT,
    filled_qty REAL NOT NULL,
    fill_price REAL NOT NULL,
    commission REAL NOT NULL DEFAULT 0,
    fill_time TEXT NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(id),
    UNIQUE (order_id, exec_id)
);
"""

BROKER_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_order_fills_order_id ON order_fills(order_id);
"""

STRATEGY_PARAM_SETS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS strategy_param_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name TEXT NOT NULL,
    version TEXT NOT NULL,
    params_json TEXT NOT NULL,
    config_version TEXT,
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    activated_at TEXT,
    deactivated_at TEXT,
    notes TEXT,
    UNIQUE(strategy_name, version)
);
"""

# Decisions are book-keyed and carry first-class decision_score /
# decision_confidence columns. Audit history — no cascade.
ROTATION_DECISIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS rotation_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    decision_time TEXT NOT NULL,
    incumbent_strategy_id INTEGER,
    challenger_strategy_id INTEGER,
    selected_strategy_id INTEGER,
    rotation_action TEXT NOT NULL CHECK (rotation_action IN ('hold', 'rotate')),
    cooldown_active INTEGER NOT NULL DEFAULT 0,
    decision_score REAL,
    decision_confidence REAL,
    score_components_json TEXT NOT NULL,
    gate_results_json TEXT NOT NULL,
    decision_reason TEXT,
    config_version TEXT,
    window_start TEXT,
    window_end TEXT,
    realized_pnl_delta REAL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE RESTRICT,
    FOREIGN KEY (incumbent_strategy_id) REFERENCES strategies(id),
    FOREIGN KEY (challenger_strategy_id) REFERENCES strategies(id),
    FOREIGN KEY (selected_strategy_id) REFERENCES strategies(id)
);
"""

ROTATION_DECISIONS_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_rotation_decisions_book_time
ON rotation_decisions(book_id, decision_time DESC);
CREATE INDEX IF NOT EXISTS idx_rotation_decisions_action_time_book
ON rotation_decisions(rotation_action, decision_time DESC);
"""

# Metrics are book-keyed; account-level rows live on the account's default
# book.
DAILY_METRICS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS daily_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    metric_date TEXT NOT NULL,
    return_pct REAL,
    drawdown_pct REAL,
    turnover_pct REAL,
    slippage_bps REAL,
    hit_rate REAL,
    expectancy REAL,
    risk_adjusted_score REAL,
    trade_count INTEGER,
    fees_total REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
    UNIQUE (book_id, metric_date)
);
"""

DAILY_METRICS_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_daily_metrics_book_date
ON daily_metrics(book_id, metric_date DESC);
"""

STRATEGY_PARAM_SETS_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_strategy_param_sets_strategy_active
ON strategy_param_sets(strategy_name, is_active);
"""

# The strategy is a strategies FK copied from the
# primary run; nullable so reads fall back to the account strategy when unset.
WALK_FORWARD_GROUPS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS walk_forward_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    grouping_key TEXT NOT NULL UNIQUE,
    account_id INTEGER NOT NULL,
    strategy_id INTEGER,
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
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    FOREIGN KEY (strategy_id) REFERENCES strategies(id)
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
ON walk_forward_groups(account_id, strategy_id, created_at DESC);
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

# ---------------------------------------------------------------------------
# Strategy-book schema (run `python -m scripts.data_ops.describe_db_schema`
# for the live shape).
# ---------------------------------------------------------------------------

BOOKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'closed')),
    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
    start_equity REAL NOT NULL,
    current_cash REAL NOT NULL,
    current_equity REAL NOT NULL,
    trade_universes TEXT,
    goal_min_return_pct REAL,
    goal_max_return_pct REAL,
    goal_period TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
    UNIQUE (account_id, name)
);
"""

BOOKS_INDEXES_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_books_default_per_account
ON books(account_id)
WHERE is_default = 1;
CREATE INDEX IF NOT EXISTS idx_books_account_status
ON books(account_id, status);
"""

BOOK_EXECUTION_SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS book_execution_settings (
    book_id INTEGER PRIMARY KEY,
    learning_enabled INTEGER NOT NULL DEFAULT 0 CHECK (learning_enabled IN (0, 1)),
    risk_policy TEXT NOT NULL DEFAULT 'none' CHECK (
        risk_policy IN ('none', 'fixed_stop', 'take_profit', 'stop_and_target')
    ),
    stop_loss_pct REAL,
    take_profit_pct REAL,
    profit_take_pct REAL,
    max_loss_pct REAL,
    trade_size_pct REAL,
    max_position_pct REAL,
    max_trades_per_run INTEGER CHECK (max_trades_per_run IS NULL OR max_trades_per_run >= 1),
    instrument_mode TEXT NOT NULL DEFAULT 'equity' CHECK (instrument_mode IN ('equity', 'leaps')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
);
"""

BOOK_OPTION_SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS book_option_settings (
    book_id INTEGER PRIMARY KEY,
    option_strike_offset_pct REAL,
    option_min_dte INTEGER,
    option_max_dte INTEGER,
    option_type TEXT CHECK (option_type IS NULL OR option_type IN ('call', 'put')),
    target_delta_min REAL,
    target_delta_max REAL,
    max_premium_per_trade REAL,
    max_contracts_per_trade INTEGER,
    iv_rank_min REAL,
    iv_rank_max REAL,
    roll_dte_threshold INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
);
"""

BOOK_ROTATION_SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS book_rotation_settings (
    book_id INTEGER PRIMARY KEY,
    rotation_enabled INTEGER NOT NULL DEFAULT 0 CHECK (rotation_enabled IN (0, 1)),
    rotation_mode TEXT,
    rotation_optimality_mode TEXT,
    rotation_interval_days INTEGER,
    rotation_interval_minutes INTEGER,
    rotation_lookback_days INTEGER,
    rotation_schedule TEXT,
    min_trades_in_window INTEGER,
    outperformance_threshold_bps REAL,
    cooldown_days INTEGER,
    risk_adjusted_return_weight REAL,
    stability_weight REAL,
    drawdown_penalty_weight REAL,
    cost_penalty_weight REAL,
    regime_fit_weight REAL,
    regime_strategy_risk_on_id INTEGER,
    regime_strategy_neutral_id INTEGER,
    regime_strategy_risk_off_id INTEGER,
    overlay_mode TEXT,
    overlay_min_tickers INTEGER,
    overlay_confidence_threshold REAL,
    overlay_watchlist TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
    FOREIGN KEY (regime_strategy_risk_on_id) REFERENCES strategies(id),
    FOREIGN KEY (regime_strategy_neutral_id) REFERENCES strategies(id),
    FOREIGN KEY (regime_strategy_risk_off_id) REFERENCES strategies(id)
);
"""

STRATEGIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_key TEXT NOT NULL UNIQUE,
    primitive TEXT NOT NULL,
    params_json TEXT NOT NULL,
    style TEXT NOT NULL CHECK (style IN ('trend', 'mean_reversion', 'neutral', 'alternative')),
    required_features TEXT,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'frozen', 'retired')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

FEATURE_PROVIDERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS feature_providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_key TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
    config_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

BOOK_STRATEGY_ASSIGNMENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS book_strategy_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    strategy_id INTEGER NOT NULL,
    param_set_id INTEGER,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    is_incumbent INTEGER NOT NULL DEFAULT 1 CHECK (is_incumbent IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
    FOREIGN KEY (strategy_id) REFERENCES strategies(id),
    FOREIGN KEY (param_set_id) REFERENCES strategy_param_sets(id)
);
"""

BOOK_STRATEGY_ASSIGNMENTS_INDEXES_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_book_assignments_open_per_book
ON book_strategy_assignments(book_id)
WHERE effective_to IS NULL;
CREATE INDEX IF NOT EXISTS idx_book_assignments_book_effective
ON book_strategy_assignments(book_id, effective_from DESC);
CREATE INDEX IF NOT EXISTS idx_book_assignments_strategy_effective
ON book_strategy_assignments(strategy_id, effective_from DESC);
"""

ORDERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    strategy_id INTEGER,
    rotation_decision_id INTEGER,
    broker_order_id TEXT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    qty REAL NOT NULL,
    order_type TEXT NOT NULL DEFAULT 'market' CHECK (order_type IN ('market', 'limit')),
    time_in_force TEXT NOT NULL DEFAULT 'day' CHECK (time_in_force IN ('day', 'gtc')),
    requested_price REAL,
    status TEXT NOT NULL CHECK (
        status IN ('submitted', 'partially_filled', 'filled', 'rejected', 'cancelled')
    ),
    filled_qty REAL NOT NULL DEFAULT 0,
    avg_fill_price REAL,
    commission REAL NOT NULL DEFAULT 0,
    submitted_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
    FOREIGN KEY (strategy_id) REFERENCES strategies(id)
);
"""

ORDERS_INDEXES_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_account_broker_order_id
ON orders(account_id, broker_order_id)
WHERE broker_order_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_orders_account_status_submitted
ON orders(account_id, status, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_book_submitted
ON orders(book_id, submitted_at DESC);
"""

POSITIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS positions (
    book_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    qty REAL NOT NULL,
    avg_cost REAL NOT NULL,
    market_value REAL NOT NULL,
    unrealized_pnl REAL NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (book_id, symbol),
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
);
"""

POSITIONS_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_positions_symbol_updated
ON positions(symbol, updated_at DESC);
"""

LEDGER_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    entry_type TEXT NOT NULL CHECK (
        entry_type IN ('trade', 'fee', 'deposit', 'withdrawal', 'adjustment')
    ),
    amount REAL NOT NULL,
    reference_type TEXT,
    reference_id TEXT,
    entry_time TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
);
"""

LEDGER_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_ledger_book_entry_time
ON ledger(book_id, entry_time DESC);
CREATE INDEX IF NOT EXISTS idx_ledger_reference
ON ledger(reference_type, reference_id);
"""

RISK_SNAPSHOTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS risk_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    snapshot_time TEXT NOT NULL,
    gross_exposure REAL NOT NULL,
    net_exposure REAL NOT NULL,
    max_symbol_concentration_pct REAL NOT NULL,
    max_sector_concentration_pct REAL NOT NULL,
    drawdown_pct REAL,
    leverage_proxy REAL,
    daily_loss_pct REAL,
    kill_switch_triggered INTEGER NOT NULL DEFAULT 0 CHECK (kill_switch_triggered IN (0, 1)),
    risk_payload_json TEXT NOT NULL,
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    UNIQUE (account_id, snapshot_time)
);
"""

RISK_DECISIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS risk_decisions (
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
    requested_notional REAL,
    approved_notional REAL,
    risk_payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    FOREIGN KEY (book_id) REFERENCES books(id)
);
"""

RISK_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_risk_snapshots_account_time
ON risk_snapshots(account_id, snapshot_time DESC);
CREATE INDEX IF NOT EXISTS idx_risk_decisions_account_time
ON risk_decisions(account_id, decision_time DESC);
CREATE INDEX IF NOT EXISTS idx_risk_decisions_book_time
ON risk_decisions(book_id, decision_time DESC);
"""

SCHEMA_SQL = "\n".join(
    (
        ACCOUNTS_TABLE_SQL,
        TRADES_TABLE_SQL,
        TRADES_INDEXES_SQL,
        GLOBAL_SETTINGS_TABLE_SQL,
        EQUITY_SNAPSHOTS_TABLE_SQL,
        EQUITY_SNAPSHOTS_INDEXES_SQL,
        BACKTEST_RUNS_TABLE_SQL,
        BACKTEST_TRADES_TABLE_SQL,
        BACKTEST_EQUITY_SNAPSHOTS_TABLE_SQL,
        BACKTEST_INDEXES_SQL,
        ORDER_FILLS_TABLE_SQL,
        BROKER_INDEXES_SQL,
        STRATEGY_PARAM_SETS_TABLE_SQL,
        ROTATION_DECISIONS_TABLE_SQL,
        ROTATION_DECISIONS_INDEXES_SQL,
        DAILY_METRICS_TABLE_SQL,
        DAILY_METRICS_INDEXES_SQL,
        STRATEGY_PARAM_SETS_INDEXES_SQL,
        WALK_FORWARD_GROUPS_TABLE_SQL,
        WALK_FORWARD_GROUP_RUNS_TABLE_SQL,
        WALK_FORWARD_INDEXES_SQL,
        PROMOTION_REVIEWS_TABLE_SQL,
        PROMOTION_REVIEW_EVENTS_TABLE_SQL,
        PROMOTION_REVIEW_INDEXES_SQL,
        # Strategy-book schema: strategies before book_rotation_settings
        # and book_strategy_assignments (FK targets); books before its
        # dependents.
        BOOKS_TABLE_SQL,
        BOOKS_INDEXES_SQL,
        STRATEGIES_TABLE_SQL,
        FEATURE_PROVIDERS_TABLE_SQL,
        BOOK_EXECUTION_SETTINGS_TABLE_SQL,
        BOOK_OPTION_SETTINGS_TABLE_SQL,
        BOOK_ROTATION_SETTINGS_TABLE_SQL,
        BOOK_STRATEGY_ASSIGNMENTS_TABLE_SQL,
        BOOK_STRATEGY_ASSIGNMENTS_INDEXES_SQL,
        ORDERS_TABLE_SQL,
        ORDERS_INDEXES_SQL,
        POSITIONS_TABLE_SQL,
        POSITIONS_INDEXES_SQL,
        LEDGER_TABLE_SQL,
        LEDGER_INDEXES_SQL,
        RISK_SNAPSHOTS_TABLE_SQL,
        RISK_DECISIONS_TABLE_SQL,
        RISK_INDEXES_SQL,
    )
)
