"""Tests for NewsFeatureProvider and the news_sentiment signal function."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd

from infrastructure.feature_providers.news_provider import (
    _MAX_TOTAL_RSS_HEADLINES,
    _MIN_HEADLINE_THRESHOLD,
    NEWS_HEADLINE_COUNT,
    NEWS_SENTIMENT_SCORE,
    NewsFeatureProvider,
)
from trading.domain.strategies.registry import STRATEGY_REGISTRY
from trading.domain.strategies.resolution import resolve_strategy
from trading.domain.strategies.signals.alternative import _news_sentiment_signal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rss_body(titles: list[str]) -> bytes:
    """Build a minimal RSS XML body with the given item titles."""
    items = "".join(f"<item><title>{t}</title></item>" for t in titles)
    return f"<rss><channel>{items}</channel></rss>".encode()


def _make_feature_history(score: float, count: float) -> pd.DataFrame:
    return pd.DataFrame({NEWS_SENTIMENT_SCORE: [score], NEWS_HEADLINE_COUNT: [count]})


def _make_history(n: int = 40, start: float = 100.0, slope: float = 0.5) -> pd.Series:
    return pd.Series([start + i * slope for i in range(n)])


# ---------------------------------------------------------------------------
# NewsFeatureProvider — RSS headline fetching
# ---------------------------------------------------------------------------


class TestNewsFeatureProviderRss:
    def _mock_urlopen(self, titles: list[str]):
        mock_resp = MagicMock()
        mock_resp.read.return_value = _rss_body(titles)
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return MagicMock(return_value=mock_resp)

    def test_headlines_extracted_from_rss(self):
        headlines = ["Stock rises", "Market up", "Bullish outlook"]
        provider = NewsFeatureProvider()
        with patch(
            "infrastructure.feature_providers.news_provider.urllib.request.urlopen",
            self._mock_urlopen(headlines),
        ):
            result = provider._fetch_rss_headlines("AAPL")
        assert any("rises" in h or "up" in h or "outlook" in h for h in result)

    def test_rss_failure_returns_empty_list(self):
        from urllib.error import URLError

        provider = NewsFeatureProvider()
        with patch(
            "infrastructure.feature_providers.news_provider.urllib.request.urlopen",
            side_effect=URLError("timeout"),
        ):
            result = provider._fetch_rss_headlines("AAPL")
        assert result == []

    def test_rss_breaks_at_headline_cap_per_feed(self):
        """Headline collection stops at _MAX_TOTAL_RSS_HEADLINES for a single feed."""
        many_titles = [f"Headline {i}" for i in range(_MAX_TOTAL_RSS_HEADLINES + 10)]
        provider = NewsFeatureProvider()
        # Raise on the second template so all collected items come from the first URL.
        from urllib.error import URLError

        call_count = {"n": 0}

        def _mock_urlopen(url, timeout):
            call_count["n"] += 1
            if call_count["n"] > 1:
                raise URLError("skip second template")
            mock_resp = MagicMock()
            mock_resp.read.return_value = _rss_body(many_titles)
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        with patch("infrastructure.feature_providers.news_provider.urllib.request.urlopen", _mock_urlopen):
            result = provider._fetch_rss_headlines("AAPL")

        assert len(result) == _MAX_TOTAL_RSS_HEADLINES


# ---------------------------------------------------------------------------
# NewsFeatureProvider — _fetch (bundle computation)
# ---------------------------------------------------------------------------


class TestNewsFeatureProviderFetch:
    def _provider_with_headlines(self, headlines: list[str]) -> NewsFeatureProvider:
        provider = NewsFeatureProvider()
        provider._collect_headlines = MagicMock(return_value=headlines)
        return provider

    def test_available_bundle_when_enough_headlines(self):
        headlines = ["Great earnings"] * (_MIN_HEADLINE_THRESHOLD + 2)
        provider = self._provider_with_headlines(headlines)
        bundle = provider._fetch("AAPL")
        assert bundle.available is True
        assert NEWS_SENTIMENT_SCORE in bundle.features
        assert NEWS_HEADLINE_COUNT in bundle.features

    def test_headline_count_matches(self):
        headlines = ["headline"] * 5
        provider = self._provider_with_headlines(headlines)
        bundle = provider._fetch("AAPL")
        assert bundle.get(NEWS_HEADLINE_COUNT) == 5.0

    def test_unavailable_when_below_threshold(self):
        headlines = ["only one headline"]  # below _MIN_HEADLINE_THRESHOLD
        provider = self._provider_with_headlines(headlines)
        bundle = provider._fetch("AAPL")
        assert bundle.available is False

    def test_positive_sentiment_for_bullish_headlines(self):
        headlines = [
            "Strong earnings beat expectations",
            "Record revenue growth reported",
            "Analysts upgrade stock to buy",
            "Shares surge on positive outlook",
        ]
        provider = self._provider_with_headlines(headlines)
        bundle = provider._fetch("AAPL")
        assert bundle.available is True
        assert bundle.get(NEWS_SENTIMENT_SCORE, -1.0) > 0.0

    def test_negative_sentiment_for_bearish_headlines(self):
        headlines = [
            "Company misses earnings, stock crashes",
            "Losses mount as revenue falls sharply",
            "Analysts downgrade amid disappointing outlook",
            "Shares plunge on terrible quarterly report",
        ]
        provider = self._provider_with_headlines(headlines)
        bundle = provider._fetch("AAPL")
        assert bundle.available is True
        assert bundle.get(NEWS_SENTIMENT_SCORE, 1.0) < 0.0

    def test_source_label_on_bundle(self):
        headlines = ["neutral news"] * 5
        provider = self._provider_with_headlines(headlines)
        bundle = provider._fetch("AAPL")
        assert bundle.source == "rss+vader"

    def test_newsapi_not_called_without_key(self):
        provider = NewsFeatureProvider()
        provider._fetch_rss_headlines = MagicMock(return_value=["h"] * 5)
        with patch.dict("os.environ", {}, clear=True):
            result = provider._fetch_newsapi_headlines("AAPL")
        assert result == []

    def test_newsapi_called_when_key_present(self):
        provider = NewsFeatureProvider()
        mock_client_instance = MagicMock()
        mock_client_instance.get_everything.return_value = {"articles": [{"title": f"Article {i}"} for i in range(3)]}
        with patch.dict("os.environ", {"NEWS_API_KEY": "fake-key"}):
            with patch("newsapi.NewsApiClient", return_value=mock_client_instance):
                result = provider._fetch_newsapi_headlines("AAPL")
        assert len(result) == 3

    def test_newsapi_exception_returns_empty_list(self):
        """NewsAPI fetch failure logs a warning and returns []."""
        provider = NewsFeatureProvider()
        mock_client_instance = MagicMock()
        mock_client_instance.get_everything.side_effect = RuntimeError("api quota exceeded")
        with patch.dict("os.environ", {"NEWS_API_KEY": "fake-key"}):
            with patch("newsapi.NewsApiClient", return_value=mock_client_instance):
                result = provider._fetch_newsapi_headlines("AAPL")
        assert result == []

    def test_feature_names_contains_expected_keys(self):
        provider = NewsFeatureProvider()
        assert NEWS_SENTIMENT_SCORE in provider._feature_names
        assert NEWS_HEADLINE_COUNT in provider._feature_names

    def test_collect_headlines_aggregates_rss_and_newsapi(self):
        provider = NewsFeatureProvider()
        provider._fetch_rss_headlines = MagicMock(return_value=["rss1", "rss2"])
        provider._fetch_newsapi_headlines = MagicMock(return_value=["api1"])
        result = provider._collect_headlines("AAPL")
        assert result == ["rss1", "rss2", "api1"]


# ---------------------------------------------------------------------------
# _news_sentiment_signal
# ---------------------------------------------------------------------------


class TestNewsSentimentSignal:
    def test_buy_when_trending_up_and_bullish(self):
        history = _make_history(n=40, slope=1.0)
        fh = _make_feature_history(score=0.30, count=8.0)
        assert _news_sentiment_signal(history, {}, fh) == "buy"

    def test_hold_when_features_missing(self):
        history = _make_history(n=40, slope=1.0)
        assert _news_sentiment_signal(history, {}, None) == "hold"

    def test_hold_when_history_too_short(self):
        history = _make_history(n=5)
        fh = _make_feature_history(score=0.30, count=8.0)
        assert _news_sentiment_signal(history, {}, fh) == "hold"

    def test_hold_when_headline_count_too_low(self):
        history = _make_history(n=40, slope=1.0)
        fh = _make_feature_history(score=0.30, count=1.0)
        assert _news_sentiment_signal(history, {}, fh) == "hold"

    def test_sell_when_declining_and_negative_sentiment(self):
        # Declining prices: last close < fast SMA
        history = _make_history(n=40, start=200.0, slope=-2.0)
        fh = _make_feature_history(score=-0.30, count=8.0)
        signal = _news_sentiment_signal(history, {}, fh)
        assert signal == "sell"

    def test_hold_on_neutral_sentiment_uptrend(self):
        history = _make_history(n=40, slope=1.0)
        fh = _make_feature_history(score=0.05, count=8.0)  # below buy_sentiment=0.10
        signal = _news_sentiment_signal(history, {}, fh)
        assert signal in ("hold", "sell")

    def test_custom_thresholds_respected(self):
        history = _make_history(n=40, slope=1.0)
        fh = _make_feature_history(score=0.30, count=8.0)
        # Require very high sentiment to buy
        params = {"buy_sentiment": 0.90}
        assert _news_sentiment_signal(history, params, fh) != "buy"


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


class TestNewsSentimentRegistryEntry:
    def test_registered_in_strategy_registry(self):
        assert "news_sentiment" in STRATEGY_REGISTRY

    def test_strategy_style_is_alternative(self):
        spec = STRATEGY_REGISTRY["news_sentiment"]
        assert spec.strategy_style == "alternative"

    def test_required_features_declared(self):
        spec = STRATEGY_REGISTRY["news_sentiment"]
        assert NEWS_SENTIMENT_SCORE in spec.required_features
        assert NEWS_HEADLINE_COUNT in spec.required_features

    def test_aliases_resolve_correctly(self):
        for alias in ("news", "sentiment", "news_sentiment_strategy"):
            spec = resolve_strategy(alias)
            assert spec.strategy_id == "news_sentiment"

    def test_keyword_resolve_news(self):
        assert resolve_strategy("news_driven").strategy_id == "news_sentiment"

    def test_keyword_resolve_sentiment(self):
        assert resolve_strategy("sentiment_based").strategy_id == "news_sentiment"
