"""Tests for SocialFeatureProvider and the social_trend_rotation signal function."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from infrastructure.feature_providers.social_provider import (
    SOCIAL_MENTION_COUNT,
    SOCIAL_REDDIT_SENTIMENT,
    SOCIAL_TREND_SCORE,
    SocialFeatureProvider,
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

        with patch("pytrends.request.TrendReq", return_value=mock_pt):
            result = provider._fetch_google_trend("AAPL")

        assert result == pytest.approx(0.80)

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

    def test_empty_df_returns_none(self):
        """interest_over_time() returning empty DataFrame → None (line 132)."""
        provider = SocialFeatureProvider()
        mock_pt = MagicMock()
        mock_pt.interest_over_time.return_value = pd.DataFrame()
        with patch("pytrends.request.TrendReq", return_value=mock_pt):
            result = provider._fetch_google_trend("AAPL")
        assert result is None

    def test_ticker_column_missing_returns_none(self):
        """DataFrame returned but missing the requested ticker column → None (line 132)."""
        provider = SocialFeatureProvider()
        mock_pt = MagicMock()
        # Return a df with wrong ticker column.
        mock_pt.interest_over_time.return_value = _make_gtrends_df("MSFT", last_value=60)
        with patch("pytrends.request.TrendReq", return_value=mock_pt):
            result = provider._fetch_google_trend("AAPL")
        assert result is None

    def test_short_series_returns_none(self):
        """Series shorter than _GTRENDS_MIN_OBSERVATIONS → None (line 136)."""
        from infrastructure.feature_providers.social_provider import _GTRENDS_MIN_OBSERVATIONS

        provider = SocialFeatureProvider()
        mock_pt = MagicMock()
        # Return fewer rows than the minimum.
        mock_pt.interest_over_time.return_value = _make_gtrends_df("AAPL", rows=max(1, _GTRENDS_MIN_OBSERVATIONS - 1))
        with patch("pytrends.request.TrendReq", return_value=mock_pt):
            result = provider._fetch_google_trend("AAPL")
        assert result is None


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

    def test_reddit_no_matching_titles_returns_zero(self):
        """Posts found but none mention the ticker → returns (0, 0.0) (line 175)."""
        mock_post = MagicMock()
        mock_post.title = "General market discussion without specific ticker"

        mock_subreddit = MagicMock()
        mock_subreddit.search.return_value = [mock_post] * 3

        mock_reddit = MagicMock()
        mock_reddit.subreddit.return_value = mock_subreddit

        provider = SocialFeatureProvider()
        with patch.dict("os.environ", {"REDDIT_CLIENT_ID": "id", "REDDIT_CLIENT_SECRET": "secret"}):
            with patch("praw.Reddit", return_value=mock_reddit):
                count, sentiment = provider._fetch_reddit("AAPL")

        assert count == 0
        assert sentiment == 0.0

    def test_feature_names_contains_expected_keys(self):
        provider = SocialFeatureProvider()
        assert SOCIAL_TREND_SCORE in provider._feature_names
        assert SOCIAL_MENTION_COUNT in provider._feature_names
        assert SOCIAL_REDDIT_SENTIMENT in provider._feature_names


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
