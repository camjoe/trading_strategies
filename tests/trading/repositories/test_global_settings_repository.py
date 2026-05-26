from __future__ import annotations

import pytest

from trading.services.runtime_settings import set_evaluation_confidence_settings
from trading.repositories.global_settings import (
    fetch_global_settings_row,
    upsert_evaluation_confidence_settings,
    upsert_promotion_policy_settings,
    upsert_runtime_throttle_settings,
)


class TestUpsertEvaluationConfidenceSettings:
    def test_persists_valid_normalized_weight_pairs(self, conn) -> None:
        set_evaluation_confidence_settings(
            conn,
            backtest_trade_count_for_full_confidence=50,
            backtest_snapshot_count_for_full_confidence=60,
            paper_live_snapshot_count_for_full_confidence=30,
            backtest_trade_confidence_weight=0.7,
            backtest_snapshot_confidence_weight=0.3,
            backtest_evidence_weight=0.6,
            paper_live_evidence_weight=0.4,
            updated_at="2026-04-17T00:00:00Z",
        )

        row = fetch_global_settings_row(conn)

        assert row is not None
        assert float(row["evaluation_backtest_trade_confidence_weight"]) == pytest.approx(0.7)
        assert float(row["evaluation_backtest_evidence_weight"]) == pytest.approx(0.6)

    def test_rejects_invalid_backtest_weight_sum(self, conn) -> None:
        with pytest.raises(
            ValueError,
            match="backtest_trade_confidence_weight \\+ backtest_snapshot_confidence_weight must equal 1.0",
        ):
            set_evaluation_confidence_settings(
                conn,
                backtest_trade_count_for_full_confidence=50,
                backtest_snapshot_count_for_full_confidence=60,
                paper_live_snapshot_count_for_full_confidence=30,
                backtest_trade_confidence_weight=0.8,
                backtest_snapshot_confidence_weight=0.8,
                backtest_evidence_weight=0.6,
                paper_live_evidence_weight=0.4,
                updated_at="2026-04-17T00:00:00Z",
            )

        assert fetch_global_settings_row(conn) is None

    def test_rejects_invalid_evidence_weight_sum(self, conn) -> None:
        with pytest.raises(
            ValueError,
            match="backtest_evidence_weight \\+ paper_live_evidence_weight must equal 1.0",
        ):
            set_evaluation_confidence_settings(
                conn,
                backtest_trade_count_for_full_confidence=50,
                backtest_snapshot_count_for_full_confidence=60,
                paper_live_snapshot_count_for_full_confidence=30,
                backtest_trade_confidence_weight=0.7,
                backtest_snapshot_confidence_weight=0.3,
                backtest_evidence_weight=0.2,
                paper_live_evidence_weight=0.2,
                updated_at="2026-04-17T00:00:00Z",
            )

        assert fetch_global_settings_row(conn) is None

    def test_repository_upsert_persists_without_policy_validation(self, conn) -> None:
        upsert_evaluation_confidence_settings(
            conn,
            backtest_trade_count_for_full_confidence=50,
            backtest_snapshot_count_for_full_confidence=60,
            paper_live_snapshot_count_for_full_confidence=30,
            backtest_trade_confidence_weight=0.8,
            backtest_snapshot_confidence_weight=0.8,
            backtest_evidence_weight=0.2,
            paper_live_evidence_weight=0.2,
            updated_at="2026-04-17T00:00:00Z",
        )

        row = fetch_global_settings_row(conn)

        assert row is not None
        assert float(row["evaluation_backtest_trade_confidence_weight"]) == pytest.approx(0.8)


class TestRuntimeThrottleAndPromotionPolicySettings:
    def test_upsert_runtime_throttle_settings_inserts_and_updates(self, conn) -> None:
        upsert_runtime_throttle_settings(
            conn,
            runtime_max_trades_per_day=5,
            runtime_max_trades_per_minute=2,
            updated_at="2026-04-18T00:00:00Z",
        )
        upsert_runtime_throttle_settings(
            conn,
            runtime_max_trades_per_day=7,
            runtime_max_trades_per_minute=None,
            updated_at="2026-04-18T01:00:00Z",
        )

        row = fetch_global_settings_row(conn)

        assert row is not None
        assert int(row["runtime_max_trades_per_day"]) == 7
        assert row["runtime_max_trades_per_minute"] is None
        assert row["updated_at"] == "2026-04-18T01:00:00Z"

    def test_upsert_promotion_policy_settings_inserts_and_updates(self, conn) -> None:
        upsert_promotion_policy_settings(
            conn,
            min_research_backtest_trade_count=20,
            min_research_backtest_snapshot_count=40,
            min_research_backtest_return_pct=5.0,
            min_research_max_drawdown_pct=-8.5,
            min_research_walk_forward_average_return_pct=2.5,
            min_live_paper_snapshot_count=15,
            min_live_overall_confidence=0.7,
            updated_at="2026-04-19T00:00:00Z",
        )
        upsert_promotion_policy_settings(
            conn,
            min_research_backtest_trade_count=25,
            min_research_backtest_snapshot_count=45,
            min_research_backtest_return_pct=6.0,
            min_research_max_drawdown_pct=-7.0,
            min_research_walk_forward_average_return_pct=3.5,
            min_live_paper_snapshot_count=20,
            min_live_overall_confidence=0.8,
            updated_at="2026-04-19T01:00:00Z",
        )

        row = fetch_global_settings_row(conn)

        assert row is not None
        assert int(row["promotion_min_research_backtest_trade_count"]) == 25
        assert int(row["promotion_min_research_backtest_snapshot_count"]) == 45
        assert float(row["promotion_min_research_walk_forward_average_return_pct"]) == pytest.approx(3.5)
        assert float(row["promotion_min_live_overall_confidence"]) == pytest.approx(0.8)
        assert row["updated_at"] == "2026-04-19T01:00:00Z"
