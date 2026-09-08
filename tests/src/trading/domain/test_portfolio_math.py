import pytest

from trading.domain.metrics.portfolio_math import (
    alpha_pct,
    benchmark_available,
    compute_market_value,
    compute_market_value_and_unrealized,
    compute_unrealized_pnl,
    strategy_return_pct,
)


def test_market_value_and_unrealized_pnl_ignore_missing_or_non_positive_positions() -> None:
    positions = {"AAPL": 2.0, "MSFT": 1.5, "NVDA": 0.0}
    prices = {"AAPL": 10.0, "MSFT": 20.0}
    avg_cost = {"AAPL": 8.0, "MSFT": 25.0, "NVDA": 100.0}

    assert compute_market_value(positions, prices) == pytest.approx(50.0)
    assert compute_unrealized_pnl(positions, avg_cost, prices) == pytest.approx(-3.5)


def test_strict_and_lenient_valuation_disagree_on_an_unpriced_holding() -> None:
    # The reason these are two functions and not one. MSFT has no price: the
    # lenient pass drops it from both figures, while the strict unrealized refuses
    # rather than report a P&L that silently omits a holding.
    positions = {"AAPL": 2.0, "MSFT": 1.0}
    avg_cost = {"AAPL": 8.0, "MSFT": 25.0}
    prices = {"AAPL": 10.0}

    market_value, unrealized = compute_market_value_and_unrealized(positions, avg_cost, prices)
    assert (market_value, unrealized) == (pytest.approx(20.0), pytest.approx(4.0))

    assert compute_market_value(positions, prices) == pytest.approx(20.0)
    with pytest.raises(KeyError):
        compute_unrealized_pnl(positions, avg_cost, prices)


def test_compute_market_value_and_unrealized_skips_missing_prices() -> None:
    market_value, unrealized = compute_market_value_and_unrealized(
        positions={"AAPL": 10.0, "MSFT": 5.0},
        avg_cost={"AAPL": 100.0, "MSFT": 200.0},
        prices={"AAPL": 120.0},
    )

    assert market_value == pytest.approx(1200.0)
    assert unrealized == pytest.approx(200.0)


def test_strategy_return_pct_raises_when_initial_cash_is_zero() -> None:
    with pytest.raises(ValueError):
        strategy_return_pct(100.0, 0.0)


def test_benchmark_available_requires_both_values() -> None:
    assert benchmark_available(105.0, 5.0) is True
    assert benchmark_available(None, 5.0) is False
    assert benchmark_available(105.0, None) is False


def test_alpha_pct_computes_difference() -> None:
    assert alpha_pct(12.0, 8.0) == pytest.approx(4.0)
