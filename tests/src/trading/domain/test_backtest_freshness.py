from __future__ import annotations

from trading.domain.evaluation.backtest_freshness import (
    DEFAULT_BACKTEST_STALE_THRESHOLD_DAYS,
    assess_backtest_freshness,
)


def test_unavailable_when_no_backtest_run() -> None:
    result = assess_backtest_freshness(backtest_created_at=None, reference_iso="2026-03-16T00:00:00Z")

    assert result.available is False
    assert result.age_days is None
    assert result.is_stale is False
    assert result.stale_threshold_days == DEFAULT_BACKTEST_STALE_THRESHOLD_DAYS


def test_fresh_within_threshold() -> None:
    result = assess_backtest_freshness(
        backtest_created_at="2026-03-15T00:00:00Z",
        reference_iso="2026-03-16T00:00:00Z",
    )

    assert result.available is True
    assert result.age_days == 1.0
    assert result.is_stale is False


def test_stale_beyond_threshold() -> None:
    result = assess_backtest_freshness(
        backtest_created_at="2026-03-10T00:00:00Z",
        reference_iso="2026-03-16T00:00:00Z",
    )

    assert result.available is True
    assert result.age_days == 6.0
    assert result.is_stale is True


def test_boundary_at_threshold_is_not_stale() -> None:
    # Exactly threshold_days old is not yet stale (strict >).
    result = assess_backtest_freshness(
        backtest_created_at="2026-03-13T00:00:00Z",
        reference_iso="2026-03-16T00:00:00Z",
        threshold_days=3,
    )

    assert result.age_days == 3.0
    assert result.is_stale is False


def test_custom_threshold_respected() -> None:
    result = assess_backtest_freshness(
        backtest_created_at="2026-03-15T00:00:00Z",
        reference_iso="2026-03-16T00:00:00Z",
        threshold_days=0,
    )

    assert result.stale_threshold_days == 0
    assert result.is_stale is True
