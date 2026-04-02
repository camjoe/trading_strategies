from datetime import date

import pandas as pd
import pytest

from trading.services.pricing_service import benchmark_stats, fetch_latest_prices


def _series(*closes: float) -> pd.Series:
    return pd.Series(list(closes), dtype=float)


def _close_history(ticker: str, closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({ticker: closes})


class TestFetchLatestPrices:
    def test_single(self):
        result = fetch_latest_prices(
            ["AAPL"],
            fetch_close_series_fn=lambda ticker, period: _series(99.0, 100.5, 101.0),
        )
        assert result == {"AAPL": 101.0}

    def test_multiple(self):
        prices_map = {"AAPL": 150.0, "SPY": 500.0}
        result = fetch_latest_prices(
            ["AAPL", "SPY"],
            fetch_close_series_fn=lambda ticker, period: _series(prices_map[ticker]),
        )
        assert result == {"AAPL": 150.0, "SPY": 500.0}

    def test_empty_list_makes_no_provider_calls(self):
        called: list[str] = []
        fetch_latest_prices(
            [],
            fetch_close_series_fn=lambda ticker, period: called.append(ticker) or None,
        )
        assert called == []

    def test_provider_none_omits_ticker(self):
        """Provider returns None for all failure modes (bad ticker, all-NaN closes, exception);
        fetch_latest_prices omits those tickers from the result."""
        assert fetch_latest_prices(
            ["AAPL"],
            fetch_close_series_fn=lambda ticker, period: None,
        ) == {}

    def test_one_failing_ticker_does_not_block_others(self):
        """One bad ticker should not prevent other results from being collected."""
        def _stub(ticker: str, period: str) -> pd.Series | None:
            return None if ticker == "BAD" else _series(200.0)

        result = fetch_latest_prices(["GOOD", "BAD"], fetch_close_series_fn=_stub)
        assert result == {"GOOD": 200.0}


class TestBenchmarkStats:
    def _stats(
        self,
        ticker: str,
        initial_cash: float,
        created_at: str,
        close_history_fn,
        today_fn=date.today,
    ) -> tuple[float | None, float | None]:
        return benchmark_stats(
            ticker,
            initial_cash,
            created_at,
            fetch_close_history_fn=close_history_fn,
            today_fn=today_fn,
        )

    def test_normal(self):
        equity, ret = self._stats(
            "SPY", 10_000.0, "2024-01-01T00:00:00",
            lambda tickers, start, end: _close_history(tickers[0], [100.0, 110.0, 120.0]),
        )
        assert equity == pytest.approx(12_000.0)
        assert ret == pytest.approx(20.0)

    def test_ticker_normalized_to_uppercase(self):
        """Ticker is normalised to uppercase before being passed to the provider."""
        calls: list[list[str]] = []

        def _stub(tickers: list[str], start: date, end: date) -> pd.DataFrame:
            calls.append(tickers)
            return _close_history(tickers[0], [50.0, 50.0])

        equity, ret = self._stats(" spy ", 1_000.0, "2024-01-01", _stub)
        assert equity == pytest.approx(1_000.0)
        assert ret == pytest.approx(0.0)
        assert calls == [["SPY"]]

    def test_provider_value_error_returns_none(self):
        def _raise(*args, **kwargs):
            raise ValueError("no data")

        assert self._stats("SPY", 10_000.0, "2024-01-01", _raise) == (None, None)

    def test_provider_os_error_returns_none(self):
        def _raise(*args, **kwargs):
            raise OSError("timeout")

        assert self._stats("SPY", 10_000.0, "2024-01-01", _raise) == (None, None)

    def test_uses_created_at_date(self):
        """created_at is truncated to a date before being passed to the provider."""
        calls: list[tuple] = []

        def _stub(tickers: list[str], start: date, end: date) -> pd.DataFrame:
            calls.append((tickers, start, end))
            return _close_history(tickers[0], [10.0, 20.0])

        self._stats("QQQ", 5_000.0, "2023-06-15T12:34:56", _stub)
        assert calls[0][1] == date(2023, 6, 15)

    def test_duplicate_ticker_columns_uses_first(self):
        """If provider returns duplicate ticker columns, benchmark_stats still computes using first column."""
        def _stub(_tickers: list[str], _start: date, _end: date) -> pd.DataFrame:
            return pd.DataFrame(
                [[100.0, 100.0], [110.0, 111.0], [120.0, 122.0]],
                columns=["SPY", "SPY"],
            )

        equity, ret = self._stats("SPY", 10_000.0, "2024-01-01", _stub)
        assert equity == pytest.approx(12_000.0)
        assert ret == pytest.approx(20.0)

    def test_duplicate_columns_zero_width_returns_none(self):
        class _CloseHistory:
            def __getitem__(self, _ticker):
                return pd.DataFrame(index=[0, 1])

        assert self._stats(
            "SPY", 10_000.0, "2024-01-01",
            lambda *_args, **_kwargs: _CloseHistory(),
        ) == (None, None)

    def test_all_nan_series_returns_none(self):
        assert self._stats(
            "SPY", 10_000.0, "2024-01-01",
            lambda tickers, start, end: _close_history(tickers[0], [float("nan"), float("nan")]),
        ) == (None, None)

