from dataclasses import dataclass

from trading.database.db_common import DEFAULT_ROTATION_OVERLAY_WATCHLIST_JSON


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
    ColumnMigration("goal_min_return_pct", "ALTER TABLE accounts ADD COLUMN goal_min_return_pct REAL"),
    ColumnMigration("goal_max_return_pct", "ALTER TABLE accounts ADD COLUMN goal_max_return_pct REAL"),
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
    ColumnMigration("rotation_schedule", "ALTER TABLE accounts ADD COLUMN rotation_schedule TEXT"),
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
        "rotation_overlay_watchlist",
        f"ALTER TABLE accounts ADD COLUMN rotation_overlay_watchlist TEXT NOT NULL DEFAULT '{DEFAULT_ROTATION_OVERLAY_WATCHLIST_JSON}'",
        (
            f"UPDATE accounts SET rotation_overlay_watchlist = '{DEFAULT_ROTATION_OVERLAY_WATCHLIST_JSON}' "
            "WHERE rotation_overlay_watchlist IS NULL OR TRIM(rotation_overlay_watchlist) = ''",
        ),
    ),
    ColumnMigration(
        "rotation_active_index",
        "ALTER TABLE accounts ADD COLUMN rotation_active_index INTEGER NOT NULL DEFAULT 0",
    ),
    ColumnMigration("rotation_last_at", "ALTER TABLE accounts ADD COLUMN rotation_last_at TEXT"),
    ColumnMigration(
        "rotation_active_strategy",
        "ALTER TABLE accounts ADD COLUMN rotation_active_strategy TEXT",
    ),
    ColumnMigration("trade_size_pct", "ALTER TABLE accounts ADD COLUMN trade_size_pct REAL"),
    ColumnMigration("max_position_pct", "ALTER TABLE accounts ADD COLUMN max_position_pct REAL"),
)

BACKTEST_RUN_MIGRATIONS = (
    ColumnMigration(
        "strategy_name",
        "ALTER TABLE backtest_runs ADD COLUMN strategy_name TEXT",
    ),
)

ACCOUNT_BROKER_MIGRATIONS = (
    ColumnMigration(
        "broker_type",
        "ALTER TABLE accounts ADD COLUMN broker_type TEXT NOT NULL DEFAULT 'paper'",
    ),
    ColumnMigration("broker_host", "ALTER TABLE accounts ADD COLUMN broker_host TEXT"),
    ColumnMigration("broker_port", "ALTER TABLE accounts ADD COLUMN broker_port INTEGER"),
    ColumnMigration("broker_client_id", "ALTER TABLE accounts ADD COLUMN broker_client_id INTEGER"),
    ColumnMigration(
        "live_trading_enabled",
        "ALTER TABLE accounts ADD COLUMN live_trading_enabled INTEGER NOT NULL DEFAULT 0",
    ),
)

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

GLOBAL_SETTINGS_MIGRATIONS = (
    ColumnMigration(
        "evaluation_backtest_trade_count_for_full_confidence",
        "ALTER TABLE global_settings ADD COLUMN evaluation_backtest_trade_count_for_full_confidence INTEGER NOT NULL DEFAULT 50",
    ),
    ColumnMigration(
        "evaluation_backtest_snapshot_count_for_full_confidence",
        "ALTER TABLE global_settings ADD COLUMN evaluation_backtest_snapshot_count_for_full_confidence INTEGER NOT NULL DEFAULT 60",
    ),
    ColumnMigration(
        "evaluation_paper_live_snapshot_count_for_full_confidence",
        "ALTER TABLE global_settings ADD COLUMN evaluation_paper_live_snapshot_count_for_full_confidence INTEGER NOT NULL DEFAULT 30",
    ),
    ColumnMigration(
        "evaluation_backtest_trade_confidence_weight",
        "ALTER TABLE global_settings ADD COLUMN evaluation_backtest_trade_confidence_weight REAL NOT NULL DEFAULT 0.7",
    ),
    ColumnMigration(
        "evaluation_backtest_snapshot_confidence_weight",
        "ALTER TABLE global_settings ADD COLUMN evaluation_backtest_snapshot_confidence_weight REAL NOT NULL DEFAULT 0.3",
    ),
    ColumnMigration(
        "evaluation_backtest_evidence_weight",
        "ALTER TABLE global_settings ADD COLUMN evaluation_backtest_evidence_weight REAL NOT NULL DEFAULT 0.6",
    ),
    ColumnMigration(
        "evaluation_paper_live_evidence_weight",
        "ALTER TABLE global_settings ADD COLUMN evaluation_paper_live_evidence_weight REAL NOT NULL DEFAULT 0.4",
    ),
    ColumnMigration(
        "promotion_min_research_backtest_trade_count",
        "ALTER TABLE global_settings ADD COLUMN promotion_min_research_backtest_trade_count INTEGER NOT NULL DEFAULT 10",
    ),
    ColumnMigration(
        "promotion_min_research_backtest_snapshot_count",
        "ALTER TABLE global_settings ADD COLUMN promotion_min_research_backtest_snapshot_count INTEGER NOT NULL DEFAULT 20",
    ),
    ColumnMigration(
        "promotion_min_research_backtest_return_pct",
        "ALTER TABLE global_settings ADD COLUMN promotion_min_research_backtest_return_pct REAL NOT NULL DEFAULT 0.0",
    ),
    ColumnMigration(
        "promotion_min_research_max_drawdown_pct",
        "ALTER TABLE global_settings ADD COLUMN promotion_min_research_max_drawdown_pct REAL NOT NULL DEFAULT -25.0",
    ),
    ColumnMigration(
        "promotion_min_research_walk_forward_average_return_pct",
        "ALTER TABLE global_settings ADD COLUMN promotion_min_research_walk_forward_average_return_pct REAL NOT NULL DEFAULT 0.0",
    ),
    ColumnMigration(
        "promotion_min_live_paper_snapshot_count",
        "ALTER TABLE global_settings ADD COLUMN promotion_min_live_paper_snapshot_count INTEGER NOT NULL DEFAULT 10",
    ),
    ColumnMigration(
        "promotion_min_live_overall_confidence",
        "ALTER TABLE global_settings ADD COLUMN promotion_min_live_overall_confidence REAL NOT NULL DEFAULT 0.6",
    ),
)
