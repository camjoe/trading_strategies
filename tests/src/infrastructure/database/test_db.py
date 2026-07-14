from pathlib import Path

import pytest

from infrastructure.database.backend import SQLiteBackend, get_backend, set_backend
from infrastructure.database.init import _column_names, _ensure_column, ensure_db, init_schema
from infrastructure.database.migrations import (
    ACCOUNT_MIGRATIONS,
    DEFAULT_ROTATION_OVERLAY_WATCHLIST_JSON,
    ensure_order_fills_order_delete_cascade,
)


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
    conn = ensure_db()
    try:
        table_rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name ASC").fetchall()
        names = {str(row["name"]) for row in table_rows}

        assert "accounts" in names
        assert "trades" in names
        assert "global_settings" in names
        assert "equity_snapshots" in names
        assert "backtest_runs" in names
        assert "backtest_trades" in names
        assert "backtest_equity_snapshots" in names
        assert "promotion_reviews" in names
        assert "promotion_review_events" in names
    finally:
        conn.close()


def _fk_delete_action(conn, table_name: str, column_name: str, references_table: str) -> str | None:
    for row in conn.execute(f"PRAGMA foreign_key_list({table_name})").fetchall():
        if row["from"] == column_name and row["table"] == references_table:
            return str(row["on_delete"]).upper()
    return None


def test_fresh_schema_child_owned_foreign_keys_cascade(sqlite_backend: SQLiteBackend) -> None:
    conn = ensure_db()
    try:
        assert _fk_delete_action(conn, "order_fills", "order_id", "orders") == "CASCADE"
        assert _fk_delete_action(conn, "backtest_trades", "run_id", "backtest_runs") == "CASCADE"
        assert _fk_delete_action(conn, "backtest_equity_snapshots", "run_id", "backtest_runs") == "CASCADE"
        assert _fk_delete_action(conn, "promotion_review_events", "review_id", "promotion_reviews") == "CASCADE"
        assert _fk_delete_action(conn, "walk_forward_group_runs", "group_id", "walk_forward_groups") == "CASCADE"
        assert _fk_delete_action(conn, "walk_forward_group_runs", "run_id", "backtest_runs") == "NO ACTION"
    finally:
        conn.close()


