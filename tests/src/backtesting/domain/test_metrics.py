from __future__ import annotations

import pandas as pd
import pytest

import backtesting.domain.metrics as metrics_module
from backtesting.domain.metrics import (
    benchmark_return_pct,
    calmar_ratio,
    equity_curve_from_rows,
    max_drawdown_pct,
    normalize_benchmark_series,
    sharpe_ratio,
    sortino_ratio,
    summarize_backtest_performance,
    total_return_pct,
)


def test_total_return_pct_matches_first_last_equity() -> None:
    assert total_return_pct(first_equity=10_000.0, last_equity=11_000.0) == pytest.approx(10.0)
    assert total_return_pct(first_equity=10_000.0, last_equity=9_500.0) == pytest.approx(-5.0)


def test_max_drawdown_handles_empty_and_non_positive_peak() -> None:
    assert max_drawdown_pct([]) == 0.0
    assert max_drawdown_pct([0.0, -10.0, -5.0]) == 0.0
    assert max_drawdown_pct([100.0, 90.0, 95.0, 80.0]) == pytest.approx(-20.0)


def test_normalize_benchmark_series_accepts_series_and_dataframe() -> None:
    series = pd.Series([100.0, "bad", None, 101.0])
    normalized_series = normalize_benchmark_series(series)
    assert list(normalized_series.values) == [100.0, 101.0]

    frame = pd.DataFrame({"SPY": [100.0, "bad", 102.0]})
    normalized_frame = normalize_benchmark_series(frame)
    assert list(normalized_frame.values) == [100.0, 102.0]


def test_normalize_benchmark_series_handles_empty_dataframe() -> None:
    frame = pd.DataFrame()
    normalized = normalize_benchmark_series(frame)
    assert normalized.empty


def test_benchmark_return_pct_edge_cases() -> None:
    assert benchmark_return_pct(pd.Series([100.0]), initial_cash=10000.0) is None
    assert benchmark_return_pct(pd.Series([0.0, 110.0]), initial_cash=10000.0) is None
    assert benchmark_return_pct(pd.Series([100.0, 110.0]), initial_cash=10000.0) == pytest.approx(10.0)


def test_risk_ratios_handle_basic_series() -> None:
    returns = pd.Series([0.01, -0.005, 0.02, -0.01])

    assert sharpe_ratio(returns) == pytest.approx(4.9923017660270625)
    assert sortino_ratio(returns) == pytest.approx(7.529940238806681)
    assert calmar_ratio(annualized_return_pct=12.0, max_drawdown_pct_value=-6.0) == pytest.approx(2.0)


def test_risk_ratio_helpers_return_none_for_degenerate_inputs() -> None:
    assert sharpe_ratio(pd.Series([], dtype=float)) is None
    assert sharpe_ratio(pd.Series([0.0, 0.0])) is None
    assert sortino_ratio(pd.Series([0.01, 0.02])) is None
    assert calmar_ratio(annualized_return_pct=10.0, max_drawdown_pct_value=0.0) is None
    # A drawdown floor is what keeps the same degenerate input rankable for the optimizer.
    assert calmar_ratio(
        annualized_return_pct=10.0, max_drawdown_pct_value=0.0, drawdown_floor_pct=1.0
    ) == pytest.approx(10.0)


def test_summarize_backtest_performance_computes_trade_analytics() -> None:
    metrics = summarize_backtest_performance(
        equity_curve=[1000.0, 1050.0, 1025.0, 1100.0],
        trades=[
            {"ticker": "AAPL", "side": "buy", "qty": 1.0, "price": 100.0, "fee": 1.0},
            {"ticker": "AAPL", "side": "sell", "qty": 1.0, "price": 110.0, "fee": 1.0},
            {"ticker": "MSFT", "side": "buy", "qty": 1.0, "price": 50.0, "fee": 0.0},
            {"ticker": "MSFT", "side": "sell", "qty": 1.0, "price": 45.0, "fee": 0.0},
        ],
    )

    assert metrics.win_rate_pct == pytest.approx(50.0)
    assert metrics.profit_factor == pytest.approx(1.6)
    assert metrics.avg_trade_return_pct == pytest.approx(-1.0396039603960396)
    assert metrics.sharpe_ratio is not None
    assert metrics.calmar_ratio is not None


@pytest.mark.parametrize(
    "trade,error_message",
    [
        ({"ticker": "AAPL", "side": "buy", "qty": 0.0, "price": 100.0, "fee": 0.0}, "quantity must be > 0"),
        ({"ticker": "AAPL", "side": "buy", "qty": 1.0, "price": -1.0, "fee": 0.0}, "price must be >= 0"),
        ({"ticker": "AAPL", "side": "hold", "qty": 1.0, "price": 100.0, "fee": 0.0}, "Unsupported trade side"),
    ],
)
def test_summarize_backtest_performance_rejects_invalid_trade_rows(
    trade: dict[str, object],
    error_message: str,
) -> None:
    with pytest.raises(ValueError, match=error_message):
        summarize_backtest_performance(
            equity_curve=[1000.0, 1001.0],
            trades=[trade],
        )


def test_summarize_backtest_performance_rejects_sell_larger_than_position() -> None:
    with pytest.raises(ValueError, match="trying to sell"):
        summarize_backtest_performance(
            equity_curve=[1000.0, 1001.0],
            trades=[
                {"ticker": "AAPL", "side": "sell", "qty": 2.0, "price": 100.0, "fee": 0.0},
            ],
        )


def test_metrics_private_helpers_and_trade_numeric_guards() -> None:
    assert metrics_module._equity_return_series([100.0]).empty
    assert metrics_module._annualized_return_pct([100.0]) is None
    assert metrics_module._annualized_return_pct([0.0, 100.0]) is None
    assert sortino_ratio(pd.Series([], dtype=float)) is None

    with pytest.raises(ValueError, match="Buy trade price must be > 0"):
        summarize_backtest_performance(
            equity_curve=[1000.0, 1001.0],
            trades=[{"ticker": "AAPL", "side": "buy", "qty": 1.0, "price": 0.0, "fee": 0.0}],
        )

    # Rejected by the shared coercion in trading.domain.accounting, which the replay
    # now uses so a persisted trade reads the same on the live and backtest paths.
    with pytest.raises(ValueError, match="Expected float-convertible value"):
        summarize_backtest_performance(
            equity_curve=[1000.0, 1001.0],
            trades=[{"ticker": "AAPL", "side": "buy", "qty": object(), "price": 100.0, "fee": 0.0}],
        )


def test_equity_curve_from_rows_keeps_row_order() -> None:
    rows = [{"equity": 1000.0}, {"equity": 1050.0}, {"equity": 990.0}]

    assert equity_curve_from_rows(rows) == [1000.0, 1050.0, 990.0]


def test_equity_curve_from_rows_drops_snapshots_with_no_equity() -> None:
    """A null mark is nothing to measure, so it leaves the curve rather than entering it as None."""
    rows = [{"equity": 1000.0}, {"equity": None}, {"equity": 1050.0}]

    assert equity_curve_from_rows(rows) == [1000.0, 1050.0]


def test_equity_curve_from_rows_handles_no_rows() -> None:
    assert equity_curve_from_rows([]) == []
