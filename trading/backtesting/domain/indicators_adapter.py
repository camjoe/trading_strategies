"""Re-export shim — canonical location is trading.domain.indicators_adapter."""

from trading.domain.indicators_adapter import calculate_macd, calculate_rs_rsi

__all__ = ["calculate_macd", "calculate_rs_rsi"]
