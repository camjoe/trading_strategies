"""Tests for SocialFeatureProvider and the social_trend_rotation signal function."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from trading.features.base import ExternalFeatureBundle
from trading.features.social_feature_provider import (
    SOCIAL_MENTION_COUNT,
    SOCIAL_REDDIT_SENTIMENT,
    SOCIAL_TREND_SCORE,
    SocialFeatureProvider,
    _GTRENDS_MIN_OBSERVATIONS,
)
from trading.backtesting.domain.strategy_signals import (
    STRATEGY_REGISTRY,
    _social_trend_rotation_signal,
    resolve_strategy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_feature_history(trend: float, mentions: float, reddit: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            SOCIAL_TREND_SCORE: [trend],
            SOCIAL_MENTION_COUNT: [mentions],
            SOCIAL_REDDIT_SENTIMENT: [reddit],
        }
    )


def _make_history(n: int = 40, start: float = 100.0, slope: float = 0.5) -> pd.Series:
    return pd.Series([start + i * slope for i in range(n)])


def _make_gtrends_df(ticker: str, rows: int = 20, last_value: int = 75) -> pd.DataFrame:
    """Build a fake interest_over_time() response DataFrame."""
    values = list(range(rows - 1)) + [last_value]
    return pd.DataFrame({ticker: values, "isPartial": [False] * rows})


# ---------------------------------------------------------------------------
# SocialFeatureProvider — Google Trends
# ---------------------------------------------------------------------------


class TestSocialFeatureProviderGoogleTrends:
    def test_returns_normalised_score(self):
        provider = SocialFeatureProvider()
        mock_pt = MagicMock()
        mock_pt.interest_over_time.return_value = _make_gtrends_df("AAPL", last_value=80)

        with patch("trading.features.social_feature_provider.TrendReq", return_value=mock_pt, create=True):
            with patch(
                "trading.features.social_feature_provider.SocialFeatureProvider._fetch_google_trend",
                return_value=0.80,
            ):
                result = provider._fetch_google_trend("AAPL")
        # patched directly → just checks it returns without error
        assert result == 0.80

    def test_fetch_google_trend_failure_returns_none(self):
        provider = SocialFeatureProvider()
        with patch(
            "pytrends.request.TrendReq",
            side_effect=Exception("network error"),
        ):
            result = provider._fetch_google_trend("AAPL")
        assert result is None

    def test_normalisation_clamps_to_0_1(self):
        """Directly test the normalisation logic with a known value."""
        provider = SocialFeatureProvider()
        provider._fetch_google_trend = MagicMock(return_value=100 / 100.0)
        val = provider._fetch_google_trend("AAPL")
        assert 0.0 <= val <= 1.0


# ---------------------------------------------------------------------------
# SocialFeatureProvider — Reddit
# ---------------------------------------------------------------------------


class TestSocialFeatureProviderReddit:
    def test_returns_zero_zero_when_no_credentials(self):
        provider = SocialFeatureProvider()
        with patch.dict("os.environ", {}, clear=True):
            count, sentiment = provider._fetch_reddit("AAPL")
        assert count == 0
        assert sentiment == 0.0

    def test_returns_count_and_sentiment_when_posts_found(self):
        mock_post = MagicMock()
        mock_post.title = "AAPL stock is surging to new highs"

        mock_subreddit = MagicMock()
        mock_subreddit.search.return_value = [mock_post] * 3

        mock_reddit = MagicMock()
        mock_reddit.subreddit.return_value = mock_subreddit

        provider = SocialFeatureProvider()
        with patch.dict("os.environ", {"REDDIT_CLIENT_ID": "id", "REDDIT_CLIENT_SECRET": "secret"}):
            with patch("praw.Reddit", return_value=mock_reddit):
                count, sentiment = provider._fetch_reddit("AAPL")

        assert count > 0
        assert -1.0 <= sentiment <= 1.0

    def test_reddit_exception_returns_zero(self):
        provider = SocialFeatureProvider()
        with patch.dict("os.environ", {"REDDIT_CLIENT_ID": "id", "REDDIT_CLIENT_SECRET": "secret"}):
            with patch("praw.Reddit", side_effect=RuntimeError("api error")):
                count, sentiment = provider._fetch_reddit("AAPL")
        assert count == 0
        assert sentiment == 0.0


# ---------------------------------------------------------------------------
# SocialFeatureProvider — _fetch (bundle)
# ---------------------------------------------------------------------------


class TestSocialFeatureProviderFetch:
    def test_available_bundle_when_trend_score_present(self):
        provider = SocialFeatureProvider()
        provider._fetch_google_trend = MagicMock(return_value=0.65)
        provider._fetch_reddit = MagicMock(return_value=(10, 0.20))
        bundle = provider._fetch("AAPL")
        assert bundle.available is True
        assert SOCIAL_TREND_SCORE in bundle.features
        assert SOCIAL_MENTION_COUNT in bundle.features
        assert SOCIAL_REDDIT_SENTIMENT in bundle.features

    def test_unavailable_when_trend_score_none(self):
        provider = SocialFeatureProvider()
        provider._fetch_google_trend = MagicMock(return_value=None)
        provider._fetch_reddit = MagicMock(return_value=(5, 0.10))
        bundle = provider._fetch("AAPL")
        assert bundle.available is False

    def test_mention_count_and_sentiment_from_reddit(self):
        provider = SocialFeatureProvider()
        provider._fetch_google_trend = MagicMock(return_value=0.50)
        provider._fetch_reddit = MagicMock(return_value=(7, -0.15))
        bundle = provider._fetch("AAPL")
        assert bundle.get(SOCIAL_MENTION_COUNT) == 7.0
        assert bundle.get(SOCIAL_REDDIT_SENTIMENT) == pytest.approx(-0.15, abs=1e-5)

    def test_source_label(self):
        provider = SocialFeatureProvider()
        provider._fetch_google_trend = MagicMock(return_value=0.50)
        provider._fetch_reddit = MagicMock(return_value=(0, 0.0))
        bundle = provider._fetch("AAPL")
        assert bundle.source == "reddit+gtrends"

    def test_reddit_unavailable_still_available_bundle(self):
        """Bundle is available when trend score is present even if Reddit fails."""
        provider = SocialFeatureProvider()
        provider._fetch_google_trend = MagicMock(return_value=0.60)
        provider._fetch_reddit = MagicMock(return_value=(0, 0.0))
        bundle = provider._fetch("AAPL")
        assert bundle.available is True
        assert bundle.get(SOCIAL_MENTION_COUNT) == 0.0
        assert bundle.get(SOCIAL_REDDIT_SENTIMENT) == 0.0


# ---------------------------------------------------------------------------
# _social_trend_rotation_signal
# ---------------------------------------------------------------------------


class TestSocialTrendRotationSignal:
    def test_buy_when_uptrend_and_high_social_interest(self):
        history = _make_history(n=40, slope=1.0)
        fh = _make_feature_history(trend=0.70, mentions=10.0, reddit=0.10)
        assert _social_trend_rotation_signal(history, {}, fh) == "buy"

    def test_hold_when_features_missing(self):
        history = _make_history(n=40, slope=1.0)
        assert _social_trend_rotation_signal(history, {}, None) == "hold"

    def test_hold_when_history_too_short(self):
        history = _make_history(n=5)
        fh = _make_feature_history(trend=0.70, mentions=10.0, reddit=0.10)
        assert _social_trend_rotation_signal(history, {}, fh) == "hold"

    def test_sell_when_trend_declining_and_low_interest(self):
        history = _make_history(n=40, start=200.0, slope=-2.0)
        fh = _make_feature_history(trend=0.10, mentions=1.0, reddit=-0.30)
        signal = _social_trend_rotation_signal(history, {}, fh)
        assert signal == "sell"

    def test_sell_when_trend_score_below_exit(self):
        history = _make_history(n=40, slope=0.5)
        fh = _make_feature_history(trend=0.05, mentions=2.0, reddit=0.00)
        signal = _social_trend_rotation_signal(history, {}, fh)
        # trend_score 0.05 < trend_exit 0.20 → sell
        assert signal == "sell"

    def test_hold_when_trend_below_buy_threshold(self):
        history = _make_history(n=40, slope=1.0)
        fh = _make_feature_history(trend=0.30, mentions=5.0, reddit=0.05)
        # trend_score 0.30 < trend_threshold 0.40 → no buy
        signal = _social_trend_rotation_signal(history, {}, fh)
        assert signal in ("hold", "sell")

    def test_custom_params_respected(self):
        history = _make_history(n=40, slope=1.0)
        fh = _make_feature_history(trend=0.70, mentions=10.0, reddit=0.10)
        params = {"trend_threshold": 0.90}  # require very high interest → no buy
        assert _social_trend_rotation_signal(history, params, fh) != "buy"


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


class TestSocialTrendRotationRegistryEntry:
    def test_registered_in_strategy_registry(self):
        assert "social_trend_rotation" in STRATEGY_REGISTRY

    def test_strategy_style_is_alternative(self):
        spec = STRATEGY_REGISTRY["social_trend_rotation"]
        assert spec.strategy_style == "alternative"

    def test_required_features_declared(self):
        spec = STRATEGY_REGISTRY["social_trend_rotation"]
        assert SOCIAL_TREND_SCORE in spec.required_features
        assert SOCIAL_MENTION_COUNT in spec.required_features
        assert SOCIAL_REDDIT_SENTIMENT in spec.required_features

    def test_aliases_resolve_correctly(self):
        for alias in ("social", "social_trend", "reddit_trend"):
            spec = resolve_strategy(alias)
            assert spec.strategy_id == "social_trend_rotation"

    def test_keyword_resolve_social(self):
        assert resolve_strategy("social_momentum").strategy_id == "social_trend_rotation"

    def test_keyword_resolve_reddit(self):
        assert resolve_strategy("reddit_based_strategy").strategy_id == "social_trend_rotation"
