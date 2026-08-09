"""Precompute a strategy's declared indicators, and read them one bar at a time.

A signal needs two or three numbers per bar. Deriving them from a price history
inside the signal means recomputing the whole rolling window on every trading
day — the same arithmetic repeated once per bar, to keep only the last value.
Computing each declared indicator once per ticker per run and indexing into it
turns that into a lookup.

Pure math over a bar frame: no provider, no connection, no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from common.constants import PERCENT_SCALE, TRADING_DAYS_PER_YEAR
from trading.domain.indicators import calculate_rs_rsi
from trading.domain.strategies.contracts import (
    INDICATOR_KIND_RETURN_VOL,
    INDICATOR_KIND_ROLLING_MAX,
    INDICATOR_KIND_ROLLING_MIN,
    INDICATOR_KIND_RSI,
    INDICATOR_KIND_SMA,
    INDICATOR_KIND_STDDEV,
    INDICATOR_SOURCE_CLOSE,
    IndicatorSpec,
    StrategyParams,
)


def _compute(series: pd.Series, spec: IndicatorSpec, window: int) -> pd.Series:
    """The raw series for one indicator, before shifting."""
    if spec.kind == INDICATOR_KIND_SMA:
        return series.rolling(window=window).mean()
    if spec.kind == INDICATOR_KIND_ROLLING_MAX:
        return series.rolling(window=window).max()
    if spec.kind == INDICATOR_KIND_ROLLING_MIN:
        return series.rolling(window=window).min()
    if spec.kind == INDICATOR_KIND_STDDEV:
        # Population standard deviation, matching the band math it replaces.
        return series.rolling(window=window).std(ddof=0)
    if spec.kind == INDICATOR_KIND_RSI:
        _rs, rsi = calculate_rs_rsi(series, window=window)
        return rsi
    if spec.kind == INDICATOR_KIND_RETURN_VOL:
        returns = series.pct_change()
        return returns.rolling(window=window).std(ddof=0) * (TRADING_DAYS_PER_YEAR**0.5) * PERCENT_SCALE
    raise ValueError(f"Unknown indicator kind: {spec.kind!r}")


def build_indicator_arrays(
    bars: pd.DataFrame,
    specs: tuple[IndicatorSpec, ...],
    params: StrategyParams,
    *,
    calendar: pd.DatetimeIndex | None = None,
) -> dict[str, np.ndarray]:
    """Compute every declared indicator over one ticker's bars.

    Returns plain float arrays aligned to ``bars.index`` — positional lookup is
    what makes the per-bar read cheap, and it keeps the view free of pandas
    indexing on the hot path.

    Pass *calendar* to express the results on a different (longer) index than
    the one they were computed over: each value carries forward until the
    ticker's next bar. The rolling windows still see only real bars, while the
    caller can index by a position on a shared calendar. Days before the
    ticker's first bar have nothing to carry forward and stay NaN, which the
    signals' finite-value guards already treat as "hold".
    """
    arrays: dict[str, np.ndarray] = {}
    for spec in specs:
        if spec.source not in bars.columns:
            raise ValueError(f"Indicator '{spec.name}' needs bar column '{spec.source}', which is not present.")
        computed = _compute(bars[spec.source], spec, spec.window_for(params))
        if spec.shift:
            computed = computed.shift(spec.shift)
        if calendar is not None:
            computed = computed.reindex(calendar).ffill()
        arrays[spec.name] = computed.to_numpy(dtype=float)
    return arrays


def count_priced_bars(closes: np.ndarray) -> np.ndarray:
    """Running count of bars with a usable close, one entry per bar.

    Signals gate on how much history they actually have. The series they used to
    receive had missing bars dropped out of it, so its length counted priced bars
    rather than elapsed calendar days — a ticker that listed late reached its
    minimum history later than its position in the calendar suggests. Counting
    priced bars here preserves that gate exactly.
    """
    return np.cumsum(np.isfinite(closes)).astype(int)


def build_signal_inputs(
    bars: pd.DataFrame,
    specs: tuple[IndicatorSpec, ...],
    params: StrategyParams,
    *,
    calendar: pd.DatetimeIndex,
) -> tuple[np.ndarray, dict[str, np.ndarray], np.ndarray]:
    """One ticker's ``(closes, indicators, priced_bars)`` for an :class:`IndicatorView`.

    Everything is derived from *bars* — the ticker's own trading days — and then
    expressed on *calendar*, the shared calendar the simulation walks.

    That order is the point. Deriving from a frame already reindexed onto the
    shared calendar puts other tickers' trading days inside this ticker's
    rolling windows as carried-forward repeats, which makes its indicators a
    function of the universe it happens to sit in: add an unrelated ticker that
    trades on a day this one did not, and this one's moving average moves. An
    indicator has to be a property of the instrument alone.

    Carrying values forward afterwards is not the same thing — it holds the
    value as of the ticker's last real bar, which is exactly what the live path
    computes from that same bar. The two agree by construction.
    """
    closes = bars[INDICATOR_SOURCE_CLOSE]
    aligned_closes = closes.reindex(calendar).ffill()
    priced = pd.Series(count_priced_bars(closes.to_numpy(dtype=float)), index=closes.index)
    aligned_priced = priced.reindex(calendar).ffill().fillna(0)
    return (
        aligned_closes.to_numpy(dtype=float),
        build_indicator_arrays(bars, specs, params, calendar=calendar),
        aligned_priced.to_numpy(dtype=int),
    )


@dataclass(frozen=True)
class IndicatorView:
    """One ticker's precomputed indicators and closes, positioned at one bar.

    ``offset`` is relative to that bar: 0 is the bar being decided, -1 the one
    before it. Reads outside the available history return NaN rather than
    raising, so a signal's existing finite-value guards keep working unchanged.
    """

    closes: np.ndarray
    indicators: Mapping[str, np.ndarray]
    index: int
    priced_bars: np.ndarray | None = None

    def bars(self) -> int:
        """Priced bars up to and including this one — replaces ``len(history)``."""
        if self.priced_bars is None:
            return self.index + 1
        return int(_at(self.priced_bars, self.index)) if 0 <= self.index < len(self.priced_bars) else 0

    def close(self, offset: int = 0) -> float:
        return _at(self.closes, self.index + offset)

    def value(self, name: str, offset: int = 0) -> float:
        series = self.indicators.get(name)
        if series is None:
            raise KeyError(f"Indicator '{name}' was not declared by this strategy.")
        return _at(series, self.index + offset)


def _at(series: np.ndarray, position: int) -> float:
    if position < 0 or position >= len(series):
        return float("nan")
    return float(series[position])
