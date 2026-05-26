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


def test_proxy_feature_provider_loads_category_proxy_mappings(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    category_file = tmp_path / "categories.txt"
    category_file.write_text("ignored\n", encoding="utf-8")
    monkeypatch.setattr(
        "trading.services.market_data.features.load_ticker_categories",
        lambda _path: {"tech": ["aapl"], "financials": ["msft"]},
    )
    provider = ProxyFeatureDataProvider(category_file=str(category_file))

    mapping, warnings = provider._load_proxy_map(["AAPL", "XLF"])

    assert mapping["AAPL"] == "XLK"
    assert mapping["MSFT"] == "XLF"
    assert mapping["XLF"] == "XLF"
    assert warnings == []


def test_proxy_feature_provider_returns_empty_bundle_for_empty_close_history() -> None:
    bundle = ProxyFeatureDataProvider(category_file="missing_categories.txt").build_feature_bundle(
        ["AAPL"],
        date(2026, 1, 1),
        date(2026, 1, 31),
        pd.DataFrame(),
    )

    assert bundle.ticker_features == {}
    assert bundle.market_features is None
    assert bundle.warnings == ()


def test_proxy_feature_provider_marks_unmapped_tickers_and_normalizes_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = pd.date_range("2026-01-01", periods=40, freq="B", tz="UTC")
    close_history = pd.DataFrame(
        {
            "XLK": [100.0 + i for i in range(40)],
            "UNMAPPED": [50.0 + (i * 0.5) for i in range(40)],
        },
        index=index,
    )
    proxy_frame = pd.DataFrame(
        {
            "SPY": [100.0 + (i * 0.2) for i in range(40)],
            "TLT": [100.0 + (i * 0.05) for i in range(40)],
            "^VIX": [20.0 + ((i % 5) * 0.1) for i in range(40)],
            "XLK": [100.0 + (i * 0.35) for i in range(40)],
        },
        index=index.tz_convert(None),
    )

    class StubProvider:
        def fetch_close_history(self, tickers: list[str], _start, _end) -> pd.DataFrame:
            return proxy_frame.loc[:, tickers]

    monkeypatch.setattr(market_data, "get_provider", lambda: StubProvider())
    provider = ProxyFeatureDataProvider(category_file="missing_categories.txt")

    bundle = provider.build_feature_bundle(["XLK", "UNMAPPED"], date(2026, 1, 1), date(2026, 3, 1), close_history)

    mapped = bundle.history_for_ticker("XLK", index[-1])
    unmapped = bundle.history_for_ticker("UNMAPPED", index[-1])
    assert mapped is not None and unmapped is not None
    assert mapped.index.tz is None
    assert float(unmapped["topic_proxy_available"].iloc[-1]) == 0.0
    assert pd.isna(unmapped["topic_proxy_rel_strength"].iloc[-1])
    assert pd.isna(unmapped["topic_proxy_trend_gap"].iloc[-1])
    assert any("Topic proxy mappings were unavailable for: UNMAPPED" in warning for warning in bundle.warnings)
    assert any("Proxy features use sector/theme ETFs" in warning for warning in bundle.warnings)


def test_feature_bundle_history_for_ticker_returns_none_for_missing_ticker() -> None:
    bundle = FeatureBundle(ticker_features={})
    result = bundle.history_for_ticker("MISSING", pd.Timestamp("2026-01-01"))
    assert result is None


def test_feature_bundle_history_for_ticker_returns_none_for_empty_frame() -> None:
    bundle = FeatureBundle(ticker_features={"AAPL": pd.DataFrame()})
    result = bundle.history_for_ticker("AAPL", pd.Timestamp("2026-01-01"))
    assert result is None


def test_feature_bundle_history_for_ticker_handles_timezone_aware_cutoff() -> None:
    index = pd.date_range("2026-01-01", periods=3, freq="B")
    frame = pd.DataFrame({"signal": [1.0, 2.0, 3.0]}, index=index)
    bundle = FeatureBundle(ticker_features={"SPY": frame})

    tz_cutoff = pd.Timestamp("2026-01-02 18:00:00", tz="America/New_York")
    history = bundle.history_for_ticker("SPY", tz_cutoff)
    assert history is not None
    assert len(history) >= 1


def test_feature_bundle_history_for_ticker_returns_none_when_all_data_after_cutoff() -> None:
    index = pd.date_range("2026-06-01", periods=3, freq="B")
    frame = pd.DataFrame({"signal": [1.0, 2.0, 3.0]}, index=index)
    bundle = FeatureBundle(ticker_features={"SPY": frame})

    early_cutoff = pd.Timestamp("2025-01-01")
    result = bundle.history_for_ticker("SPY", early_cutoff)
    assert result is None
