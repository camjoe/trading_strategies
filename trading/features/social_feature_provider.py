"""Social media trend feature provider.

Aggregates social signal strength for a ticker from two sources:

1. **Google Trends** (via ``pytrends``, no API key required):
   Fetches 30-day interest-over-time index for the ticker symbol.
   Returns a 0–100 normalised trend score.

2. **Reddit** (via ``praw``, requires env vars):
   Searches r/stocks, r/investing, and r/wallstreetbets for recent
   posts mentioning the ticker.  Scores each post title with VADER
   and aggregates mention count + sentiment.
   Required env vars: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET.
   Optional: REDDIT_USER_AGENT (defaults to a neutral UA string).

Features emitted:
    social_trend_score     — Google Trends interest index, normalised to
                             [0, 1].  0 = no interest, 1 = peak interest.
    social_mention_count   — Number of Reddit posts found (float).
    social_reddit_sentiment — Mean VADER compound score of Reddit post
                              titles in [-1, 1].  0.0 when Reddit is
                              unavailable.
"""
from __future__ import annotations

import logging
import os

from trading.features.base import ExternalFeatureBundle, ExternalFeatureProvider

_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature name constants
# ---------------------------------------------------------------------------

SOCIAL_TREND_SCORE = "social_trend_score"
SOCIAL_MENTION_COUNT = "social_mention_count"
SOCIAL_REDDIT_SENTIMENT = "social_reddit_sentiment"

# ---------------------------------------------------------------------------
# Google Trends config
# ---------------------------------------------------------------------------

# Timeframe passed to pytrends (30 days of daily data).
_GTRENDS_TIMEFRAME = "today 1-m"
_GTRENDS_GEO = "US"

# Minimum non-zero observations before trusting the trend score.
_GTRENDS_MIN_OBSERVATIONS = 7

# ---------------------------------------------------------------------------
# Reddit config
# ---------------------------------------------------------------------------

_REDDIT_SUBREDDITS = ("stocks", "investing", "wallstreetbets")
_REDDIT_POST_LIMIT = 25
_REDDIT_CLIENT_ID_ENV = "REDDIT_CLIENT_ID"
_REDDIT_CLIENT_SECRET_ENV = "REDDIT_CLIENT_SECRET"
_REDDIT_USER_AGENT_ENV = "REDDIT_USER_AGENT"
_REDDIT_DEFAULT_USER_AGENT = "trading-bot/1.0 (research only)"


class SocialFeatureProvider(ExternalFeatureProvider):
    """Derive social trend signals from Google Trends and Reddit.

    Both sources degrade gracefully: if Google Trends is unavailable the
    trend score is 0; if Reddit credentials are absent or the API fails
    the mention count and Reddit sentiment default to 0.

    Example usage::

        provider = SocialFeatureProvider()
        bundle = provider.get_features("GME")
        if not bundle.available:
            return "hold"
        trend = bundle.get(SOCIAL_TREND_SCORE, 0.0)
    """

    @property
    def source_label(self) -> str:
        return "reddit+gtrends"

    @property
    def _feature_names(self) -> tuple[str, ...]:
        return (SOCIAL_TREND_SCORE, SOCIAL_MENTION_COUNT, SOCIAL_REDDIT_SENTIMENT)

    def _fetch(self, ticker: str) -> ExternalFeatureBundle:
        trend_score = self._fetch_google_trend(ticker)
        mention_count, reddit_sentiment = self._fetch_reddit(ticker)

        # Require at least some signal from Google Trends to emit an available bundle.
        if trend_score is None:
            return ExternalFeatureBundle.unavailable(source=self.source_label)

        return ExternalFeatureBundle(
            features={
                SOCIAL_TREND_SCORE: round(trend_score, 6),
                SOCIAL_MENTION_COUNT: float(mention_count),
                SOCIAL_REDDIT_SENTIMENT: round(reddit_sentiment, 6),
            },
            available=True,
            source=self.source_label,
        )

    # ------------------------------------------------------------------
    # Google Trends
    # ------------------------------------------------------------------

    def _fetch_google_trend(self, ticker: str) -> float | None:
        """Return normalised Google Trends interest (0–1) or None on failure."""
        try:
            from pytrends.request import TrendReq

            pt = TrendReq(hl="en-US", tz=0)
            pt.build_payload([ticker], timeframe=_GTRENDS_TIMEFRAME, geo=_GTRENDS_GEO)
            df = pt.interest_over_time()
        except Exception as exc:
            _LOG.debug("SocialFeatureProvider: Google Trends failed for %s: %s", ticker, exc)
            return None

        if df is None or df.empty or ticker not in df.columns:
            return None

        series = df[ticker].dropna()
        if len(series) < _GTRENDS_MIN_OBSERVATIONS:
            return None

        recent = float(series.iloc[-1])
        # Normalise from [0,100] to [0,1].
        return min(1.0, max(0.0, recent / 100.0))

    # ------------------------------------------------------------------
    # Reddit
    # ------------------------------------------------------------------

    def _fetch_reddit(self, ticker: str) -> tuple[int, float]:
        """Return (mention_count, mean_vader_sentiment) from Reddit.

        Returns (0, 0.0) when credentials are absent or the fetch fails.
        """
        client_id = os.getenv(_REDDIT_CLIENT_ID_ENV)
        client_secret = os.getenv(_REDDIT_CLIENT_SECRET_ENV)
        if not client_id or not client_secret:
            return 0, 0.0

        try:
            import praw
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

            reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=os.getenv(_REDDIT_USER_AGENT_ENV, _REDDIT_DEFAULT_USER_AGENT),
            )
            analyzer = SentimentIntensityAnalyzer()
            titles: list[str] = []

            for sub_name in _REDDIT_SUBREDDITS:
                subreddit = reddit.subreddit(sub_name)
                for post in subreddit.search(ticker, limit=_REDDIT_POST_LIMIT, sort="new"):
                    if ticker.upper() in post.title.upper():
                        titles.append(post.title)

            if not titles:
                return 0, 0.0

            scores = [analyzer.polarity_scores(t)["compound"] for t in titles]
            return len(titles), sum(scores) / len(scores)

        except Exception as exc:
            _LOG.warning("SocialFeatureProvider: Reddit fetch failed: %s", exc)
            return 0, 0.0
