import pytest

from trading.domain.evaluation_confidence import (
    EvaluationConfidenceSettings,
    compute_backtest_confidence,
    compute_blended_score,
    compute_overall_confidence,
    compute_paper_live_confidence,
)


def test_compute_backtest_confidence_uses_trade_and_snapshot_coverage() -> None:
    confidence = compute_backtest_confidence(
        trade_count=25,
        snapshot_count=30,
    )

    assert confidence == pytest.approx(0.5)


def test_compute_paper_live_confidence_uses_snapshot_coverage() -> None:
    confidence = compute_paper_live_confidence(snapshot_count=15)

    assert confidence == pytest.approx(0.5)


def test_compute_overall_confidence_uses_conservative_evidence_weights() -> None:
    confidence = compute_overall_confidence(
        backtest_confidence=0.5,
        paper_live_confidence=0.25,
    )

    assert confidence == pytest.approx(0.4)


def test_compute_blended_score_ignores_missing_scores() -> None:
    score = compute_blended_score(
        backtest_score=8.0,
        paper_live_score=None,
        backtest_confidence=0.6,
        paper_live_confidence=0.0,
    )

    assert score == pytest.approx(8.0)


def test_compute_blended_score_biases_toward_higher_confidence_evidence() -> None:
    score = compute_blended_score(
        backtest_score=10.0,
        paper_live_score=4.0,
        backtest_confidence=0.8,
        paper_live_confidence=0.2,
    )

    assert score == pytest.approx(9.142857142857142)


def test_compute_backtest_confidence_uses_injected_settings() -> None:
    confidence = compute_backtest_confidence(
        trade_count=25,
        snapshot_count=30,
        settings=EvaluationConfidenceSettings(
            backtest_trade_count_for_full_confidence=100,
            backtest_snapshot_count_for_full_confidence=100,
            backtest_trade_confidence_weight=0.5,
            backtest_snapshot_confidence_weight=0.5,
        ),
    )

    assert confidence == pytest.approx(0.275)
