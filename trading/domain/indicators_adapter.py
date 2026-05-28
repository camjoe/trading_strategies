"""Indicator calculations for backtesting strategies.

Owns the implementations of MACD and RS/RSI directly — no dependency on the
trends package. Both functions are pure pandas math using shared constants from
common.constants.
"""

from __future__ import annotations

import math

import pandas as pd

from common.constants import (
    MACD_FAST_SPAN,
    MACD_SIGNAL_SPAN,
    MACD_SLOW_SPAN,
    RSI_DEFAULT_WINDOW,
    RSI_SCALE,
)


def calculate_macd(history: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate MACD, signal line, and histogram.

    Args:
        history: Historical close price series.

    Returns:
        Tuple of (macd, signal, histogram) series.
    """
    close = history.replace([math.inf, -math.inf], float("nan"))
    ema_fast = close.ewm(span=MACD_FAST_SPAN, adjust=False).mean()
    ema_slow = close.ewm(span=MACD_SLOW_SPAN, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal = macd.ewm(span=MACD_SIGNAL_SPAN, adjust=False).mean()
    histogram = macd - signal
    return macd, signal, histogram


def calculate_rs_rsi(history: pd.Series, window: int = RSI_DEFAULT_WINDOW) -> tuple[pd.Series, pd.Series]:
    """Calculate Relative Strength and RSI.

    Args:
        history: Historical close price series.
        window: Lookback window for rolling averages (default: RSI_DEFAULT_WINDOW).

    Returns:
        Tuple of (rs, rsi) series.
    """
    close = history.replace([math.inf, -math.inf], float("nan"))
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=window).mean()
    avg_loss = loss.rolling(window=window).mean()
    rs = avg_gain / avg_loss
    # Flat windows (avg_gain == avg_loss == 0) → treat as neutral momentum
    flat = (avg_gain == 0) & (avg_loss == 0)
    rs = rs.where(~flat, other=1.0)
    rsi = RSI_SCALE - (RSI_SCALE / (1 + rs))
    rsi = rsi.clip(lower=0.0, upper=float(RSI_SCALE))
    return rs, rsi
