from __future__ import annotations

import math

import pandas as pd

from common.constants import (
    RSI_DEFAULT_WINDOW,
    RSI_OVERBOUGHT,
    RSI_OVERSOLD,
    TRADING_DAYS_PER_YEAR,
)
from trading.domain.indicators import calculate_rs_rsi
from trading.domain.strategies.contracts import StrategyParams


def _trend_signal(
    history: pd.Series,
    params: StrategyParams,
    _feature_history: pd.DataFrame | None = None,
) -> str:
    fast_window = int(params.get("fast_window", 10))
    slow_window = int(params.get("slow_window", 20))
    min_history = max(30, slow_window)
    if len(history) < min_history:
        return "hold"

    close = float(history.iloc[-1])
    if not math.isfinite(close):
        return "hold"
    sma_fast = float(history.tail(fast_window).mean())
    sma_slow = float(history.tail(slow_window).mean())
    if not math.isfinite(sma_fast) or not math.isfinite(sma_slow):
        return "hold"
    if close > sma_fast > sma_slow:
        return "buy"
    if close < sma_fast:
        return "sell"
    return "hold"


def _mean_reversion_signal(
    history: pd.Series,
    params: StrategyParams,
    _feature_history: pd.DataFrame | None = None,
) -> str:
    window = int(params.get("window", 20))
    band_pct = float(params.get("band_pct", 0.02))
    if len(history) < 30:
        return "hold"

    close = float(history.iloc[-1])
    if not math.isfinite(close):
        return "hold"
    sma_mid = float(history.tail(window).mean())
    if not math.isfinite(sma_mid):
        return "hold"
    if close < (sma_mid * (1.0 - band_pct)):
        return "buy"
    if close > (sma_mid * (1.0 + band_pct)):
        return "sell"
    return "hold"


def _rsi_signal(
    history: pd.Series,
    params: StrategyParams,
    _feature_history: pd.DataFrame | None = None,
) -> str:
    window = int(params.get("window", RSI_DEFAULT_WINDOW))
    oversold = float(params.get("oversold", RSI_OVERSOLD))
    overbought = float(params.get("overbought", RSI_OVERBOUGHT))
    min_history = max(30, window + 1)
    if len(history) < min_history:
        return "hold"

    _rs, rsi = calculate_rs_rsi(history, window=window)
    last_rsi = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else float("nan")
    if pd.isna(last_rsi) or not math.isfinite(last_rsi):
        return "hold"
    if last_rsi < oversold:
        return "buy"
    if last_rsi > overbought:
        return "sell"
    return "hold"


def _breakout_signal(
    history: pd.Series,
    params: StrategyParams,
    _feature_history: pd.DataFrame | None = None,
) -> str:
    window = int(params.get("window", 20))
    min_history = max(30, window + 1)
    if len(history) < min_history:
        return "hold"

    current_close = float(history.iloc[-1])
    if not math.isfinite(current_close):
        return "hold"
    prior_window = history.iloc[-(window + 1) : -1]
    highest_breakout = float(prior_window.max())
    lowest_breakdown = float(prior_window.min())
    if not math.isfinite(highest_breakout) or not math.isfinite(lowest_breakdown):
        return "hold"

    if current_close > highest_breakout:
        return "buy"
    if current_close < lowest_breakdown:
        return "sell"
    return "hold"


def _pullback_in_trend_signal(
    history: pd.Series,
    params: StrategyParams,
    _feature_history: pd.DataFrame | None = None,
) -> str:
    fast_window = int(params.get("fast_window", 20))
    trend_window = int(params.get("trend_window", 50))
    pullback_pct = float(params.get("pullback_pct", 0.03))
    min_history = max(60, trend_window)
    if len(history) < min_history:
        return "hold"

    close = float(history.iloc[-1])
    sma_fast = float(history.tail(fast_window).mean())
    sma_trend = float(history.tail(trend_window).mean())

    if not math.isfinite(close) or not math.isfinite(sma_fast) or not math.isfinite(sma_trend):
        return "hold"

    if close < sma_trend:
        return "sell"

    in_uptrend = sma_fast > sma_trend
    in_pullback_zone = (sma_fast * (1.0 - pullback_pct)) <= close <= sma_fast
    if in_uptrend and in_pullback_zone:
        return "buy"
    return "hold"


