from __future__ import annotations
import json
import sqlite3
from dataclasses import dataclass

from common.paths.project_paths import TRADE_UNIVERSE_PATH
from common.tickers import load_tickers_from_file

# Default source used to seed account-level overlay watchlists so regime overlays
# can evaluate a stable baseline universe even before the account accumulates holdings.
# Mirrors trading.services.profile_source.DEFAULT_TICKERS_FILE — same file, different semantic name.
DEFAULT_ROTATION_OVERLAY_WATCHLIST_FILE = str(TRADE_UNIVERSE_PATH)

# Canonical seeded overlay watchlist shared by new-account defaults and account
# backfills when the watchlist column is introduced by migration.
DEFAULT_ROTATION_OVERLAY_WATCHLIST = load_tickers_from_file(DEFAULT_ROTATION_OVERLAY_WATCHLIST_FILE)
DEFAULT_ROTATION_OVERLAY_WATCHLIST_JSON = json.dumps(
    DEFAULT_ROTATION_OVERLAY_WATCHLIST,
    separators=(",", ":"),
)


@dataclass(frozen=True)
class ColumnMigration:
    column_name: str
    ddl: str
    post_sql: tuple[str, ...] = ()


def _fk_delete_action(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
    references_table: str,
) -> str | None:
    rows = conn.execute(f"PRAGMA foreign_key_list({table_name})").fetchall()
    for row in rows:
        if str(row[3]) == column_name and str(row[2]) == references_table:
            return str(row[6]).upper()
    return None


def _run_rebuild(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    create_sql: str,
    copy_sql: str,
    index_sql: str = "",
) -> None:
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN")
    try:
        conn.execute(create_sql)
        conn.execute(copy_sql)
        conn.execute(f"DROP TABLE {table_name}")
        conn.execute(f"ALTER TABLE {table_name}_new RENAME TO {table_name}")
        for stmt in index_sql.split(";"):
            if stmt.strip():
                conn.execute(stmt)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")

    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError(f"Foreign-key violations after {table_name} rebuild: {violations!r}")


def ensure_order_fills_order_delete_cascade(conn: sqlite3.Connection) -> None:
    if _fk_delete_action(conn, "order_fills", "order_id", "orders") == "CASCADE":
        return

    _run_rebuild(
        conn,
        table_name="order_fills",
        create_sql="""
            CREATE TABLE order_fills_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                broker_fill_id TEXT,
                exec_id TEXT,
                filled_qty REAL NOT NULL,
                fill_price REAL NOT NULL,
                commission REAL NOT NULL DEFAULT 0,
                fill_time TEXT NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
                UNIQUE (order_id, exec_id)
            )
        """,
        copy_sql="""
            INSERT INTO order_fills_new (
                id, order_id, broker_fill_id, exec_id, filled_qty,
                fill_price, commission, fill_time
            )
            SELECT
                id, order_id, broker_fill_id, exec_id, filled_qty,
                fill_price, commission, fill_time
            FROM order_fills
        """,
        index_sql="CREATE INDEX IF NOT EXISTS idx_order_fills_order_id ON order_fills(order_id);",
    )


def ensure_backtest_run_child_delete_cascades(conn: sqlite3.Connection) -> None:
    if _fk_delete_action(conn, "backtest_trades", "run_id", "backtest_runs") != "CASCADE":
        _run_rebuild(
            conn,
            table_name="backtest_trades",
            create_sql="""
                CREATE TABLE backtest_trades_new (
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
                    FOREIGN KEY (run_id) REFERENCES backtest_runs(id) ON DELETE CASCADE
                )
            """,
            copy_sql="""
                INSERT INTO backtest_trades_new (
                    id, run_id, trade_time, ticker, side, qty, price, fee, slippage_bps, note
                )
                SELECT id, run_id, trade_time, ticker, side, qty, price, fee, slippage_bps, note
                FROM backtest_trades
            """,
            index_sql="CREATE INDEX IF NOT EXISTS idx_backtest_trades_run_id ON backtest_trades(run_id);",
        )

    if _fk_delete_action(conn, "backtest_equity_snapshots", "run_id", "backtest_runs") != "CASCADE":
        _run_rebuild(
            conn,
            table_name="backtest_equity_snapshots",
            create_sql="""
                CREATE TABLE backtest_equity_snapshots_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    snapshot_time TEXT NOT NULL,
                    cash REAL NOT NULL,
                    market_value REAL NOT NULL,
                    equity REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    unrealized_pnl REAL NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES backtest_runs(id) ON DELETE CASCADE
                )
            """,
            copy_sql="""
                INSERT INTO backtest_equity_snapshots_new (
                    id, run_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
                )
                SELECT id, run_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
                FROM backtest_equity_snapshots
            """,
            index_sql=(
                "CREATE INDEX IF NOT EXISTS idx_backtest_equity_run_id "
                "ON backtest_equity_snapshots(run_id);"
            ),
        )


