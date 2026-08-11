"""Persistence operations for generated fixture databases (demo and sandbox).

Deliberately narrow. Only the two records whose production writers a fixture
cannot drive: a backtest run (``backtesting.repositories.runs.insert_run``
stamps its own ``created_at``, so a deterministic fixture cannot use it) and a
promotion review (``PromotionReviewRepository.insert_review`` builds its row
from real ``PromotionAssessment``/``StrategyEvaluationArtifact`` objects, which
a fixture has no way to produce).

Everything else the seeder needs goes through the owning repository —
see ``trading.services.fixtures.seeding``. Close either gap above and this
module goes with it.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from trading.persistence.json_columns import dumps_json_column
from trading.persistence.unit_of_work import commit_unit_of_work

# Marks every synthetic backtest run so a generated row is never mistaken for a
# real research result.
FIXTURE_TICKERS_FILE = "synthetic:FIXTURE"

# Assessment/evaluation artifact versions on seeded promotion reviews. The
# `fixture-` prefix keeps them sortable alongside real versions while remaining
# obviously synthetic.
FIXTURE_ARTIFACT_VERSION = "fixture-v1"


class FixtureSeedRepository:
    """Write coherent synthetic records through one repository boundary."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert_backtest(
        self,
        *,
        account_id: int,
        strategy_key: str,
        start_date: str,
        end_date: str,
        snapshots: Sequence[tuple[str, float]],
        execution_margin_days: int,
        now_iso: str,
    ) -> None:
        strategy = self._conn.execute("SELECT id FROM strategies WHERE strategy_key = ?", (strategy_key,)).fetchone()
        if strategy is None:
            raise ValueError(f"Fixture strategy '{strategy_key}' is missing.")
        cursor = self._conn.execute(
            """INSERT INTO backtest_runs
               (account_id, strategy_id, run_name, purpose, start_date, end_date, created_at,
                slippage_bps, fee_per_trade, tickers_file, notes, warnings)
               VALUES (?, ?, 'Generated fixture backtest', 'standalone', ?, ?, ?, 2.5, 0,
                       ?, 'Deterministic synthetic fixture run.', '')""",
            (account_id, int(strategy["id"]), start_date, end_date, now_iso, FIXTURE_TICKERS_FILE),
        )
        run_id = cursor.lastrowid
        if run_id is None:
            raise ValueError("Expected a run id after inserting the fixture backtest.")
        first_date = snapshots[execution_margin_days - 1][0]
        last_date = snapshots[-execution_margin_days][0]
        opening_equity = snapshots[0][1]
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
                (
                    run_id,
                    snapshot_date,
                    equity * 0.35,
                    equity * 0.65,
                    equity,
                    max(0.0, equity - opening_equity) * 0.4,
                    0.0,
                ),
            )
        commit_unit_of_work(self._conn)

    def insert_promotion_review(self, *, account_id: int, account_name: str, strategy_key: str, now_iso: str) -> None:
        strategy = self._conn.execute("SELECT id FROM strategies WHERE strategy_key = ?", (strategy_key,)).fetchone()
        if strategy is None:
            raise ValueError(f"Fixture strategy '{strategy_key}' is missing.")
        assessment = {"sample": True, "label": "Synthetic fixture evidence", "status": "ready_for_review"}
        evaluation = {"sample": True, "label": "Synthetic fixture evidence", "trade_count": 15, "snapshot_count": 30}
        cursor = self._conn.execute(
            """INSERT INTO promotion_reviews
               (account_id, account_name_snapshot, strategy_name, review_state, assessment_stage,
                assessment_status, ready_for_live, overall_confidence, live_trading_enabled_snapshot,
                promotion_assessment_version, evaluation_artifact_version, frozen_assessment_payload,
                frozen_evaluation_payload, requested_by, operator_summary_note, created_at, updated_at, strategy_id)
               VALUES (?, ?, ?, 'requested', 'promotion_review', 'ready_for_review', 0, 0.82, 0,
                       ?, ?, ?, ?, 'generated-fixture',
                       'Synthetic sample evidence only; not suitable for live-trading decisions.', ?, ?, ?)""",
            (
                account_id,
                account_name,
                strategy_key,
                FIXTURE_ARTIFACT_VERSION,
                FIXTURE_ARTIFACT_VERSION,
                dumps_json_column(assessment),
                dumps_json_column(evaluation),
                now_iso,
                now_iso,
                int(strategy["id"]),
            ),
        )
        review_id = cursor.lastrowid
        if review_id is None:
            raise ValueError("Expected a review id after inserting the fixture promotion review.")
        # A review with no events is an unreachable state in the real workflow:
        # the request that creates it is itself the first recorded transition.
        self._conn.execute(
            """INSERT INTO promotion_review_events
               (review_id, event_seq, event_type, actor_type, actor_name, from_review_state,
                to_review_state, note, created_at)
               VALUES (?, 1, 'requested', 'operator', 'generated-fixture', NULL, 'requested',
                       'Generated fixture review request.', ?)""",
            (review_id, now_iso),
        )
        commit_unit_of_work(self._conn)
