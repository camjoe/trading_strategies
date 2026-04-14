from __future__ import annotations

import pandas as pd
import pytest

from trading.backtesting.domain.metrics import (
    benchmark_return_pct,
    calmar_ratio,
    max_drawdown_pct,
    normalize_benchmark_series,
    sharpe_ratio,
    sortino_ratio,
    summarize_backtest_performance,
)


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


def test_benchmark_return_pct_edge_cases() -> None:
    assert benchmark_return_pct(pd.Series([100.0]), initial_cash=10000.0) is None
    assert benchmark_return_pct(pd.Series([0.0, 110.0]), initial_cash=10000.0) is None
    assert benchmark_return_pct(pd.Series([100.0, 110.0]), initial_cash=10000.0) == pytest.approx(10.0)


def test_risk_ratios_handle_basic_series() -> None:
    returns = pd.Series([0.01, -0.005, 0.02, -0.01])

    assert sharpe_ratio(returns) == pytest.approx(4.9923017660270625)
    assert sortino_ratio(returns) == pytest.approx(7.529940238806681)
    assert calmar_ratio(annualized_return_pct=12.0, max_drawdown_pct_value=-6.0) == pytest.approx(2.0)


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