def ensure_promotion_review_events_delete_cascade(conn: sqlite3.Connection) -> None:
    if _fk_delete_action(conn, "promotion_review_events", "review_id", "promotion_reviews") == "CASCADE":
        return

    _run_rebuild(
        conn,
        table_name="promotion_review_events",
        create_sql="""
            CREATE TABLE promotion_review_events_new (
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
                FOREIGN KEY (review_id) REFERENCES promotion_reviews(id) ON DELETE CASCADE,
                UNIQUE(review_id, event_seq)
            )
        """,
        copy_sql="""
            INSERT INTO promotion_review_events_new (
                id, review_id, event_seq, event_type, actor_type, actor_name,
                from_review_state, to_review_state, note, event_payload, created_at
            )
            SELECT
                id, review_id, event_seq, event_type, actor_type, actor_name,
                from_review_state, to_review_state, note, event_payload, created_at
            FROM promotion_review_events
        """,
        index_sql="""
            CREATE INDEX IF NOT EXISTS idx_promotion_review_events_review_seq
            ON promotion_review_events(review_id, event_seq ASC);
            CREATE INDEX IF NOT EXISTS idx_promotion_review_events_review_created
            ON promotion_review_events(review_id, created_at ASC);
        """,
    )


def ensure_walk_forward_group_runs_delete_cascade(conn: sqlite3.Connection) -> None:
    if _fk_delete_action(conn, "walk_forward_group_runs", "group_id", "walk_forward_groups") == "CASCADE":
        return

    _run_rebuild(
        conn,
        table_name="walk_forward_group_runs",
        create_sql="""
            CREATE TABLE walk_forward_group_runs_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                run_id INTEGER NOT NULL UNIQUE,
                window_index INTEGER NOT NULL,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                total_return_pct REAL NOT NULL,
                FOREIGN KEY (group_id) REFERENCES walk_forward_groups(id) ON DELETE CASCADE,
                FOREIGN KEY (run_id) REFERENCES backtest_runs(id),
                UNIQUE(group_id, window_index)
            )
        """,
        copy_sql="""
            INSERT INTO walk_forward_group_runs_new (
                id, group_id, run_id, window_index, window_start, window_end, total_return_pct
            )
            SELECT id, group_id, run_id, window_index, window_start, window_end, total_return_pct
            FROM walk_forward_group_runs
        """,
        index_sql="""
            CREATE INDEX IF NOT EXISTS idx_walk_forward_group_runs_group_window
            ON walk_forward_group_runs(group_id, window_index ASC);
        """,
    )


def ensure_table_rebuild_migrations(conn: sqlite3.Connection) -> None:
    ensure_order_fills_order_delete_cascade(conn)
    ensure_backtest_run_child_delete_cascades(conn)
    ensure_promotion_review_events_delete_cascade(conn)
    ensure_walk_forward_group_runs_delete_cascade(conn)


ACCOUNT_MIGRATIONS = (
    ColumnMigration(
        "account_kind",
        "ALTER TABLE accounts ADD COLUMN account_kind TEXT NOT NULL DEFAULT 'managed'",
    ),
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
        (
            "ALTER TABLE accounts ADD COLUMN rotation_overlay_watchlist TEXT NOT NULL DEFAULT "
            f"'{DEFAULT_ROTATION_OVERLAY_WATCHLIST_JSON}'"
        ),
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
    ColumnMigration("trade_universes", "ALTER TABLE accounts ADD COLUMN trade_universes TEXT"),
)

# BACKTEST_RUN_MIGRATIONS retired with the clean-schema swap: backtest_runs
# keys the backtested strategy as a strategies FK (strategy_id) in the DDL,
# replacing the additive strategy_name column.
BACKTEST_RUN_MIGRATIONS: tuple[ColumnMigration, ...] = ()

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
    # Clean-schema custody columns.
    ColumnMigration(
        "base_ccy",
        "ALTER TABLE accounts ADD COLUMN base_ccy TEXT NOT NULL DEFAULT 'USD'",
    ),
    ColumnMigration("updated_at", "ALTER TABLE accounts ADD COLUMN updated_at TEXT"),
)

# ORDER_FILL_MIGRATIONS retired with the clean-schema order_fills swap:
# the table is order-keyed with exec_id + its unique constraint in the DDL.

