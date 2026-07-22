"""Persistence operations for the application-owned offline demo story."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence

from trading.repositories.unit_of_work import commit_unit_of_work


class DemoSeedRepository:
    """Write coherent synthetic records through one repository boundary."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def account_id(self, name: str) -> int:
        row = self._conn.execute("SELECT id FROM accounts WHERE name = ?", (name,)).fetchone()
        if row is None:
            raise ValueError(f"Demo account '{name}' was not created.")
        return int(row["id"])

    def default_book_id(self, account_id: int) -> int:
        row = self._conn.execute(
            "SELECT id FROM books WHERE account_id = ? AND is_default = 1", (account_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Default book missing for demo account {account_id}.")
        return int(row["id"])

    def set_account_demo_safety(self, account_id: int, *, now_iso: str) -> None:
        self._conn.execute(
            "UPDATE accounts SET broker_type = 'paper', live_trading_enabled = 0, updated_at = ? WHERE id = ?",
            (now_iso, account_id),
        )

    def insert_fill(
        self, *, account_id: int, book_id: int, symbol: str, side: str, qty: float, price: float, time_iso: str
    ) -> None:
        cursor = self._conn.execute(
            """INSERT INTO orders
               (book_id, account_id, symbol, side, qty, requested_price, status, filled_qty,
                avg_fill_price, commission, submitted_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'filled', ?, ?, 0, ?, ?)""",
            (book_id, account_id, symbol, side, qty, price, qty, price, time_iso, time_iso),
        )
        order_id = cursor.lastrowid
        if order_id is None:
            raise ValueError("Expected an order id after inserting a demo fill.")
        self._conn.execute(
            "INSERT INTO order_fills (order_id, filled_qty, fill_price, commission, fill_time) VALUES (?, ?, ?, 0, ?)",
            (order_id, qty, price, time_iso),
        )

    def upsert_position(
        self, *, book_id: int, symbol: str, qty: float, avg_cost: float, market_value: float, now_iso: str
    ) -> None:
        self._conn.execute(
            """INSERT INTO positions (book_id, symbol, qty, avg_cost, market_value, unrealized_pnl, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (book_id, symbol, qty, avg_cost, market_value, market_value - qty * avg_cost, now_iso),
        )

    def insert_snapshot(
        self, *, book_id: int, time_iso: str, cash: float, market_value: float, equity: float, realized: float
    ) -> None:
        self._conn.execute(
            """INSERT INTO equity_snapshots
               (book_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (book_id, time_iso, cash, market_value, equity, realized, equity - cash - market_value),
        )

    def insert_daily_metric(
        self, *, book_id: int, metric_date: str, return_pct: float, drawdown_pct: float, now_iso: str
    ) -> None:
        self._conn.execute(
            """INSERT INTO daily_metrics
               (book_id, metric_date, return_pct, drawdown_pct, turnover_pct, slippage_bps,
                hit_rate, expectancy, risk_adjusted_score, trade_count, fees_total, created_at, updated_at)
               VALUES (?, ?, ?, ?, 0.08, 2.5, 0.58, 0.42, 0.71, 2, 0, ?, ?)""",
            (book_id, metric_date, return_pct, drawdown_pct, now_iso, now_iso),
        )

    def insert_backtest(
        self,
        *,
        account_id: int,
        strategy_key: str,
        start_date: str,
        end_date: str,
        snapshots: Sequence[tuple[str, float]],
        now_iso: str,
    ) -> None:
        strategy = self._conn.execute("SELECT id FROM strategies WHERE strategy_key = ?", (strategy_key,)).fetchone()
        if strategy is None:
            raise ValueError(f"Demo strategy '{strategy_key}' is missing.")
        cursor = self._conn.execute(
            """INSERT INTO backtest_runs
               (account_id, strategy_id, run_name, purpose, start_date, end_date, created_at,
                slippage_bps, fee_per_trade, tickers_file, notes, warnings)
               VALUES (?, ?, 'Offline demo backtest', 'standalone', ?, ?, ?, 2.5, 0,
                       'synthetic:DEMO', 'Deterministic synthetic demo run.', '')""",
            (account_id, int(strategy["id"]), start_date, end_date, now_iso),
        )
        run_id = cursor.lastrowid
        if run_id is None:
            raise ValueError("Expected a run id after inserting the demo backtest.")
        first_date = snapshots[4][0]
        last_date = snapshots[-5][0]
        self._conn.execute(
            """INSERT INTO backtest_executions
               (run_id, execution_date, ticker, side, qty, price, fee, slippage_bps, note)
               VALUES (?, ?, 'AAPL', 'buy', 12, 150, 0, 2.5, 'Synthetic sample execution')""",
            (run_id, first_date),
        )
        self._conn.execute(
            """INSERT INTO backtest_executions
               (run_id, execution_date, ticker, side, qty, price, fee, slippage_bps, note)
               VALUES (?, ?, 'AAPL', 'sell', 12, 162, 0, 2.5, 'Synthetic sample execution')""",
            (run_id, last_date),
        )
        for snapshot_date, equity in snapshots:
            self._conn.execute(
                """INSERT INTO backtest_equity_snapshots
                   (run_id, snapshot_date, cash, market_value, equity, realized_pnl, unrealized_pnl)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (run_id, snapshot_date, equity * 0.35, equity * 0.65, equity, max(0.0, equity - 10_000.0) * 0.4, 0.0),
            )

    def insert_promotion_review(self, *, account_id: int, account_name: str, strategy_key: str, now_iso: str) -> None:
        strategy = self._conn.execute("SELECT id FROM strategies WHERE strategy_key = ?", (strategy_key,)).fetchone()
        if strategy is None:
            raise ValueError(f"Demo strategy '{strategy_key}' is missing.")
        assessment = {"sample": True, "label": "Synthetic demo evidence", "status": "ready_for_review"}
        evaluation = {"sample": True, "label": "Synthetic demo evidence", "trade_count": 15, "snapshot_count": 30}
        self._conn.execute(
            """INSERT INTO promotion_reviews
               (account_id, account_name_snapshot, strategy_name, review_state, assessment_stage,
                assessment_status, ready_for_live, overall_confidence, live_trading_enabled_snapshot,
                promotion_assessment_version, evaluation_artifact_version, frozen_assessment_payload,
                frozen_evaluation_payload, requested_by, operator_summary_note, created_at, updated_at, strategy_id)
               VALUES (?, ?, ?, 'requested', 'promotion_review', 'ready_for_review', 0, 0.82, 0,
                       'demo-v1', 'demo-v1', ?, ?, 'offline-demo',
                       'Synthetic sample evidence only; not suitable for live-trading decisions.', ?, ?, ?)""",
            (
                account_id,
                account_name,
                strategy_key,
                json.dumps(assessment),
                json.dumps(evaluation),
                now_iso,
                now_iso,
                int(strategy["id"]),
            ),
        )

    def finish(self) -> None:
        commit_unit_of_work(self._conn)