def _bollinger_mean_reversion_signal(
    history: pd.Series,
    params: StrategyParams,
    _feature_history: pd.DataFrame | None = None,
) -> str:
    window = int(params.get("window", 20))
    num_std = float(params.get("num_std", 2.0))
    min_history = max(30, window)
    if len(history) < min_history:
        return "hold"

    segment = history.tail(window)
    close = float(segment.iloc[-1])
    if not math.isfinite(close):
        return "hold"
    segment_finite = segment[segment.map(lambda value: math.isfinite(float(value)))]
    if len(segment_finite) < len(segment):
        return "hold"
    middle = float(segment_finite.mean())
    std = float(segment_finite.std(ddof=0))
    if not math.isfinite(std) or std <= 0:
        return "hold"

    lower_band = middle - (num_std * std)
    upper_band = middle + (num_std * std)
    if close < lower_band:
        return "buy"
    if close > upper_band:
        return "sell"
    return "hold"


def _ma_crossover_signal(
    history: pd.Series,
    params: StrategyParams,
    _feature_history: pd.DataFrame | None = None,
) -> str:
    fast_window = int(params.get("fast_window", 20))
    slow_window = int(params.get("slow_window", 50))
    min_history = max(60, slow_window + 1)
    if len(history) < min_history:
        return "hold"

    fast = history.rolling(window=fast_window).mean()
    slow = history.rolling(window=slow_window).mean()
    prev_fast = float(fast.iloc[-2])
    prev_slow = float(slow.iloc[-2])
    curr_fast = float(fast.iloc[-1])
    curr_slow = float(slow.iloc[-1])

    has_missing_crossover_inputs = any(pd.isna(value) for value in (prev_fast, prev_slow, curr_fast, curr_slow))
    if has_missing_crossover_inputs:
        return "hold"
    if not all(math.isfinite(v) for v in (prev_fast, prev_slow, curr_fast, curr_slow)):
        return "hold"

    if prev_fast <= prev_slow and curr_fast > curr_slow:
        return "buy"
    if prev_fast >= prev_slow and curr_fast < curr_slow:
        return "sell"

    # Keep this strategy actionable after a recent crossover by honoring
    # the current fast/slow stack and price confirmation.
    close = float(history.iloc[-1])
    if not math.isfinite(close):
        return "hold"
    if curr_fast > curr_slow and close >= curr_fast:
        return "buy"
    if curr_fast < curr_slow and close <= curr_fast:
        return "sell"
    return "hold"


def _volatility_filtered_trend_signal(
    history: pd.Series,
    params: StrategyParams,
    _feature_history: pd.DataFrame | None = None,
) -> str:
    fast_window = int(params.get("fast_window", 20))
    slow_window = int(params.get("slow_window", 50))
    vol_window = int(params.get("vol_window", 20))
    max_annualized_vol_pct = float(params.get("max_annualized_vol_pct", 45.0))
    min_history = max(60, slow_window, vol_window + 1)
    if len(history) < min_history:
        return "hold"

    close = float(history.iloc[-1])
    if not math.isfinite(close):
        return "hold"

    returns = history.pct_change().dropna()
    recent_returns = returns.tail(vol_window)
    recent_returns = recent_returns[recent_returns.map(lambda value: math.isfinite(float(value)))]
    if recent_returns.empty:
        return "hold"
    annualized_vol_pct = float(recent_returns.std(ddof=0) * (TRADING_DAYS_PER_YEAR**0.5) * 100.0)
    if pd.isna(annualized_vol_pct) or annualized_vol_pct > max_annualized_vol_pct:
        return "hold"

    sma_fast = float(history.tail(fast_window).mean())
    sma_slow = float(history.tail(slow_window).mean())
    has_valid_trend_inputs = math.isfinite(close) and math.isfinite(sma_fast) and math.isfinite(sma_slow)
    if not has_valid_trend_inputs:
        return "hold"
    if close > sma_fast > sma_slow:
        return "buy"
    if close < sma_fast:
        return "sell"
    return "hold"
