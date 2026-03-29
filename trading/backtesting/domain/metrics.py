from __future__ import annotations

import pandas as pd


def max_drawdown_pct(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0

    peak = equity_curve[0]
    max_dd = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak <= 0:
            continue
        dd = (equity / peak) - 1.0
        max_dd = min(max_dd, dd)
    return max_dd * 100.0


def normalize_benchmark_series(benchmark_close: pd.Series | pd.DataFrame) -> pd.Series:
    if isinstance(benchmark_close, pd.DataFrame):
        if benchmark_close.empty:
            return pd.Series(dtype=float)
        series = benchmark_close.iloc[:, 0]
    else:
        series = benchmark_close

    if isinstance(series, pd.DataFrame):
        if series.empty:
            return pd.Series(dtype=float)
        series = series.iloc[:, 0]

    return pd.to_numeric(series, errors="coerce").dropna()


def benchmark_return_pct(benchmark_close: pd.Series | pd.DataFrame, initial_cash: float) -> float | None:
    series = normalize_benchmark_series(benchmark_close)
    if len(series) < 2:
        return None

    start_px = float(series.iloc[0])
    end_px = float(series.iloc[-1])
    if start_px <= 0:
        return None

    equity = initial_cash * (end_px / start_px)
    return ((equity / initial_cash) - 1.0) * 100.0
