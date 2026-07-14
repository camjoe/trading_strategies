"""Tests for paper_trading_web.backend.services.promotion."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import paper_trading_web.backend.services.promotion as promotion_module
from paper_trading_web.backend.services.promotion import (
    _normalize_optional_text,
    build_promotion_overview,
)
from trading.models.evaluation import (
    EvaluationBacktestEvidence,
    EvaluationConfidence,
    EvaluationDiagnostics,
    EvaluationPaperLiveEvidence,
    EvaluationWalkForwardEvidence,
    StrategyEvaluationArtifact,
)


class TestNormalizeOptionalText:
    def test_none_returns_none(self) -> None:
        assert _normalize_optional_text(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert _normalize_optional_text("") is None

    def test_whitespace_only_returns_none(self) -> None:
        assert _normalize_optional_text("   ") is None

    def test_valid_value_passes_through(self) -> None:
        assert _normalize_optional_text("trend_v1") == "trend_v1"

    def test_strips_surrounding_whitespace(self) -> None:
        assert _normalize_optional_text("  trend_v1  ") == "trend_v1"


class TestBuildPromotionOverview:
    def _make_assessment(self, payload: dict[str, object] | None = None) -> MagicMock:
        assessment = MagicMock()
        assessment.to_payload.return_value = payload or {"status": "pending"}
        return assessment

    def _make_history_entry(self) -> MagicMock:
        event = MagicMock()
        event.to_payload.return_value = {"kind": "snapshot"}

        entry = MagicMock()
        entry.review.to_payload.return_value = {"score": 0.8}
        entry.events = [event]
        return entry

    def _make_evaluation(self) -> StrategyEvaluationArtifact:
        return StrategyEvaluationArtifact(
            backtest=EvaluationBacktestEvidence(
                available=True,
                trade_count=42,
                snapshot_count=9,
                total_return_pct=12.5,
                max_drawdown_pct=-3.2,
            ),
            walk_forward=EvaluationWalkForwardEvidence(
                available=True,
                grouped=True,
                average_return_pct=3.4,
                best_return_pct=5.6,
                worst_return_pct=-1.2,
            ),
            paper_live=EvaluationPaperLiveEvidence(
                available=True,
                return_pct=2.3,
                snapshot_count=7,
                source_level="strategy",
                strategy_isolated=True,
            ),
            confidence=EvaluationConfidence(
                backtest_confidence=0.8,
                paper_live_confidence=0.7,
                overall_confidence=0.75,
                blended_score=8.9,
            ),
            diagnostics=EvaluationDiagnostics(data_gaps=["missing_walk_forward_evidence"]),
        )

    def test_returns_expected_payload_structure(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        assessment = self._make_assessment({"status": "pending"})
        entry = self._make_history_entry()

        monkeypatch.setattr(
            promotion_module,
            "fetch_current_promotion_snapshot",
            lambda *_a, **_kw: (self._make_evaluation(), assessment),
        )
        monkeypatch.setattr(
            promotion_module,
            "fetch_promotion_review_history",
            lambda *_a, **_kw: [entry],
        )

        result = build_promotion_overview(conn, account_name="acct_test")

        assert result["assessment"] == {"status": "pending"}
        assert result["history"] == [{"review": {"score": 0.8}, "events": [{"kind": "snapshot"}]}]
        assert result["evaluation"]["backtest"]["returnPct"] == pytest.approx(12.5)
        assert result["evaluation"]["backtest"]["tradeCount"] == 42
        assert result["evaluation"]["walkForward"]["grouped"] is True
        assert result["evaluation"]["paperLive"]["strategyIsolated"] is True
        assert result["evaluation"]["confidence"]["blendedScore"] == pytest.approx(8.9)
        assert result["evaluation"]["dataGaps"] == ["missing_walk_forward_evidence"]

    def test_normalizes_whitespace_strategy_name_to_none(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str | None] = []

        def _capture_snapshot(_conn, *, account_name, strategy_name):
            calls.append(strategy_name)
            return self._make_evaluation(), self._make_assessment()

        monkeypatch.setattr(
            promotion_module,
            "fetch_current_promotion_snapshot",
            _capture_snapshot,
        )
        monkeypatch.setattr(
            promotion_module,
            "fetch_promotion_review_history",
            lambda *_a, **_kw: [],
        )

        build_promotion_overview(conn, account_name="acct_test", strategy_name="   ")

        assert calls == [None]

    def test_passes_normalized_strategy_name_to_both_fetches(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        assessment_calls: list[str | None] = []
        history_calls: list[str | None] = []

        def _capture_snapshot(_conn, *, account_name, strategy_name):
            assessment_calls.append(strategy_name)
            return self._make_evaluation(), self._make_assessment()

        def _capture_history(_conn, *, account_name, strategy_name, limit):
            history_calls.append(strategy_name)
            return []

        monkeypatch.setattr(promotion_module, "fetch_current_promotion_snapshot", _capture_snapshot)
        monkeypatch.setattr(promotion_module, "fetch_promotion_review_history", _capture_history)

        build_promotion_overview(conn, account_name="acct_test", strategy_name="  trend_v1  ")

        assert assessment_calls == ["trend_v1"]
        assert history_calls == ["trend_v1"]

    def test_respects_limit_parameter(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        limits: list[int] = []

        def _capture_history(_conn, *, account_name, strategy_name, limit):
            limits.append(limit)
            return []

        monkeypatch.setattr(
            promotion_module,
            "fetch_current_promotion_snapshot",
            lambda *_a, **_kw: (self._make_evaluation(), self._make_assessment()),
        )
        monkeypatch.setattr(promotion_module, "fetch_promotion_review_history", _capture_history)

        build_promotion_overview(conn, account_name="acct_test", limit=10)

        assert limits == [10]
