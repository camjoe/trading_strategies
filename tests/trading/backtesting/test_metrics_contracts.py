from __future__ import annotations

import pandas as pd
import pytest

from trading.backtesting.domain.metrics import benchmark_return_pct, max_drawdown_pct, normalize_benchmark_series


def test_metrics_normalize_benchmark_series_with_dataframe_and_series() -> None:
    series = pd.Series([100.0, "bad", None, 101.0])
    normalized_series = normalize_benchmark_series(series)
    assert list(normalized_series.values) == [100.0, 101.0]

    frame = pd.DataFrame({"SPY": [100.0, "bad", 102.0]})
    normalized_frame = normalize_benchmark_series(frame)
    assert list(normalized_frame.values) == [100.0, 102.0]


def test_metrics_benchmark_return_pct_edge_cases() -> None:
    assert benchmark_return_pct(pd.Series([100.0]), initial_cash=10000.0) is None
    assert benchmark_return_pct(pd.Series([0.0, 110.0]), initial_cash=10000.0) is None
    assert benchmark_return_pct(pd.Series([100.0, 110.0]), initial_cash=10000.0) == pytest.approx(10.0)


def test_metrics_max_drawdown_pct_edge_cases() -> None:
    assert max_drawdown_pct([]) == 0.0
    assert max_drawdown_pct([0.0, -10.0, -5.0]) == 0.0
    assert max_drawdown_pct([100.0, 90.0, 95.0, 80.0]) == pytest.approx(-20.0)
