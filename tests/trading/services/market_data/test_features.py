from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from trading.services.market_data.features import ProxyFeatureDataProvider
from trading.services.market_data.interfaces import FeatureBundle
import trading.services.market_data as market_data


def test_feature_bundle_history_for_ticker_returns_copy_and_respects_cutoff() -> None:
    index = pd.date_range("2026-01-01", periods=3, freq="B")
    original = pd.DataFrame({"signal": [1.0, 2.0, 3.0]}, index=index)
    bundle = FeatureBundle(ticker_features={"AAPL": original})

    history = bundle.history_for_ticker("AAPL", index[1])

    assert history is not None
    assert list(history.index) == list(index[:2])
    history.iloc[0, 0] = 99.0
    assert original.iloc[0, 0] == 1.0


def test_proxy_feature_provider_reports_missing_category_file_warning() -> None:
    provider = ProxyFeatureDataProvider(category_file="missing_categories.txt")
    mapping, warnings = provider._load_proxy_map(["XLK", "AAPL"])

    assert mapping["XLK"] == "XLK"
    assert "AAPL" not in mapping
    assert any("Category file 'missing_categories.txt' not found" in warning for warning in warnings)


def test_proxy_feature_provider_returns_warning_bundle_when_proxy_fetch_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = pd.date_range("2026-01-01", periods=5, freq="B")
    close_history = pd.DataFrame({"AAPL": [100.0, 101.0, 102.0, 103.0, 104.0]}, index=index)

    class FailingProvider:
        def fetch_close_history(self, _tickers, _start, _end):
            raise ValueError("feed unavailable")

    monkeypatch.setattr(market_data, "get_provider", lambda: FailingProvider())
    provider = ProxyFeatureDataProvider(category_file="missing_categories.txt")

    bundle = provider.build_feature_bundle(["AAPL"], date(2026, 1, 1), date(2026, 1, 31), close_history)

    assert bundle.ticker_features == {}
    assert any("Proxy feature data unavailable: feed unavailable" in warning for warning in bundle.warnings)


def test_proxy_feature_provider_builds_features_for_known_proxy_ticker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = pd.date_range("2026-01-01", periods=40, freq="B")
    close_history = pd.DataFrame({"XLK": [100.0 + i for i in range(40)]}, index=index)
    proxy_frame = pd.DataFrame(
        {
            "SPY": [100.0 + (i * 0.2) for i in range(40)],
            "TLT": [100.0 + (i * 0.05) for i in range(40)],
            "^VIX": [20.0 + ((i % 5) * 0.1) for i in range(40)],
            "XLK": [100.0 + (i * 0.35) for i in range(40)],
        },
        index=index,
    )

    class StubProvider:
        def fetch_close_history(self, tickers: list[str], _start, _end) -> pd.DataFrame:
            return proxy_frame.loc[:, tickers]

    monkeypatch.setattr(market_data, "get_provider", lambda: StubProvider())
    provider = ProxyFeatureDataProvider(category_file="missing_categories.txt")

    bundle = provider.build_feature_bundle(["XLK"], date(2026, 1, 1), date(2026, 3, 1), close_history)

    features = bundle.history_for_ticker("XLK", index[-1])
    assert features is not None
    assert "topic_proxy_rel_strength" in features.columns
    assert float(features["topic_proxy_available"].iloc[-1]) == 1.0
