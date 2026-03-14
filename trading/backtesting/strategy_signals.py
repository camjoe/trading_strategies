from __future__ import annotations

from collections.abc import Callable
import importlib

import pandas as pd

try:
    from trends.indicators import calculate_macd, calculate_rs_rsi
except ModuleNotFoundError:
    indicators = importlib.import_module("indicators")
    calculate_macd = indicators.calculate_macd
    calculate_rs_rsi = indicators.calculate_rs_rsi


def _trend_signal(history: pd.Series) -> str:
    if len(history) < 30:
        return "hold"

    close = float(history.iloc[-1])
    sma_10 = float(history.tail(10).mean())
    sma_20 = float(history.tail(20).mean())
    if close > sma_10 > sma_20:
        return "buy"
    if close < sma_10:
        return "sell"
    return "hold"


def _mean_reversion_signal(history: pd.Series) -> str:
    if len(history) < 30:
        return "hold"

    close = float(history.iloc[-1])
    sma_20 = float(history.tail(20).mean())
    if close < (sma_20 * 0.98):
        return "buy"
    if close > (sma_20 * 1.02):
        return "sell"
    return "hold"


def _rsi_signal(history: pd.Series) -> str:
    if len(history) < 30:
        return "hold"

    _rs, rsi = calculate_rs_rsi(history, window=14)
    last_rsi = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else float("nan")
    if pd.isna(last_rsi):
        return "hold"
    if last_rsi < 30:
        return "buy"
    if last_rsi > 70:
        return "sell"
    return "hold"


def _macd_signal(history: pd.Series) -> str:
    if len(history) < 35:
        return "hold"

    macd, macd_signal, _hist = calculate_macd(history)
    prev_diff = macd.iloc[-2] - macd_signal.iloc[-2]
    curr_diff = macd.iloc[-1] - macd_signal.iloc[-1]
    if pd.isna(prev_diff) or pd.isna(curr_diff):
        return "hold"
    if prev_diff <= 0 and curr_diff > 0:
        return "buy"
    if prev_diff >= 0 and curr_diff < 0:
        return "sell"
    return "hold"


def resolve_signal(strategy_name: str, history: pd.Series) -> str:
    """Resolve strategy labels to explicit signal models used during backtesting."""
    name = strategy_name.strip().lower()

    if "rsi" in name:
        return _rsi_signal(history)

    if "macd" in name:
        return _macd_signal(history)

    if "mean" in name or "reversion" in name:
        return _mean_reversion_signal(history)

    if "trend" in name or "momentum" in name:
        return _trend_signal(history)

    return _trend_signal(history)
