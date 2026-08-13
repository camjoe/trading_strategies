from trading.models.evaluation import BacktestFreshness
from trading.services.evaluation.presentation import backtest_freshness_display_parts


def test_returns_none_when_freshness_missing() -> None:
    assert backtest_freshness_display_parts(None) is None


def test_returns_none_when_unavailable() -> None:
    assert backtest_freshness_display_parts(BacktestFreshness(available=False, age_days=3.0)) is None


def test_returns_none_when_age_missing() -> None:
    assert backtest_freshness_display_parts(BacktestFreshness(available=True, age_days=None)) is None


def test_returns_age_and_fresh_label() -> None:
    parts = backtest_freshness_display_parts(BacktestFreshness(available=True, age_days=2.5, is_stale=False))
    assert parts == (2.5, "fresh")


def test_returns_age_and_stale_label() -> None:
    parts = backtest_freshness_display_parts(BacktestFreshness(available=True, age_days=9.0, is_stale=True))
    assert parts == (9.0, "stale")