GLOBAL_SETTINGS_MIGRATIONS = (
    ColumnMigration(
        "evaluation_backtest_trade_count_for_full_confidence",
        (
            "ALTER TABLE global_settings ADD COLUMN"
            " evaluation_backtest_trade_count_for_full_confidence INTEGER NOT NULL DEFAULT 50"
        ),
    ),
    ColumnMigration(
        "evaluation_backtest_snapshot_count_for_full_confidence",
        (
            "ALTER TABLE global_settings ADD COLUMN"
            " evaluation_backtest_snapshot_count_for_full_confidence INTEGER NOT NULL DEFAULT 60"
        ),
    ),
    ColumnMigration(
        "evaluation_paper_live_snapshot_count_for_full_confidence",
        (
            "ALTER TABLE global_settings ADD COLUMN"
            " evaluation_paper_live_snapshot_count_for_full_confidence INTEGER NOT NULL DEFAULT 30"
        ),
    ),
    ColumnMigration(
        "evaluation_backtest_trade_confidence_weight",
        "ALTER TABLE global_settings ADD COLUMN evaluation_backtest_trade_confidence_weight REAL NOT NULL DEFAULT 0.7",
    ),
    ColumnMigration(
        "evaluation_backtest_snapshot_confidence_weight",
        (
            "ALTER TABLE global_settings ADD COLUMN"
            " evaluation_backtest_snapshot_confidence_weight REAL NOT NULL DEFAULT 0.3"
        ),
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
        (
            "ALTER TABLE global_settings ADD COLUMN"
            " promotion_min_research_backtest_trade_count INTEGER NOT NULL DEFAULT 10"
        ),
    ),
    ColumnMigration(
        "promotion_min_research_backtest_snapshot_count",
        (
            "ALTER TABLE global_settings ADD COLUMN"
            " promotion_min_research_backtest_snapshot_count INTEGER NOT NULL DEFAULT 20"
        ),
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
        (
            "ALTER TABLE global_settings ADD COLUMN"
            " promotion_min_research_walk_forward_average_return_pct REAL NOT NULL DEFAULT 0.0"
        ),
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

# Placeholder hooks for future additive column migrations on these tables.
# New ColumnMigration entries should be appended in place.
TABLE_MIGRATIONS_BY_TABLE: dict[str, tuple[ColumnMigration, ...]] = {
    "strategy_param_sets": (),
    "rotation_decisions": (),
    "daily_metrics": (),
}

# Additive column migrations for the clean book tables (greenfield CREATEs cover
# fresh DBs; these bring existing DBs up to the current shape).
BOOK_MIGRATIONS_BY_TABLE: dict[str, tuple[ColumnMigration, ...]] = {
    # param_set_id: legacy and unused since the strategy catalog became canonical (a strategy row is its own
    # parameterization); the column is left NULL and persists only until a
    # data-op drops it, so existing DBs keep matching the schema DDL.
    "book_strategy_assignments": (
        ColumnMigration("param_set_id", "ALTER TABLE book_strategy_assignments ADD COLUMN param_set_id INTEGER"),
    ),
    # Rotation policy (score weights, threshold, cooldown, min-trades),
    # migrated out of code-only RotationPolicyConfig defaults. All nullable —
    # NULL means "use the code default", preserving current behavior for
    # existing rows and fresh installs alike.
    "book_rotation_settings": (
        ColumnMigration(
            "min_trades_in_window",
            "ALTER TABLE book_rotation_settings ADD COLUMN min_trades_in_window INTEGER",
        ),
        ColumnMigration(
            "outperformance_threshold_bps",
            "ALTER TABLE book_rotation_settings ADD COLUMN outperformance_threshold_bps REAL",
        ),
        ColumnMigration(
            "cooldown_days",
            "ALTER TABLE book_rotation_settings ADD COLUMN cooldown_days INTEGER",
        ),
        ColumnMigration(
            "risk_adjusted_return_weight",
            "ALTER TABLE book_rotation_settings ADD COLUMN risk_adjusted_return_weight REAL",
        ),
        ColumnMigration(
            "stability_weight",
            "ALTER TABLE book_rotation_settings ADD COLUMN stability_weight REAL",
        ),
        ColumnMigration(
            "drawdown_penalty_weight",
            "ALTER TABLE book_rotation_settings ADD COLUMN drawdown_penalty_weight REAL",
        ),
        ColumnMigration(
            "cost_penalty_weight",
            "ALTER TABLE book_rotation_settings ADD COLUMN cost_penalty_weight REAL",
        ),
        ColumnMigration(
            "regime_fit_weight",
            "ALTER TABLE book_rotation_settings ADD COLUMN regime_fit_weight REAL",
        ),
    ),
}
