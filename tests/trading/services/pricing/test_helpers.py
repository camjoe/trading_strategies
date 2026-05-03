from datetime import date

import pandas as pd
import pytest

import trading.services.pricing.helpers as pricing_helpers
from trading.services.pricing import benchmark_stats, fetch_latest_prices


def _series(*closes: float) -> pd.Series:
    return pd.Series(list(closes), dtype=float)


def _close_history(ticker: str, closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({ticker: closes})


class _StubProvider:
    def __init__(self, *, close_series_fn=None, close_history_fn=None) -> None:
        self._close_series_fn = close_series_fn
        self._close_history_fn = close_history_fn

    def fetch_close_series(self, ticker: str, period: str):
        if self._close_series_fn is None:
            return None
        return self._close_series_fn(ticker, period)

    def fetch_close_history(self, tickers: list[str], start: date, end: date):
        if self._close_history_fn is None:
            return None
        return self._close_history_fn(tickers, start, end)


def _install_provider(monkeypatch: pytest.MonkeyPatch, provider: _StubProvider) -> None:
    monkeypatch.setattr(pricing_helpers, "get_provider", lambda: provider)


class TestFetchLatestPrices:
    def test_single(self, monkeypatch: pytest.MonkeyPatch):
        _install_provider(
            monkeypatch,
            _StubProvider(close_series_fn=lambda _ticker, _period: _series(99.0, 100.5, 101.0)),
        )

        result = fetch_latest_prices(["AAPL"])

        assert result == {"AAPL": 101.0}

    def test_multiple(self, monkeypatch: pytest.MonkeyPatch):
        prices_map = {"AAPL": 150.0, "SPY": 500.0}
        _install_provider(
            monkeypatch,
            _StubProvider(close_series_fn=lambda ticker, _period: _series(prices_map[ticker])),
        )

        result = fetch_latest_prices(["AAPL", "SPY"])

        assert result == {"AAPL": 150.0, "SPY": 500.0}

    def test_empty_list_makes_no_provider_calls(self, monkeypatch: pytest.MonkeyPatch):
        called: list[str] = []
        _install_provider(
            monkeypatch,
            _StubProvider(close_series_fn=lambda ticker, _period: called.append(ticker) or None),
        )

        fetch_latest_prices([])

        assert called == []

    def test_provider_none_omits_ticker(self, monkeypatch: pytest.MonkeyPatch):
        _install_provider(
            monkeypatch,
            _StubProvider(close_series_fn=lambda _ticker, _period: None),
        )

        assert fetch_latest_prices(["AAPL"]) == {}

    def test_one_failing_ticker_does_not_block_others(self, monkeypatch: pytest.MonkeyPatch):
        def _stub(ticker: str, period: str) -> pd.Series | None:
            return None if ticker == "BAD" else _series(200.0)

        _install_provider(monkeypatch, _StubProvider(close_series_fn=_stub))

        result = fetch_latest_prices(["GOOD", "BAD"])

        assert result == {"GOOD": 200.0}


class TestBenchmarkStats:
    def _stats(
        self,
        ticker: str,
        initial_cash: float,
        created_at: str,
        close_history_fn,
        today_fn=date.today,
        monkeypatch: pytest.MonkeyPatch | None = None,
    ) -> tuple[float | None, float | None]:
        if monkeypatch is not None:
            _install_provider(monkeypatch, _StubProvider(close_history_fn=close_history_fn))
            monkeypatch.setattr(
                pricing_helpers,
                "date",
                type(
                    "StubDate",
                    (),
                    {
                        "today": staticmethod(today_fn),
                        "fromisoformat": staticmethod(date.fromisoformat),
                    },
                ),
            )

        return benchmark_stats(
            ticker,
            initial_cash,
            created_at,
        )

    def test_normal(self, monkeypatch: pytest.MonkeyPatch):
        equity, ret = self._stats(
            "SPY",
            10_000.0,
            "2024-01-01T00:00:00",
            lambda tickers, start, end: _close_history(tickers[0], [100.0, 110.0, 120.0]),
            monkeypatch=monkeypatch,
        )

        assert equity == pytest.approx(12_000.0)
        assert ret == pytest.approx(20.0)

    def test_ticker_normalized_to_uppercase(self, monkeypatch: pytest.MonkeyPatch):
        calls: list[list[str]] = []

        def _stub(tickers: list[str], start: date, end: date) -> pd.DataFrame:
            calls.append(tickers)
            return _close_history(tickers[0], [50.0, 50.0])

        equity, ret = self._stats(" spy ", 1_000.0, "2024-01-01", _stub, monkeypatch=monkeypatch)

        assert equity == pytest.approx(1_000.0)
        assert ret == pytest.approx(0.0)
        assert calls == [["SPY"]]

    def test_provider_value_error_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        def _raise(*args, **kwargs):
            raise ValueError("no data")

        assert self._stats("SPY", 10_000.0, "2024-01-01", _raise, monkeypatch=monkeypatch) == (None, None)

    def test_provider_os_error_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        def _raise(*args, **kwargs):
            raise OSError("timeout")

        assert self._stats("SPY", 10_000.0, "2024-01-01", _raise, monkeypatch=monkeypatch) == (None, None)

    def test_uses_created_at_date(self, monkeypatch: pytest.MonkeyPatch):
        calls: list[tuple] = []

        def _stub(tickers: list[str], start: date, end: date) -> pd.DataFrame:
            calls.append((tickers, start, end))
            return _close_history(tickers[0], [10.0, 20.0])

        self._stats("QQQ", 5_000.0, "2023-06-15T12:34:56", _stub, monkeypatch=monkeypatch)

        assert calls[0][1] == date(2023, 6, 15)

    def test_duplicate_ticker_columns_uses_first(self, monkeypatch: pytest.MonkeyPatch):
        def _stub(_tickers: list[str], _start: date, _end: date) -> pd.DataFrame:
            return pd.DataFrame(
                [[100.0, 100.0], [110.0, 111.0], [120.0, 122.0]],
                columns=["SPY", "SPY"],
            )

        equity, ret = self._stats("SPY", 10_000.0, "2024-01-01", _stub, monkeypatch=monkeypatch)

        assert equity == pytest.approx(12_000.0)
        assert ret == pytest.approx(20.0)

    def test_duplicate_columns_zero_width_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        class _CloseHistory:
            def __getitem__(self, _ticker):
                return pd.DataFrame(index=[0, 1])

        assert self._stats(
            "SPY",
            10_000.0,
            "2024-01-01",
            lambda *_args, **_kwargs: _CloseHistory(),
            monkeypatch=monkeypatch,
        ) == (None, None)

    def test_all_nan_series_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        assert self._stats(
            "SPY",
            10_000.0,
            "2024-01-01",
            lambda tickers, start, end: _close_history(tickers[0], [float("nan"), float("nan")]),
            monkeypatch=monkeypatch,
        ) == (None, None)
