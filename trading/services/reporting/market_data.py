"""Reporting market-data adapters for reporting consumers.

Binds the shared market-data provider and pricing service helpers used by the
reporting package.
"""

from __future__ import annotations

from datetime import date

from common.market_data import get_provider
from trading.services.pricing import benchmark_stats as _benchmark_stats_svc
from trading.services.pricing import fetch_latest_prices as _fetch_prices_svc


def fetch_latest_prices(tickers: list[str]) -> dict[str, float]:
    """Inject the configured provider into pricing_service."""
    return _fetch_prices_svc(tickers, fetch_close_series_fn=get_provider().fetch_close_series)


def benchmark_stats(
    benchmark_ticker: str,
    initial_cash: float,
    created_at: str,
) -> tuple[float | None, float | None]:
    """Inject the configured provider into pricing_service."""
    return _benchmark_stats_svc(
        benchmark_ticker,
        initial_cash,
        created_at,
        fetch_close_history_fn=get_provider().fetch_close_history,
        today_fn=date.today,
    )


__all__ = [
    "benchmark_stats",
    "fetch_latest_prices",
]
