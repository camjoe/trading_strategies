"""Social media trend feature provider."""

from __future__ import annotations

import logging
import os

from trading.domain.feature_provider import (
    SOCIAL_MENTION_COUNT,
    SOCIAL_MIN_REDDIT_SENTIMENT,
    SOCIAL_REDDIT_SENTIMENT,
    SOCIAL_TREND_BUY_THRESHOLD,
    SOCIAL_TREND_EXIT_THRESHOLD,
    SOCIAL_TREND_SCORE,
    ExternalFeatureBundle,
    ExternalFeatureProvider,
)

_LOG = logging.getLogger(__name__)

# Timeframe passed to pytrends (30 days of daily data).
_GTRENDS_TIMEFRAME = "today 1-m"
_GTRENDS_GEO = "US"

# Minimum non-zero observations before trusting the trend score.
_GTRENDS_MIN_OBSERVATIONS = 7

_REDDIT_SUBREDDITS = ("stocks", "investing", "wallstreetbets")
_REDDIT_POST_LIMIT = 25
_REDDIT_CLIENT_ID_ENV = "REDDIT_CLIENT_ID"
_REDDIT_CLIENT_SECRET_ENV = "REDDIT_CLIENT_SECRET"
_REDDIT_USER_AGENT_ENV = "REDDIT_USER_AGENT"
_REDDIT_DEFAULT_USER_AGENT = "trading-bot/1.0 (research only)"


class SocialFeatureProvider(ExternalFeatureProvider):
    """Derive social trend signals from Google Trends and Reddit."""

    @property
    def source_label(self) -> str:
        return "reddit+gtrends"

    @property
    def _feature_names(self) -> tuple[str, ...]:
        return (SOCIAL_TREND_SCORE, SOCIAL_MENTION_COUNT, SOCIAL_REDDIT_SENTIMENT)

    def _fetch(self, ticker: str) -> ExternalFeatureBundle:
        trend_score = self._fetch_google_trend(ticker)
        mention_count, reddit_sentiment = self._fetch_reddit(ticker)
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

    def _fetch_google_trend(self, ticker: str) -> float | None:
        """Return normalized Google Trends interest (0–1) or None on failure."""
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
        return min(1.0, max(0.0, recent / 100.0))

    def _fetch_reddit(self, ticker: str) -> tuple[int, float]:
        """Return (mention_count, mean_vader_sentiment) from Reddit."""
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

            scores = [analyzer.polarity_scores(title)["compound"] for title in titles]
            return len(titles), sum(scores) / len(scores)
        except Exception as exc:
            _LOG.warning("SocialFeatureProvider: Reddit fetch failed: %s", exc)
            return 0, 0.0


__all__ = [
    "SOCIAL_MENTION_COUNT",
    "SOCIAL_MIN_REDDIT_SENTIMENT",
    "SOCIAL_REDDIT_SENTIMENT",
    "SOCIAL_TREND_BUY_THRESHOLD",
    "SOCIAL_TREND_EXIT_THRESHOLD",
    "SOCIAL_TREND_SCORE",
    "SocialFeatureProvider",
]
