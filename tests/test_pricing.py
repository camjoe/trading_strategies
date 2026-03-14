from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from trading.pricing import benchmark_stats, fetch_latest_prices


def _hist(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"Close": closes})


# ---------------------------------------------------------------------------
# fetch_latest_prices
# ---------------------------------------------------------------------------

@patch("trading.pricing.yf")
def test_fetch_latest_prices_single(mock_yf):
    mock_yf.Ticker.return_value.history.return_value = _hist([99.0, 100.5, 101.0])
    assert fetch_latest_prices(["AAPL"]) == {"AAPL": 101.0}


@patch("trading.pricing.yf")
def test_fetch_latest_prices_multiple(mock_yf):
    def _side(ticker):
        m = MagicMock()
        m.history.return_value = _hist([{"AAPL": 150.0, "SPY": 500.0}[ticker]])
        return m
    mock_yf.Ticker.side_effect = _side
    result = fetch_latest_prices(["AAPL", "SPY"])
    assert result == {"AAPL": 150.0, "SPY": 500.0}


@patch("trading.pricing.yf")
def test_fetch_latest_prices_empty_list(mock_yf):
    assert fetch_latest_prices([]) == {}
    mock_yf.Ticker.assert_not_called()


@patch("trading.pricing.yf")
def test_fetch_latest_prices_empty_hist(mock_yf):
    mock_yf.Ticker.return_value.history.return_value = pd.DataFrame()
    assert fetch_latest_prices(["AAPL"]) == {}


@patch("trading.pricing.yf")
def test_fetch_latest_prices_all_nan_closes(mock_yf):
    mock_yf.Ticker.return_value.history.return_value = _hist([float("nan"), float("nan")])
    assert fetch_latest_prices(["AAPL"]) == {}


@patch("trading.pricing.yf")
def test_fetch_latest_prices_exception(mock_yf):
    mock_yf.Ticker.return_value.history.side_effect = RuntimeError("network error")
    assert fetch_latest_prices(["AAPL"]) == {}


@patch("trading.pricing.yf")
def test_fetch_latest_prices_one_fails(mock_yf):
    """One bad ticker should not prevent other results from being collected."""
    def _side(ticker):
        m = MagicMock()
        if ticker == "BAD":
            m.history.return_value = pd.DataFrame()
        else:
            m.history.return_value = _hist([200.0])
        return m
    mock_yf.Ticker.side_effect = _side
    result = fetch_latest_prices(["GOOD", "BAD"])
    assert result == {"GOOD": 200.0}


# ---------------------------------------------------------------------------
# benchmark_stats
# ---------------------------------------------------------------------------

@patch("trading.pricing.yf")
def test_benchmark_stats_normal(mock_yf):
    mock_yf.Ticker.return_value.history.return_value = _hist([100.0, 110.0, 120.0])
    equity, ret = benchmark_stats("SPY", 10_000.0, "2024-01-01T00:00:00")
    assert equity == pytest.approx(12_000.0)
    assert ret == pytest.approx(20.0)


@patch("trading.pricing.yf")
def test_benchmark_stats_ticker_normalized(mock_yf):
    mock_yf.Ticker.return_value.history.return_value = _hist([50.0, 50.0])
    equity, ret = benchmark_stats(" spy ", 1_000.0, "2024-01-01")
    assert equity == pytest.approx(1_000.0)
    assert ret == pytest.approx(0.0)
    mock_yf.Ticker.assert_called_once_with("SPY")


@patch("trading.pricing.yf")
def test_benchmark_stats_empty_hist(mock_yf):
    mock_yf.Ticker.return_value.history.return_value = pd.DataFrame()
    assert benchmark_stats("SPY", 10_000.0, "2024-01-01") == (None, None)


@patch("trading.pricing.yf")
def test_benchmark_stats_exception(mock_yf):
    mock_yf.Ticker.return_value.history.side_effect = OSError("timeout")
    assert benchmark_stats("SPY", 10_000.0, "2024-01-01") == (None, None)


@patch("trading.pricing.yf")
def test_benchmark_stats_uses_created_at_date(mock_yf):
    """created_at is truncated to date before being passed to yfinance."""
    mock_yf.Ticker.return_value.history.return_value = _hist([10.0, 20.0])
    benchmark_stats("QQQ", 5_000.0, "2023-06-15T12:34:56")
    _, call_kwargs = mock_yf.Ticker.return_value.history.call_args
    assert call_kwargs["start"] == "2023-06-15"
