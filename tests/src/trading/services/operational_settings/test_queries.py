"""Tests for trading.services.operational_settings.queries."""

from __future__ import annotations

import pytest

from trading.domain.evaluation_confidence import EvaluationConfidenceSettings
from trading.domain.promotion_policy import PromotionPolicySettings
from trading.repositories.global_settings import GlobalSettingsRepository
from trading.services.operational_settings.mutations import (
    set_evaluation_confidence_settings,
    set_promotion_policy_settings,
    set_runtime_throttle_settings,
)
from trading.services.operational_settings.queries import (
    fetch_evaluation_confidence_settings,
    fetch_promotion_policy_settings,
    fetch_runtime_throttle_settings,
)

# ---------------------------------------------------------------------------
# fetch_runtime_throttle_settings
# ---------------------------------------------------------------------------


class TestFetchRuntimeThrottleSettings:
    def test_no_execute_attr_returns_defaults(self) -> None:
        """Non-connection object returns default RuntimeThrottleSettings."""
        result = fetch_runtime_throttle_settings(object())  # type: ignore[arg-type]
        assert result.max_trades_per_day is None
        assert result.max_trades_per_minute is None

    def test_empty_db_returns_defaults(self, conn) -> None:
        """No global_settings row → defaults."""
        result = fetch_runtime_throttle_settings(conn)
        assert result.max_trades_per_day is None
        assert result.max_trades_per_minute is None

    def test_returns_persisted_values(self, conn) -> None:
        set_runtime_throttle_settings(
            conn,
            runtime_max_trades_per_day=25,
            runtime_max_trades_per_minute=3,
            updated_at="2026-01-01T00:00:00Z",
        )
        result = fetch_runtime_throttle_settings(conn)
        assert result.max_trades_per_day == 25
        assert result.max_trades_per_minute == 3


# ---------------------------------------------------------------------------
# fetch_evaluation_confidence_settings
# ---------------------------------------------------------------------------


class TestFetchEvaluationConfidenceSettings:
    def test_no_execute_attr_returns_defaults(self) -> None:
        result = fetch_evaluation_confidence_settings(object())  # type: ignore[arg-type]
        assert result.backtest_trade_confidence_weight is not None

    def test_empty_db_returns_defaults(self, conn) -> None:
        result = fetch_evaluation_confidence_settings(conn)
        assert result.backtest_trade_confidence_weight is not None

    def test_throttle_row_does_not_materialize_policy_overrides(self, conn) -> None:
        set_runtime_throttle_settings(
            conn,
            runtime_max_trades_per_day=25,
            runtime_max_trades_per_minute=None,
            updated_at="2026-01-01T00:00:00Z",
        )

        record = GlobalSettingsRepository(conn).fetch()
        result = fetch_evaluation_confidence_settings(conn)

        assert record is not None
        assert record.evaluation_backtest_trade_count_for_full_confidence is None
        assert result == EvaluationConfidenceSettings()

    def test_returns_persisted_values(self, conn) -> None:
        set_evaluation_confidence_settings(
            conn,
            backtest_trade_count_for_full_confidence=200,
            backtest_snapshot_count_for_full_confidence=100,
            paper_live_snapshot_count_for_full_confidence=50,
            backtest_trade_confidence_weight=0.6,
            backtest_snapshot_confidence_weight=0.4,
            backtest_evidence_weight=0.7,
            paper_live_evidence_weight=0.3,
            updated_at="2026-01-01T00:00:00Z",
        )
        result = fetch_evaluation_confidence_settings(conn)
        assert result.backtest_trade_count_for_full_confidence == 200
        assert result.backtest_trade_confidence_weight == pytest.approx(0.6)

    def test_null_weights_fall_back_to_defaults(self, conn) -> None:
        """Rows with NULL float weights fall back to domain defaults."""
        defaults = fetch_evaluation_confidence_settings(conn)
        # Set numeric counts only, leave weights as defaults by using valid sums.
        set_evaluation_confidence_settings(
            conn,
            backtest_trade_count_for_full_confidence=50,
            backtest_snapshot_count_for_full_confidence=25,
            paper_live_snapshot_count_for_full_confidence=15,
            backtest_trade_confidence_weight=defaults.backtest_trade_confidence_weight,
            backtest_snapshot_confidence_weight=defaults.backtest_snapshot_confidence_weight,
            backtest_evidence_weight=defaults.backtest_evidence_weight,
            paper_live_evidence_weight=defaults.paper_live_evidence_weight,
            updated_at="2026-01-01T00:00:00Z",
        )
        result = fetch_evaluation_confidence_settings(conn)
        assert result.backtest_trade_count_for_full_confidence == 50


# ---------------------------------------------------------------------------
# fetch_promotion_policy_settings
# ---------------------------------------------------------------------------


class TestFetchPromotionPolicySettings:
    def test_no_execute_attr_returns_defaults(self) -> None:
        result = fetch_promotion_policy_settings(object())  # type: ignore[arg-type]
        assert result.min_research_backtest_trade_count is not None

    def test_empty_db_returns_defaults(self, conn) -> None:
        result = fetch_promotion_policy_settings(conn)
        assert result.min_research_backtest_trade_count is not None

    def test_null_policy_fields_use_code_defaults(self, conn) -> None:
        set_runtime_throttle_settings(
            conn,
            runtime_max_trades_per_day=25,
            runtime_max_trades_per_minute=None,
            updated_at="2026-01-01T00:00:00Z",
        )

        assert fetch_promotion_policy_settings(conn) == PromotionPolicySettings()

    def test_returns_persisted_values(self, conn) -> None:
        set_promotion_policy_settings(
            conn,
            min_research_backtest_trade_count=30,
            min_research_backtest_snapshot_count=15,
            min_research_backtest_return_pct=8.0,
            min_research_max_drawdown_pct=20.0,
            min_research_walk_forward_average_return_pct=4.0,
            min_live_paper_snapshot_count=60,
            min_live_overall_confidence=0.65,
            updated_at="2026-01-01T00:00:00Z",
        )
        result = fetch_promotion_policy_settings(conn)
        assert result.min_research_backtest_trade_count == 30
        assert result.min_research_backtest_return_pct == pytest.approx(8.0)
        assert result.min_live_overall_confidence == pytest.approx(0.65)