def test_init_schema_rebuilds_legacy_child_owned_foreign_keys(sqlite_backend: SQLiteBackend) -> None:
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
            CREATE TABLE orders (
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
                updated_at TEXT NOT NULL
            );
            CREATE TABLE order_fills (
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
            CREATE INDEX idx_order_fills_order_id ON order_fills(order_id);
            CREATE TABLE backtest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                run_name TEXT,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE backtest_trades (
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
            CREATE INDEX idx_backtest_trades_run_id ON backtest_trades(run_id);
            CREATE TABLE backtest_equity_snapshots (
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
            CREATE INDEX idx_backtest_equity_run_id ON backtest_equity_snapshots(run_id);
            CREATE TABLE promotion_reviews (
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
            CREATE TABLE promotion_review_events (
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
            CREATE INDEX idx_promotion_review_events_review_seq
            ON promotion_review_events(review_id, event_seq ASC);
            CREATE INDEX idx_promotion_review_events_review_created
            ON promotion_review_events(review_id, created_at ASC);
            CREATE TABLE walk_forward_groups (
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
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            );
            CREATE TABLE walk_forward_group_runs (
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
            CREATE INDEX idx_walk_forward_group_runs_group_window
            ON walk_forward_group_runs(group_id, window_index ASC);

            INSERT INTO accounts (id, name, strategy, initial_cash, created_at)
            VALUES (1, 'acct_legacy_cascade', 'trend', 1000, '2026-01-01T00:00:00Z');
            INSERT INTO orders (
                id, book_id, account_id, symbol, side, qty, status, submitted_at, updated_at
            ) VALUES (1, 1, 1, 'SPY', 'buy', 1, 'filled', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
            INSERT INTO order_fills (order_id, exec_id, filled_qty, fill_price, fill_time)
            VALUES (1, 'exec-1', 1, 100, '2026-01-01T00:00:00Z');
            INSERT INTO backtest_runs (id, account_id, start_date, end_date, created_at)
            VALUES (1, 1, '2026-01-01', '2026-01-31', '2026-02-01T00:00:00Z');
            INSERT INTO backtest_trades (run_id, trade_time, ticker, side, qty, price)
            VALUES (1, '2026-01-02T00:00:00Z', 'SPY', 'buy', 1, 400);
            INSERT INTO backtest_equity_snapshots (
                run_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
            ) VALUES (1, '2026-01-02T00:00:00Z', 600, 400, 1000, 0, 0);
            INSERT INTO promotion_reviews (
                id, account_id, account_name_snapshot, strategy_name, assessment_stage,
                assessment_status, promotion_assessment_version, evaluation_artifact_version,
                frozen_assessment_payload, frozen_evaluation_payload, created_at, updated_at
            ) VALUES (
                1, 1, 'acct_legacy_cascade', 'trend', 'research', 'pass',
                'v1', 'v1', '{}', '{}', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z'
            );
            INSERT INTO promotion_review_events (review_id, event_seq, event_type, created_at)
            VALUES (1, 1, 'created', '2026-01-01T00:00:00Z');
            INSERT INTO walk_forward_groups (
                id, grouping_key, account_id, start_date, end_date, test_months,
                step_months, window_count, average_return_pct, median_return_pct,
                best_return_pct, worst_return_pct, created_at
            ) VALUES (
                1, 'wf-1', 1, '2026-01-01', '2026-03-31', 1, 1, 1, 1, 1, 2, -1,
                '2026-04-01T00:00:00Z'
            );
            INSERT INTO walk_forward_group_runs (
                group_id, run_id, window_index, window_start, window_end, total_return_pct
            ) VALUES (1, 1, 0, '2026-01-01', '2026-01-31', 1);
            """
        )

        init_schema(conn)

        assert _fk_delete_action(conn, "order_fills", "order_id", "orders") == "CASCADE"
        assert _fk_delete_action(conn, "backtest_trades", "run_id", "backtest_runs") == "CASCADE"
        assert _fk_delete_action(conn, "backtest_equity_snapshots", "run_id", "backtest_runs") == "CASCADE"
        assert _fk_delete_action(conn, "promotion_review_events", "review_id", "promotion_reviews") == "CASCADE"
        assert _fk_delete_action(conn, "walk_forward_group_runs", "group_id", "walk_forward_groups") == "CASCADE"

        assert conn.execute("SELECT COUNT(*) FROM order_fills").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM backtest_trades").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM backtest_equity_snapshots").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM promotion_review_events").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM walk_forward_group_runs").fetchone()[0] == 1

        conn.execute("DELETE FROM orders WHERE id = 1")
        assert conn.execute("SELECT COUNT(*) FROM order_fills").fetchone()[0] == 0
        conn.execute("DELETE FROM promotion_reviews WHERE id = 1")
        assert conn.execute("SELECT COUNT(*) FROM promotion_review_events").fetchone()[0] == 0
        conn.execute("DELETE FROM walk_forward_groups WHERE id = 1")
        assert conn.execute("SELECT COUNT(*) FROM walk_forward_group_runs").fetchone()[0] == 0
        conn.execute("DELETE FROM backtest_runs WHERE id = 1")
        assert conn.execute("SELECT COUNT(*) FROM backtest_trades").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM backtest_equity_snapshots").fetchone()[0] == 0
    finally:
        conn.close()


def _create_legacy_order_fills_schema(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
            qty REAL NOT NULL,
            status TEXT NOT NULL,
            filled_qty REAL NOT NULL DEFAULT 0,
            commission REAL NOT NULL DEFAULT 0,
            submitted_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE order_fills (
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
        INSERT INTO orders (
            id, book_id, account_id, symbol, side, qty, status, submitted_at, updated_at
        ) VALUES (1, 1, 1, 'SPY', 'buy', 1, 'filled', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
        INSERT INTO order_fills (order_id, exec_id, filled_qty, fill_price, fill_time)
        VALUES (1, 'exec-1', 1, 100, '2026-01-01T00:00:00Z');
        """
    )


def test_table_rebuild_rejects_open_transaction(sqlite_backend: SQLiteBackend) -> None:
    conn = sqlite_backend.open_connection()
    try:
        _create_legacy_order_fills_schema(conn)

        conn.execute("BEGIN")
        conn.execute("UPDATE orders SET filled_qty = 2 WHERE id = 1")
        with pytest.raises(RuntimeError, match="open transaction"):
            ensure_order_fills_order_delete_cascade(conn)
        conn.rollback()

        # Legacy FK action untouched by the rejected attempt; succeeds once clean.
        assert _fk_delete_action(conn, "order_fills", "order_id", "orders") == "NO ACTION"
        ensure_order_fills_order_delete_cascade(conn)
        assert _fk_delete_action(conn, "order_fills", "order_id", "orders") == "CASCADE"
    finally:
        conn.close()


def test_table_rebuild_rolls_back_on_foreign_key_violation(sqlite_backend: SQLiteBackend) -> None:
    conn = sqlite_backend.open_connection()
    try:
        _create_legacy_order_fills_schema(conn)

        # Seed an orphaned fill (no matching order) with enforcement off, mimicking
        # a legacy database that predates FK enforcement.
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            """
            INSERT INTO order_fills (order_id, exec_id, filled_qty, fill_price, fill_time)
            VALUES (999, 'exec-orphan', 1, 100, '2026-01-01T00:00:00Z')
            """
        )
        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()

        with pytest.raises(RuntimeError, match="Foreign-key violations"):
            ensure_order_fills_order_delete_cascade(conn)

        # The rebuild rolled back: legacy FK action and every row (orphan included)
        # remain for the operator to repair.
        assert _fk_delete_action(conn, "order_fills", "order_id", "orders") == "NO ACTION"
        assert conn.execute("SELECT COUNT(*) FROM order_fills").fetchone()[0] == 2
        assert bool(conn.execute("PRAGMA foreign_keys").fetchone()[0])
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

        init_schema(conn)

        account_columns = _column_names(conn, "accounts")

        assert "benchmark_ticker" in account_columns
        assert "descriptive_name" in account_columns
        assert "rotation_overlay_watchlist" in account_columns
        assert "rotation_active_strategy" in account_columns
        # backtest_runs no longer carries an additive strategy_name column: the
        # backtested strategy is a strategies FK created in the base DDL, so there is
        # no backtest_runs migration to assert here.
        global_settings_columns = _column_names(conn, "global_settings")
        assert "runtime_max_trades_per_day" in global_settings_columns
        assert "runtime_max_trades_per_minute" in global_settings_columns
        assert "evaluation_backtest_trade_count_for_full_confidence" in global_settings_columns
        assert "promotion_min_live_overall_confidence" in global_settings_columns

        row = conn.execute(
            "SELECT name, descriptive_name, benchmark_ticker, rotation_overlay_watchlist "
            "FROM accounts WHERE name = 'acct_legacy'"
        ).fetchone()
        assert row is not None
        assert row["descriptive_name"] == "acct_legacy"
        assert row["benchmark_ticker"] == "SPY"
        assert row["rotation_overlay_watchlist"] == DEFAULT_ROTATION_OVERLAY_WATCHLIST_JSON
    finally:
        conn.close()


def test_init_schema_migrates_legacy_global_settings_columns(sqlite_backend: SQLiteBackend) -> None:
    conn = sqlite_backend.open_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE global_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                runtime_max_trades_per_day INTEGER,
                runtime_max_trades_per_minute INTEGER,
                updated_at TEXT
            );

            INSERT INTO global_settings (id, runtime_max_trades_per_day, runtime_max_trades_per_minute, updated_at)
            VALUES (1, 5, 2, '2026-01-01T00:00:00Z');
            """
        )

        init_schema(conn)

        columns = _column_names(conn, "global_settings")
        assert "evaluation_backtest_trade_confidence_weight" in columns
        assert "promotion_min_research_backtest_trade_count" in columns

        row = conn.execute(
            """
            SELECT
                evaluation_backtest_trade_count_for_full_confidence,
                evaluation_paper_live_evidence_weight,
                promotion_min_research_backtest_trade_count,
                promotion_min_live_overall_confidence
            FROM global_settings
            WHERE id = 1
            """
        ).fetchone()
        assert row is not None
        assert int(row["evaluation_backtest_trade_count_for_full_confidence"]) == 50
        assert float(row["evaluation_paper_live_evidence_weight"]) == pytest.approx(0.4)
        assert int(row["promotion_min_research_backtest_trade_count"]) == 10
        assert float(row["promotion_min_live_overall_confidence"]) == pytest.approx(0.6)
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

        migration = next(item for item in ACCOUNT_MIGRATIONS if item.column_name == "descriptive_name")
        _ensure_column(conn, "accounts", migration)

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

        migration = next(item for item in ACCOUNT_MIGRATIONS if item.column_name == "rotation_overlay_watchlist")
        _ensure_column(conn, "accounts", migration)

        row = conn.execute("SELECT rotation_overlay_watchlist FROM accounts WHERE name = 'acct_watchlist'").fetchone()
        assert row is not None
        assert row["rotation_overlay_watchlist"] == DEFAULT_ROTATION_OVERLAY_WATCHLIST_JSON
    finally:
        conn.close()


def test_ensure_column_is_noop_when_column_exists(sqlite_backend: SQLiteBackend) -> None:
    conn = sqlite_backend.open_connection()
    try:
        # descriptive_name already present → the migration must be a silent noop.
        conn.executescript(
            """
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                strategy TEXT NOT NULL,
                initial_cash REAL NOT NULL,
                created_at TEXT NOT NULL,
                descriptive_name TEXT NOT NULL DEFAULT ''
            );

            INSERT INTO accounts (name, strategy, initial_cash, created_at, descriptive_name)
            VALUES ('acct_noop', 'Trend', 1000, '2026-01-01T00:00:00Z', 'kept');
            """
        )

        migration = next(item for item in ACCOUNT_MIGRATIONS if item.column_name == "descriptive_name")
        _ensure_column(conn, "accounts", migration)

        row = conn.execute("SELECT descriptive_name FROM accounts WHERE name = 'acct_noop'").fetchone()
        assert row is not None
        assert row["descriptive_name"] == "kept"  # unchanged: existing column not re-migrated
    finally:
        conn.close()
