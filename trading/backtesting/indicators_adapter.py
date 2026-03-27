"""Adapter layer for indicator imports from trends module.

This module centralizes the dependency on trends.indicators and provides
clear error messaging if the module is unavailable.
"""

from __future__ import annotations

from typing import Any, Callable

import pandas as pd


def get_indicators_module() -> Any:
    """Import and return the indicators module for backtesting strategies.

    Raises:
        RuntimeError: If trends.indicators module is not available.

    Returns:
        Module object with calculate_macd and calculate_rs_rsi functions.
    """
    try:
        from trends import indicators
        return indicators
    except (ModuleNotFoundError, ImportError) as e:
        raise RuntimeError(
            "Backtesting strategies require trends.indicators module. "
            "Ensure trends/ package is installed and importable, or provide custom indicator implementations."
        ) from e


def get_indicator_function(name: str) -> Callable:
    """Get a specific indicator function by name.

    Raises:
        RuntimeError: If trends.indicators is not available.
        AttributeError: If the function doesn't exist in indicators module.

    Args:
        name: Name of the indicator function (e.g., 'calculate_macd', 'calculate_rs_rsi')

    Returns:
        The indicator function from trends.indicators.
    """
    indicators = get_indicators_module()
    if not hasattr(indicators, name):
        raise AttributeError(
            f"Indicator function '{name}' not found in trends.indicators. "
            f"Available: calculate_macd, calculate_rs_rsi"
        )
    return getattr(indicators, name)


def calculate_macd(history: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate MACD indicators using trends module.

    Args:
        history: Historical price series

    Returns:
        Tuple of (macd, signal, histogram) series
    """
    fn = get_indicator_function("calculate_macd")
    return fn(history)


def calculate_rs_rsi(history: pd.Series, window: int = 14) -> tuple[pd.Series, pd.Series]:
    """Calculate RS and RSI indicators using trends module.

    Args:
        history: Historical price series
        window: RSI window period

    Returns:
        Tuple of (rs, rsi) series
    """
    fn = get_indicator_function("calculate_rs_rsi")
    return fn(history, window=window)
