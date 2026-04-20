from __future__ import annotations

import pytest

from trading.repositories.global_settings_repository import (
    fetch_global_settings_row,
    upsert_evaluation_confidence_settings,
)


class TestUpsertEvaluationConfidenceSettings:
    def test_persists_valid_normalized_weight_pairs(self, conn) -> None:
        upsert_evaluation_confidence_settings(
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
            upsert_evaluation_confidence_settings(
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
            upsert_evaluation_confidence_settings(
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
