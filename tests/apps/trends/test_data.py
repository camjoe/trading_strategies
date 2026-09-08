import pandas as pd
import pytest

from apps.trends.data import fetch_data
from infrastructure.market_data import YFinanceProvider


def test_fetch_data_flattens_multiindex_with_ticker_level(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("TRADING_MARKET_DATA_CACHE_DIR", str(tmp_path))
    index = pd.date_range("2026-01-01", periods=3)
    fields = ("Open", "High", "Low", "Close", "Volume")
    columns = pd.MultiIndex.from_product([list(fields), ["AAPL"]], names=["Price", "Ticker"])
    df = pd.DataFrame(
        [[100.0 + row for _ in fields] for row in range(3)],
        index=index,
        columns=columns,
    )

    monkeypatch.setattr("infrastructure.market_data.yfinance_provider.yf.download", lambda *args, **kwargs: df)

    out = fetch_data("AAPL", period="1y", interval="1d", provider=YFinanceProvider())

    assert list(out.columns) == list(fields)
    assert not isinstance(out.columns, pd.MultiIndex)


def test_fetch_data_raises_for_empty_download(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("TRADING_MARKET_DATA_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(
        "infrastructure.market_data.yfinance_provider.yf.download", lambda *args, **kwargs: pd.DataFrame()
    )

    with pytest.raises(ValueError, match="No data returned"):
        fetch_data("AAPL", period="1y", interval="1d", provider=YFinanceProvider())
