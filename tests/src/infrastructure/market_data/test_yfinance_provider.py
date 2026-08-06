"""Yahoo Finance adapter: download shaping, failure handling, and cache reuse."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

import infrastructure.market_data.yfinance_provider as provider_module
from infrastructure.market_data.cache import _MARKET_DATA_CACHE_TTL_SECONDS
from infrastructure.market_data.yfinance_provider import YFinanceProvider


def _bar_download(tickers: tuple[str, ...], periods: int = 3) -> pd.DataFrame:
    """A yfinance ``group_by="column"`` result carrying every bar field.

    Mirrors the vendor's two shapes: flat field columns for a single ticker,
    a (field, ticker) MultiIndex for several.
    """
    index = pd.date_range("2026-01-01", periods=periods)

    def _series(base: float, offset: float) -> list[float]:
        return [base + day + offset for day in range(periods)]

    if len(tickers) == 1:
        return pd.DataFrame(
            {
                "Open": _series(100.0, 0.0),
                "High": _series(100.0, 0.5),
                "Low": _series(100.0, -0.5),
                "Close": _series(100.0, 0.2),
                "Volume": _series(1000.0, 0.0),
            },
            index=index,
        )

    fields: dict[tuple[str, str], list[float]] = {}
    for position, ticker in enumerate(tickers):
        base = 100.0 * (position + 1)
        fields[("Open", ticker)] = _series(base, 0.0)
        fields[("High", ticker)] = _series(base, 0.5)
        fields[("Low", ticker)] = _series(base, -0.5)
        fields[("Close", ticker)] = _series(base, 0.2)
        fields[("Volume", ticker)] = _series(1000.0, 0.0)
    frame = pd.DataFrame(fields, index=index)
    frame.columns = pd.MultiIndex.from_tuples(frame.columns, names=["Field", "Ticker"])
    return frame


class TestSharedDownloadCache:
    def test_repeated_close_history_downloads_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        hist = _bar_download(("AAPL", "MSFT"))
        calls: list[dict[str, object]] = []
        monkeypatch.setattr(provider_module.yf, "download", lambda **kwargs: (calls.append(kwargs), hist)[1])
        provider = YFinanceProvider()

        first = provider.fetch_close_history(["aapl", "msft"], date(2026, 1, 1), date(2026, 1, 3))
        second = provider.fetch_close_history(["AAPL", "MSFT"], date(2026, 1, 1), date(2026, 1, 3))

        assert len(calls) == 1
        pd.testing.assert_frame_equal(first, second)

    def test_closes_and_bars_over_the_same_range_share_one_download(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Both bulk reads derive from the same request, so a run pays for it once."""
        hist = _bar_download(("AAPL", "MSFT"))
        calls: list[dict[str, object]] = []
        monkeypatch.setattr(provider_module.yf, "download", lambda **kwargs: (calls.append(kwargs), hist)[1])
        provider = YFinanceProvider()

        closes = provider.fetch_close_history(["AAPL", "MSFT"], date(2026, 1, 1), date(2026, 1, 3))
        bars = provider.fetch_bar_history(["AAPL", "MSFT"], date(2026, 1, 1), date(2026, 1, 3))

        assert len(calls) == 1
        assert set(bars) == {"AAPL", "MSFT"}
        assert list(closes.columns) == ["AAPL", "MSFT"]

    def test_a_different_date_range_is_a_separate_download(self, monkeypatch: pytest.MonkeyPatch) -> None:
        hist = _bar_download(("AAPL",))
        calls: list[dict[str, object]] = []
        monkeypatch.setattr(provider_module.yf, "download", lambda **kwargs: (calls.append(kwargs), hist)[1])
        provider = YFinanceProvider()

        provider.fetch_bar_history(["AAPL"], date(2026, 1, 1), date(2026, 1, 3))
        provider.fetch_bar_history(["AAPL"], date(2026, 2, 1), date(2026, 2, 3))

        assert len(calls) == 2

    def test_an_empty_download_is_not_cached(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Caching a failed fetch would pin the outage for the whole TTL."""
        calls: list[dict[str, object]] = []
        monkeypatch.setattr(
            provider_module.yf,
            "download",
            lambda **kwargs: (calls.append(kwargs), pd.DataFrame())[1],
        )
        provider = YFinanceProvider()

        for _ in range(2):
            with pytest.raises(ValueError, match="No historical price data returned"):
                provider.fetch_close_history(["AAPL"], date(2026, 1, 1), date(2026, 1, 3))

        assert len(calls) == 2

    def test_cache_write_failure_still_returns_the_data(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("TRADING_MARKET_DATA_CACHE_DIR", str(tmp_path))
        monkeypatch.setattr(provider_module.yf, "download", lambda **_kwargs: _bar_download(("AAPL",), periods=2))
        original_open = Path.open

        def _failing_open(self: Path, *args: object, **kwargs: object):
            if self.suffix == ".pkl":
                raise PermissionError("cache path is read-only")
            return original_open(self, *args, **kwargs)

        monkeypatch.setattr(Path, "open", _failing_open)

        result = YFinanceProvider().fetch_close_history(["AAPL"], date(2026, 1, 1), date(2026, 1, 2))

        assert list(result.columns) == ["AAPL"]


class TestFetchCloseHistory:
    def test_empty_ticker_list_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="At least one ticker is required"):
            YFinanceProvider().fetch_close_history([], date(2026, 1, 1), date(2026, 1, 2))

    def test_empty_download_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(provider_module.yf, "download", lambda **_kwargs: pd.DataFrame())

        with pytest.raises(ValueError, match="No historical price data returned"):
            YFinanceProvider().fetch_close_history(["AAPL"], date(2026, 1, 1), date(2026, 1, 2))

    def test_missing_close_column_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        hist = pd.DataFrame(
            {("Open", "AAPL"): [100.0], ("Open", "MSFT"): [200.0]},
            index=pd.date_range("2026-01-01", periods=1),
        )
        hist.columns = pd.MultiIndex.from_tuples(hist.columns)
        monkeypatch.setattr(provider_module.yf, "download", lambda **_kwargs: hist)

        with pytest.raises(ValueError, match="missing Close column"):
            YFinanceProvider().fetch_close_history(["AAPL", "MSFT"], date(2026, 1, 1), date(2026, 1, 2))

    def test_all_null_history_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        hist = pd.DataFrame(
            {"Close": [float("nan"), float("nan")]},
            index=pd.date_range("2026-01-01", periods=2),
        )
        monkeypatch.setattr(provider_module.yf, "download", lambda **_kwargs: hist)

        with pytest.raises(ValueError, match="Close price history is empty after cleaning"):
            YFinanceProvider().fetch_close_history(["AAPL"], date(2026, 1, 1), date(2026, 1, 2))

    def test_a_requested_ticker_absent_from_the_download_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A partial frame would silently backtest a smaller universe than asked for."""
        hist = pd.DataFrame(
            {("Close", "AAPL"): [100.0, 101.0]},
            index=pd.date_range("2026-01-01", periods=2),
        )
        hist.columns = pd.MultiIndex.from_tuples(hist.columns)
        monkeypatch.setattr(provider_module.yf, "download", lambda **_kwargs: hist)

        with pytest.raises(ValueError, match="Missing close history for tickers: MSFT"):
            YFinanceProvider().fetch_close_history(["AAPL", "MSFT"], date(2026, 1, 1), date(2026, 1, 2))


class TestFetchBarHistory:
    def test_empty_ticker_list_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="At least one ticker is required"):
            YFinanceProvider().fetch_bar_history([], date(2026, 1, 1), date(2026, 1, 2))

    def test_empty_download_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(provider_module.yf, "download", lambda **_kwargs: pd.DataFrame())

        with pytest.raises(ValueError, match="No historical bar data returned"):
            YFinanceProvider().fetch_bar_history(["AAPL"], date(2026, 1, 1), date(2026, 1, 2))

    def test_a_ticker_without_bars_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A partial result would silently backtest a smaller universe than asked for."""
        monkeypatch.setattr(provider_module.yf, "download", lambda **_kwargs: _bar_download(("AAPL", "MSFT")))

        with pytest.raises(ValueError, match="Missing bar history for tickers: NFLX"):
            YFinanceProvider().fetch_bar_history(["AAPL", "MSFT", "NFLX"], date(2026, 1, 1), date(2026, 1, 3))


class TestFetchOhlcv:
    def test_multiindex_columns_are_narrowed_to_the_requested_ticker(self, monkeypatch: pytest.MonkeyPatch) -> None:
        index = pd.date_range("2026-01-01", periods=2)
        hist = pd.DataFrame(
            {
                ("Close", "MSFT"): [200.0, 201.0],
                ("Volume", "MSFT"): [20.0, 21.0],
                ("Close", "AAPL"): [100.0, 101.0],
                ("Volume", "AAPL"): [10.0, 11.0],
            },
            index=index,
        )
        hist.columns = pd.MultiIndex.from_tuples(hist.columns, names=["Field", "Ticker"])
        calls: list[object] = []
        monkeypatch.setattr(
            provider_module.yf,
            "download",
            lambda *args, **kwargs: (calls.append((args, kwargs)), hist)[1],
        )
        provider = YFinanceProvider()

        first = provider.fetch_ohlcv("AAPL", "1mo", "1d")
        second = provider.fetch_ohlcv(" aapl ", "1mo", "1d")

        assert len(calls) == 1
        assert list(first.columns) == ["Close", "Volume"]
        assert float(first.iloc[-1]["Close"]) == 101.0
        pd.testing.assert_frame_equal(first, second)

    def test_multiindex_without_ticker_names_is_flattened(self, monkeypatch: pytest.MonkeyPatch) -> None:
        hist = pd.DataFrame(
            {("Close", "raw"): [100.0], ("Volume", "raw"): [10.0]},
            index=pd.date_range("2026-01-01", periods=1),
        )
        hist.columns = pd.MultiIndex.from_tuples(hist.columns)
        monkeypatch.setattr(provider_module.yf, "download", lambda *args, **kwargs: hist)

        assert list(YFinanceProvider().fetch_ohlcv("SPY", "5d", "1d").columns) == ["Close", "Volume"]

    def test_empty_download_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(provider_module.yf, "download", lambda *args, **kwargs: pd.DataFrame())

        with pytest.raises(ValueError, match="No data returned for ticker"):
            YFinanceProvider().fetch_ohlcv("SPY", "1mo", "1d")


class TestFetchCloseSeries:
    @staticmethod
    def _fake_ticker(history: pd.DataFrame, calls: list[str] | None = None):
        class _FakeTicker:
            def __init__(self, ticker: str) -> None:
                self.ticker = ticker

            def history(self, *, period: str, auto_adjust: bool) -> pd.DataFrame:
                assert auto_adjust is True
                if calls is not None:
                    calls.append(f"{self.ticker}:{period}")
                return history

        return _FakeTicker

    def test_repeated_reads_fetch_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        history = pd.DataFrame({"Close": [100.0, 101.0, 102.0]}, index=pd.date_range("2026-01-01", periods=3))
        calls: list[str] = []
        monkeypatch.setattr(provider_module.yf, "Ticker", self._fake_ticker(history, calls))
        provider = YFinanceProvider()

        first = provider.fetch_close_series("spy", "5d")
        second = provider.fetch_close_series("SPY", "5d")

        assert len(calls) == 1
        assert first is not None and second is not None
        pd.testing.assert_series_equal(first, second)

    def test_a_stale_entry_is_refetched(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TRADING_MARKET_DATA_CACHE_DIR", str(tmp_path))
        index = pd.date_range("2026-01-01", periods=2)
        queued = [
            pd.DataFrame({"Close": [100.0, 101.0]}, index=index),
            pd.DataFrame({"Close": [102.0, 103.0]}, index=index),
        ]

        class _FakeTicker:
            def __init__(self, ticker: str) -> None:
                self.ticker = ticker

            def history(self, *, period: str, auto_adjust: bool) -> pd.DataFrame:
                return queued.pop(0)

        monkeypatch.setattr(provider_module.yf, "Ticker", _FakeTicker)
        provider = YFinanceProvider()

        first = provider.fetch_close_series("SPY", "5d")
        cache_files = list(tmp_path.glob("*.pkl"))
        assert len(cache_files) == 1

        stale_time = os.path.getmtime(cache_files[0]) - (_MARKET_DATA_CACHE_TTL_SECONDS + 1)
        os.utime(cache_files[0], (stale_time, stale_time))
        second = provider.fetch_close_series("SPY", "5d")

        assert first is not None and second is not None
        assert float(first.iloc[-1]) == 101.0
        assert float(second.iloc[-1]) == 103.0

    @pytest.mark.parametrize(
        "history",
        [
            pd.DataFrame(),
            pd.DataFrame({"Close": [float("nan"), float("nan")]}, index=pd.date_range("2026-01-01", periods=2)),
        ],
    )
    def test_empty_history_returns_none(self, history: pd.DataFrame, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(provider_module.yf, "Ticker", self._fake_ticker(history))

        assert YFinanceProvider().fetch_close_series("SPY", "5d") is None

    def test_a_vendor_error_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _FakeTicker:
            def __init__(self, ticker: str) -> None:
                self.ticker = ticker

            def history(self, *, period: str, auto_adjust: bool) -> pd.DataFrame:
                raise RuntimeError(f"failed for {period}:{auto_adjust}")

        monkeypatch.setattr(provider_module.yf, "Ticker", _FakeTicker)

        assert YFinanceProvider().fetch_close_series("SPY", "5d") is None
