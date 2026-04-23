import pytest

from trading.services.reporting import (
    alpha_pct,
    benchmark_available,
    compute_market_value_and_unrealized,
    positions_summary_text,
    strategy_return_pct,
)


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


def test_alpha_pct_and_positions_summary_text() -> None:
    assert alpha_pct(12.0, 8.0) == pytest.approx(4.0)

    count, text = positions_summary_text({"MSFT": 2.0, "AAPL": 5.0})
    assert count == 2
    assert text.startswith("AAPL")

    truncated_count, truncated_text = positions_summary_text({f"T{i}": float(i) for i in range(7)})
    assert truncated_count == 7
    assert truncated_text.endswith(", ...")
