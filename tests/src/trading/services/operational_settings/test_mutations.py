"""Tests for trading.services.operational_settings.mutations."""

from __future__ import annotations

import pytest

from trading.services.operational_settings.mutations import (
    _validate_weight_sum,
    set_evaluation_confidence_settings,
    set_promotion_policy_settings,
    set_runtime_throttle_settings,
)


# ---------------------------------------------------------------------------
# _validate_weight_sum
# ---------------------------------------------------------------------------


class TestValidateWeightSum:
    def test_valid_weights_do_not_raise(self) -> None:
        _validate_weight_sum(
            first_name="a",
            first_value=0.6,
            second_name="b",
            second_value=0.4,
        )

    def test_invalid_weights_raise_value_error(self) -> None:
        with pytest.raises(ValueError, match="must equal 1.0"):
            _validate_weight_sum(
                first_name="a",
                first_value=0.8,
                second_name="b",
                second_value=0.8,
            )

    def test_error_message_includes_field_names(self) -> None:
        with pytest.raises(ValueError, match="trade_weight"):
            _validate_weight_sum(
                first_name="trade_weight",
                first_value=0.5,
                second_name="snapshot_weight",
                second_value=0.3,
            )


# ---------------------------------------------------------------------------
# set_runtime_throttle_settings
# ---------------------------------------------------------------------------


class TestSetRuntimeThrottleSettings:
    def test_persists_throttle_settings(self, conn) -> None:
        set_runtime_throttle_settings(
            conn,
            runtime_max_trades_per_day=50,
            runtime_max_trades_per_minute=5,
            updated_at="2026-01-01T00:00:00Z",
        )
        row = conn.execute("SELECT * FROM global_settings").fetchone()
        assert row is not None
        assert row["runtime_max_trades_per_day"] == 50
        assert row["runtime_max_trades_per_minute"] == 5

    def test_none_values_persist_as_null(self, conn) -> None:
        set_runtime_throttle_settings(
            conn,
            runtime_max_trades_per_day=None,
            runtime_max_trades_per_minute=None,
            updated_at="2026-01-01T00:00:00Z",
        )
        row = conn.execute("SELECT * FROM global_settings").fetchone()
        assert row["runtime_max_trades_per_day"] is None
        assert row["runtime_max_trades_per_minute"] is None


# ---------------------------------------------------------------------------
# set_evaluation_confidence_settings
# ---------------------------------------------------------------------------


class TestSetEvaluationConfidenceSettings:
    def _valid_kwargs(self, **overrides):
        defaults = dict(
            backtest_trade_count_for_full_confidence=100,
            backtest_snapshot_count_for_full_confidence=50,
            paper_live_snapshot_count_for_full_confidence=30,
            backtest_trade_confidence_weight=0.6,
            backtest_snapshot_confidence_weight=0.4,
            backtest_evidence_weight=0.7,
            paper_live_evidence_weight=0.3,
            updated_at="2026-01-01T00:00:00Z",
        )
        defaults.update(overrides)
        return defaults

    def test_persists_valid_settings(self, conn) -> None:
        set_evaluation_confidence_settings(conn, **self._valid_kwargs())
        row = conn.execute("SELECT * FROM global_settings").fetchone()
        assert row is not None
        assert row["evaluation_backtest_trade_count_for_full_confidence"] == 100

    def test_invalid_confidence_weights_raise_value_error(self, conn) -> None:
        with pytest.raises(ValueError, match="must equal 1.0"):
            set_evaluation_confidence_settings(
                conn,
                **self._valid_kwargs(
                    backtest_trade_confidence_weight=0.8,
                    backtest_snapshot_confidence_weight=0.8,
                ),
            )

    def test_invalid_evidence_weights_raise_value_error(self, conn) -> None:
        with pytest.raises(ValueError, match="must equal 1.0"):
            set_evaluation_confidence_settings(
                conn,
                **self._valid_kwargs(
                    backtest_evidence_weight=0.9,
                    paper_live_evidence_weight=0.9,
                ),
            )


# ---------------------------------------------------------------------------
# set_promotion_policy_settings
# ---------------------------------------------------------------------------


class TestSetPromotionPolicySettings:
    def test_persists_promotion_policy_settings(self, conn) -> None:
        set_promotion_policy_settings(
            conn,
            min_research_backtest_trade_count=20,
            min_research_backtest_snapshot_count=10,
            min_research_backtest_return_pct=5.0,
            min_research_max_drawdown_pct=15.0,
            min_research_walk_forward_average_return_pct=3.0,
            min_live_paper_snapshot_count=30,
            min_live_overall_confidence=0.6,
            updated_at="2026-01-01T00:00:00Z",
        )
        row = conn.execute("SELECT * FROM global_settings").fetchone()
        assert row is not None
        assert row["promotion_min_research_backtest_trade_count"] == 20
        assert row["promotion_min_live_overall_confidence"] == pytest.approx(0.6)
