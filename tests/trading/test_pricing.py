from datetime import date

import common.market_data as _mdata
import pandas as pd
import pytest

from trading.pricing import benchmark_stats, fetch_latest_prices


def _series(*closes: float) -> pd.Series:
    return pd.Series(list(closes), dtype=float)


def _close_history(ticker: str, closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({ticker: closes})


class TestFetchLatestPrices:
    def test_single(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(_mdata._provider, "fetch_close_series",
                            lambda ticker, period: _series(99.0, 100.5, 101.0))
        assert fetch_latest_prices(["AAPL"]) == {"AAPL": 101.0}

    def test_multiple(self, monkeypatch: pytest.MonkeyPatch):
        prices_map = {"AAPL": 150.0, "SPY": 500.0}
        monkeypatch.setattr(_mdata._provider, "fetch_close_series",
                            lambda ticker, period: _series(prices_map[ticker]))
        result = fetch_latest_prices(["AAPL", "SPY"])
        assert result == {"AAPL": 150.0, "SPY": 500.0}

    def test_empty_list_makes_no_provider_calls(self, monkeypatch: pytest.MonkeyPatch):
        called = []
        monkeypatch.setattr(_mdata._provider, "fetch_close_series",
                            lambda ticker, period: called.append(ticker) or None)
        assert fetch_latest_prices([]) == {}
        assert called == []

    def test_provider_none_omits_ticker(self, monkeypatch: pytest.MonkeyPatch):
        """Provider returns None for all failure modes (bad ticker, all-NaN closes, exception);
        fetch_latest_prices omits those tickers from the result."""
        monkeypatch.setattr(_mdata._provider, "fetch_close_series",
                            lambda ticker, period: None)
        assert fetch_latest_prices(["AAPL"]) == {}

    def test_one_failing_ticker_does_not_block_others(self, monkeypatch: pytest.MonkeyPatch):
        """One bad ticker should not prevent other results from being collected."""
        def _stub(ticker: str, period: str) -> pd.Series | None:
            return None if ticker == "BAD" else _series(200.0)

        monkeypatch.setattr(_mdata._provider, "fetch_close_series", _stub)
        result = fetch_latest_prices(["GOOD", "BAD"])
        assert result == {"GOOD": 200.0}


class TestBenchmarkStats:
    def test_normal(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(_mdata._provider, "fetch_close_history",
                            lambda tickers, start, end: _close_history(tickers[0], [100.0, 110.0, 120.0]))
        equity, ret = benchmark_stats("SPY", 10_000.0, "2024-01-01T00:00:00")
        assert equity == pytest.approx(12_000.0)
        assert ret == pytest.approx(20.0)

    def test_ticker_normalized_to_uppercase(self, monkeypatch: pytest.MonkeyPatch):
        """Ticker is normalised to uppercase before being passed to the provider."""
        calls: list[list[str]] = []

        def _stub(tickers: list[str], start: date, end: date) -> pd.DataFrame:
            calls.append(tickers)
            return _close_history(tickers[0], [50.0, 50.0])

        monkeypatch.setattr(_mdata._provider, "fetch_close_history", _stub)
        equity, ret = benchmark_stats(" spy ", 1_000.0, "2024-01-01")
        assert equity == pytest.approx(1_000.0)
        assert ret == pytest.approx(0.0)
        assert calls == [["SPY"]]

    def test_provider_value_error_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        def _raise_value_error(*args, **kwargs):
            raise ValueError("no data")

        monkeypatch.setattr(_mdata._provider, "fetch_close_history", _raise_value_error)
        assert benchmark_stats("SPY", 10_000.0, "2024-01-01") == (None, None)

    def test_provider_os_error_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        def _raise_os_error(*args, **kwargs):
            raise OSError("timeout")

        monkeypatch.setattr(_mdata._provider, "fetch_close_history", _raise_os_error)
        assert benchmark_stats("SPY", 10_000.0, "2024-01-01") == (None, None)

    def test_uses_created_at_date(self, monkeypatch: pytest.MonkeyPatch):
        """created_at is truncated to a date before being passed to the provider."""
        calls: list[tuple] = []

        def _stub(tickers: list[str], start: date, end: date) -> pd.DataFrame:
            calls.append((tickers, start, end))
            return _close_history(tickers[0], [10.0, 20.0])

        monkeypatch.setattr(_mdata._provider, "fetch_close_history", _stub)
        benchmark_stats("QQQ", 5_000.0, "2023-06-15T12:34:56")
        assert calls[0][1] == date(2023, 6, 15)

    def test_duplicate_ticker_columns_uses_first(self, monkeypatch: pytest.MonkeyPatch):
        """If provider returns duplicate ticker columns, benchmark_stats still computes using first column."""

        def _stub(_tickers: list[str], _start: date, _end: date) -> pd.DataFrame:
            return pd.DataFrame(
                [[100.0, 100.0], [110.0, 111.0], [120.0, 122.0]],
                columns=["SPY", "SPY"],
            )

        monkeypatch.setattr(_mdata._provider, "fetch_close_history", _stub)
        equity, ret = benchmark_stats("SPY", 10_000.0, "2024-01-01")
        assert equity == pytest.approx(12_000.0)
        assert ret == pytest.approx(20.0)

    def test_duplicate_columns_zero_width_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        class _CloseHistory:
            def __getitem__(self, _ticker):
                return pd.DataFrame(index=[0, 1])

        monkeypatch.setattr(_mdata._provider, "fetch_close_history", lambda *_args, **_kwargs: _CloseHistory())
        assert benchmark_stats("SPY", 10_000.0, "2024-01-01") == (None, None)

    def test_all_nan_series_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            _mdata._provider,
            "fetch_close_history",
            lambda tickers, start, end: _close_history(tickers[0], [float("nan"), float("nan")]),
        )
        assert benchmark_stats("SPY", 10_000.0, "2024-01-01") == (None, None)

