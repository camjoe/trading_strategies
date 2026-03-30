from datetime import date

from common.market_data import get_provider
from trading.services.pricing_service import benchmark_stats as benchmark_stats_impl
from trading.services.pricing_service import fetch_latest_prices as fetch_latest_prices_impl


def fetch_latest_prices(tickers: list[str]) -> dict[str, float]:
    provider = get_provider()
    return fetch_latest_prices_impl(
        tickers,
        fetch_close_series_fn=provider.fetch_close_series,
    )


def benchmark_stats(benchmark_ticker: str, initial_cash: float, created_at: str) -> tuple[float | None, float | None]:
    return benchmark_stats_impl(
        benchmark_ticker,
        initial_cash,
        created_at,
        fetch_close_history_fn=get_provider().fetch_close_history,
        today_fn=date.today,
    )
