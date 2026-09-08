"""Price-based signal functions.

Each reads its indicators from an :class:`IndicatorView` — values the engine
computed once per ticker per run — rather than deriving them from a price
history on every bar. The decision logic is unchanged from when these functions
did their own rolling maths; only where the numbers come from moved.
"""

from __future__ import annotations

import math

import pandas as pd

from common.constants import RSI_DEFAULT_WINDOW, RSI_OVERBOUGHT, RSI_OVERSOLD
from trading.domain.strategies.contracts import StrategyParams
from trading.domain.strategies.indicator_view import IndicatorView


def _all_finite(*values: float) -> bool:
    return all(math.isfinite(value) for value in values)


def _trend_signal(
    view: IndicatorView,
    params: StrategyParams,
    _feature_history: pd.DataFrame | None = None,
) -> str:
    slow_window = int(params.get("slow_window", 20))
    if view.bars() < max(30, slow_window):
        return "hold"

    close = view.close()
    sma_fast = view.value("fast_ma")
    sma_slow = view.value("slow_ma")
    if not _all_finite(close, sma_fast, sma_slow):
        return "hold"
    if close > sma_fast > sma_slow:
        return "buy"
    if close < sma_fast:
        return "sell"
    return "hold"


def _mean_reversion_signal(
    view: IndicatorView,
    params: StrategyParams,
    _feature_history: pd.DataFrame | None = None,
) -> str:
    band_pct = float(params.get("band_pct", 0.02))
    if view.bars() < 30:
        return "hold"

    close = view.close()
    sma_mid = view.value("mid_ma")
    if not _all_finite(close, sma_mid):
        return "hold"
    if close < (sma_mid * (1.0 - band_pct)):
        return "buy"
    if close > (sma_mid * (1.0 + band_pct)):
        return "sell"
    return "hold"


def _rsi_signal(
    view: IndicatorView,
    params: StrategyParams,
    _feature_history: pd.DataFrame | None = None,
) -> str:
    window = int(params.get("window", RSI_DEFAULT_WINDOW))
    oversold = float(params.get("oversold", RSI_OVERSOLD))
    overbought = float(params.get("overbought", RSI_OVERBOUGHT))
    if view.bars() < max(30, window + 1):
        return "hold"

    last_rsi = view.value("rsi")
    if not math.isfinite(last_rsi):
        return "hold"
    if last_rsi < oversold:
        return "buy"
    if last_rsi > overbought:
        return "sell"
    return "hold"


def _breakout_signal(
    view: IndicatorView,
    params: StrategyParams,
    _feature_history: pd.DataFrame | None = None,
) -> str:
    window = int(params.get("window", 20))
    if view.bars() < max(30, window + 1):
        return "hold"

    current_close = view.close()
    highest_breakout = view.value("prior_high")
    lowest_breakdown = view.value("prior_low")
    if not _all_finite(current_close, highest_breakout, lowest_breakdown):
        return "hold"

    if current_close > highest_breakout:
        return "buy"
    if current_close < lowest_breakdown:
        return "sell"
    return "hold"


def _pullback_in_trend_signal(
    view: IndicatorView,
    params: StrategyParams,
    _feature_history: pd.DataFrame | None = None,
) -> str:
    trend_window = int(params.get("trend_window", 50))
    pullback_pct = float(params.get("pullback_pct", 0.03))
    if view.bars() < max(60, trend_window):
        return "hold"

    close = view.close()
    sma_fast = view.value("fast_ma")
    sma_trend = view.value("trend_ma")
    if not _all_finite(close, sma_fast, sma_trend):
        return "hold"

    if close < sma_trend:
        return "sell"

    in_uptrend = sma_fast > sma_trend
    in_pullback_zone = (sma_fast * (1.0 - pullback_pct)) <= close <= sma_fast
    if in_uptrend and in_pullback_zone:
        return "buy"
    return "hold"


def _bollinger_mean_reversion_signal(
    view: IndicatorView,
    params: StrategyParams,
    _feature_history: pd.DataFrame | None = None,
) -> str:
    window = int(params.get("window", 20))
    num_std = float(params.get("num_std", 2.0))
    if view.bars() < max(30, window):
        return "hold"

    close = view.close()
    middle = view.value("mid_ma")
    std = view.value("band_std")
    # A non-finite value anywhere in the window propagates into the rolling
    # results, so guarding the outputs covers the whole window.
    if not _all_finite(close, middle, std) or std <= 0:
        return "hold"

    lower_band = middle - (num_std * std)
    upper_band = middle + (num_std * std)
    if close < lower_band:
        return "buy"
    if close > upper_band:
        return "sell"
    return "hold"


def _ma_crossover_signal(
    view: IndicatorView,
    params: StrategyParams,
    _feature_history: pd.DataFrame | None = None,
) -> str:
    slow_window = int(params.get("slow_window", 50))
    if view.bars() < max(60, slow_window + 1):
        return "hold"

    prev_fast = view.value("fast_ma", -1)
    prev_slow = view.value("slow_ma", -1)
    curr_fast = view.value("fast_ma")
    curr_slow = view.value("slow_ma")
    if not _all_finite(prev_fast, prev_slow, curr_fast, curr_slow):
        return "hold"

    if prev_fast <= prev_slow and curr_fast > curr_slow:
        return "buy"
    if prev_fast >= prev_slow and curr_fast < curr_slow:
        return "sell"

    # Keep this strategy actionable after a recent crossover by honoring
    # the current fast/slow stack and price confirmation.
    close = view.close()
    if not math.isfinite(close):
        return "hold"
    if curr_fast > curr_slow and close >= curr_fast:
        return "buy"
    if curr_fast < curr_slow and close <= curr_fast:
        return "sell"
    return "hold"


def _volatility_filtered_trend_signal(
    view: IndicatorView,
    params: StrategyParams,
    _feature_history: pd.DataFrame | None = None,
) -> str:
    slow_window = int(params.get("slow_window", 50))
    vol_window = int(params.get("vol_window", 20))
    max_annualized_vol_pct = float(params.get("max_annualized_vol_pct", 45.0))
    if view.bars() < max(60, slow_window, vol_window + 1):
        return "hold"

    close = view.close()
    if not math.isfinite(close):
        return "hold"

    # A window containing an unusable return yields a non-finite volatility, and
    # the bar holds. The previous implementation dropped those returns and
    # estimated from whatever survived, which could pass the filter on a handful
    # of observations — a risk filter that failed open exactly when its inputs
    # were least trustworthy.
    annualized_vol_pct = view.value("return_vol")
    if not math.isfinite(annualized_vol_pct) or annualized_vol_pct > max_annualized_vol_pct:
        return "hold"

    sma_fast = view.value("fast_ma")
    sma_slow = view.value("slow_ma")
    if not _all_finite(sma_fast, sma_slow):
        return "hold"
    if close > sma_fast > sma_slow:
        return "buy"
    if close < sma_fast:
        return "sell"
    return "hold"
