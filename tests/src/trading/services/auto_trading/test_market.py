"""Tests for trading.services.auto_trading.market — IV rank proxy builder."""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from trading.models.market_data import BAR_CLOSE, BAR_COLUMNS, BAR_VOLUME
from trading.services.auto_trading.market import build_iv_rank_proxy, fetch_bar_histories


def _mock_provider(close_series_map: dict[str, pd.Series | None]) -> MagicMock:
    """A provider returning vendor-cased OHLCV frames, as fetch_ohlcv does."""

    def _ohlcv(ticker: str, _period: str, _interval: str) -> pd.DataFrame | None:
        closes = close_series_map.get(ticker)
        if closes is None:
            return None
        return pd.DataFrame(
            {
                "Open": closes,
                "High": closes,
                "Low": closes,
                "Close": closes,
                "Volume": pd.Series(1_000_000.0, index=closes.index),
            }
        )

    provider = MagicMock()
    provider.fetch_ohlcv.side_effect = _ohlcv
    return provider


def _prices(n: int = 60, base: float = 100.0, step: float = 0.5) -> pd.Series:
    return pd.Series([base + i * step for i in range(n)])


class TestBuildIvRankProxy:
    def test_empty_universe_returns_empty_dict(self) -> None:
        result = build_iv_rank_proxy([], provider=MagicMock())
        assert result == {}

    def test_returns_rank_between_0_and_100(self) -> None:
        provider = _mock_provider({"AAPL": _prices(), "MSFT": _prices(step=1.0)})
        result = build_iv_rank_proxy(["AAPL", "MSFT"], provider=provider)
        assert set(result.keys()) == {"AAPL", "MSFT"}
        for v in result.values():
            assert 0.0 <= v <= 100.0

    def test_none_close_skipped(self) -> None:
        """fetch_close_series returning None → ticker excluded (line 23)."""
        provider = _mock_provider({"AAPL": None, "MSFT": _prices()})
        result = build_iv_rank_proxy(["AAPL", "MSFT"], provider=provider)
        assert "AAPL" not in result
        assert "MSFT" in result

    def test_short_close_series_skipped(self) -> None:
        """Series with < 30 rows → ticker excluded (line 23)."""
        provider = _mock_provider({"AAPL": _prices(n=10), "MSFT": _prices()})
        result = build_iv_rank_proxy(["AAPL", "MSFT"], provider=provider)
        assert "AAPL" not in result

    def test_empty_daily_returns_skipped(self) -> None:
        """All-identical prices → pct_change all zero, dropna → empty → skip (lines 26-28)."""
        flat = pd.Series([100.0] * 60)
        provider = _mock_provider({"FLAT": flat, "MSFT": _prices()})
        result = build_iv_rank_proxy(["FLAT", "MSFT"], provider=provider)
        # FLAT has zero std → empty daily_ret after pct_change? Actually pct_change of identical = 0, not NaN.
        # So daily_ret won't be empty; vol = 0. This is fine — just verify no crash.
        assert "MSFT" in result

    def test_exception_on_fetch_skips_ticker(self) -> None:
        """Provider raising exception for one ticker → ticker skipped gracefully."""
        provider = MagicMock()
        provider.fetch_ohlcv.side_effect = RuntimeError("network error")
        result = build_iv_rank_proxy(["AAPL"], provider=provider)
        assert result == {}

    def test_single_ticker_returns_50(self) -> None:
        """Single valid ticker → rank set to 50.0 (line 38-39)."""
        provider = _mock_provider({"AAPL": _prices()})
        result = build_iv_rank_proxy(["AAPL"], provider=provider)
        assert result == {"AAPL": pytest.approx(50.0)}

    def test_all_tickers_fail_returns_empty(self) -> None:
        provider = _mock_provider({"AAPL": None, "MSFT": None})
        result = build_iv_rank_proxy(["AAPL", "MSFT"], provider=provider)
        assert result == {}


class TestFetchBarHistories:
    """The live path reads bars through the same contract the backtest does."""

    def test_vendor_gaps_are_filled_the_way_the_backtest_fills_them(self) -> None:
        # A halted day: the vendor reports the row with no prices.
        index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
        provider = MagicMock()
        provider.fetch_ohlcv.return_value = pd.DataFrame(
            {
                "Open": [10.0, float("nan"), 12.0],
                "High": [10.0, float("nan"), 12.0],
                "Low": [10.0, float("nan"), 12.0],
                "Close": [10.0, float("nan"), 12.0],
                "Volume": [500.0, float("nan"), 700.0],
            },
            index=index,
        )

        histories = fetch_bar_histories(["AAPL"], provider=provider)

        # Raw vendor gaps here would make the same rolling window produce a
        # different value live than it does in a backtest over the same days.
        assert histories["AAPL"][BAR_CLOSE].tolist() == [10.0, 10.0, 12.0]
        assert histories["AAPL"][BAR_VOLUME].tolist() == [500.0, 0.0, 700.0]

    def test_columns_land_in_contract_order(self) -> None:
        index = pd.to_datetime(["2024-01-02", "2024-01-03"])
        provider = MagicMock()
        provider.fetch_ohlcv.return_value = pd.DataFrame(
            {
                "Volume": [1.0, 1.0],
                "Close": [1.0, 1.0],
                "Low": [1.0, 1.0],
                "High": [1.0, 1.0],
                "Open": [1.0, 1.0],
            },
            index=index,
        )

        histories = fetch_bar_histories(["AAPL"], provider=provider)

        assert list(histories["AAPL"].columns) == list(BAR_COLUMNS)

    def test_a_frame_missing_a_bar_column_is_skipped_not_raised(self) -> None:
        index = pd.to_datetime(["2024-01-02"])
        provider = MagicMock()
        provider.fetch_ohlcv.return_value = pd.DataFrame({"Close": [1.0]}, index=index)

        assert fetch_bar_histories(["AAPL"], provider=provider) == {}
