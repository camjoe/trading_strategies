import pandas as pd
import pytest

from trends.data import fetch_data


def test_fetch_data_flattens_multiindex_with_ticker_level(monkeypatch: pytest.MonkeyPatch) -> None:
    index = pd.date_range("2026-01-01", periods=3)
    columns = pd.MultiIndex.from_product(
        [["Close", "Volume"], ["AAPL"]],
        names=["Price", "Ticker"],
    )
    df = pd.DataFrame(
        [
            [100.0, 1_000_000],
            [101.0, 1_100_000],
            [102.0, 1_200_000],
        ],
        index=index,
        columns=columns,
    )

    monkeypatch.setattr("common.market_data.yf.download", lambda *args, **kwargs: df)

    out = fetch_data("AAPL", period="1y", interval="1d")

    assert "Close" in out.columns
    assert "Volume" in out.columns
    assert not isinstance(out.columns, pd.MultiIndex)


def test_fetch_data_raises_for_empty_download(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("common.market_data.yf.download", lambda *args, **kwargs: pd.DataFrame())

    with pytest.raises(ValueError, match="No data returned"):
        fetch_data("AAPL", period="1y", interval="1d")
