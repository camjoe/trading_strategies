"""Re-export shim — canonical location is trading.repositories.backtest_history."""

from trading.repositories.backtest_history import fetch_strategy_backtest_rows

__all__ = ["fetch_strategy_backtest_rows"]
