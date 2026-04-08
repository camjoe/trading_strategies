"""News sentiment feature provider.

Fetches recent news headlines for a ticker and scores them with VADER
sentiment analysis.  Two headline sources are supported:

Primary (no API key required):
    RSS feeds from Yahoo Finance, Google News, and Reuters/MarketWatch
    are fetched with urllib and parsed with the standard-library ``xml``
    module to extract ``<title>`` elements.

Optional (requires NEWS_API_KEY env var):
    NewsAPI (newsapi.org) is used as a supplementary source when the key
    is present, broadening headline coverage.

Features emitted:
    news_sentiment_score    — Mean VADER compound score across recent
                              headlines, in [-1, 1].  Positive = bullish,
                              negative = bearish.
    news_headline_count     — Number of headlines scored (float for
                              compatibility with feature_history DataFrames).
                              Zero indicates no usable headlines were found.
"""
from __future__ import annotations

import logging
import os
import urllib.request
import xml.etree.ElementTree as ET
from urllib.error import URLError

from trading.features.base import ExternalFeatureBundle, ExternalFeatureProvider

_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature name constants
# ---------------------------------------------------------------------------

NEWS_SENTIMENT_SCORE = "news_sentiment_score"
NEWS_HEADLINE_COUNT = "news_headline_count"

# ---------------------------------------------------------------------------
# RSS feed templates
# ---------------------------------------------------------------------------

# {ticker} is replaced at fetch time.
_RSS_TEMPLATES: tuple[str, ...] = (
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US",
    "https://news.google.com/rss/search?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en",
)

# Total headline cap across all RSS feeds combined.
_MAX_TOTAL_RSS_HEADLINES = 20

# Minimum headlines required to emit an available bundle.
_MIN_HEADLINE_THRESHOLD = 3

# Request timeout for each RSS fetch (seconds).
_RSS_TIMEOUT_SECONDS = 8

# NewsAPI env-var name — key is optional; used only when present.
_NEWS_API_KEY_ENV = "NEWS_API_KEY"

# Maximum NewsAPI articles to fetch per ticker.
_NEWS_API_MAX_ARTICLES = 20

# ---------------------------------------------------------------------------
# Signal thresholds — imported by strategy_signals._news_sentiment_signal
# ---------------------------------------------------------------------------

NEWS_BUY_SENTIMENT_THRESHOLD = 0.10
NEWS_SELL_SENTIMENT_THRESHOLD = -0.10
NEWS_MIN_HEADLINES_REQUIRED = 3.0


class NewsFeatureProvider(ExternalFeatureProvider):
    """Score recent news sentiment for a given ticker using VADER.

    Example usage::

        provider = NewsFeatureProvider()
        bundle = provider.get_features("AAPL")
        if not bundle.available:
            return "hold"
        score = bundle.get(NEWS_SENTIMENT_SCORE, 0.0)
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        self._analyzer = SentimentIntensityAnalyzer()

    @property
    def source_label(self) -> str:
        return "rss+vader"

    @property
    def _feature_names(self) -> tuple[str, ...]:
        return (NEWS_SENTIMENT_SCORE, NEWS_HEADLINE_COUNT)

    def _fetch(self, ticker: str) -> ExternalFeatureBundle:
        headlines = self._collect_headlines(ticker)
        if len(headlines) < _MIN_HEADLINE_THRESHOLD:
            _LOG.debug(
                "NewsFeatureProvider: only %d headlines for %s (min %d)",
                len(headlines), ticker, _MIN_HEADLINE_THRESHOLD,
            )
            return ExternalFeatureBundle.unavailable(source=self.source_label)

        scores = [self._analyzer.polarity_scores(h)["compound"] for h in headlines]
        mean_score = sum(scores) / len(scores)

        return ExternalFeatureBundle(
            features={
                NEWS_SENTIMENT_SCORE: round(mean_score, 6),
                NEWS_HEADLINE_COUNT: float(len(headlines)),
            },
            available=True,
            source=self.source_label,
        )

    # ------------------------------------------------------------------
    # Headline collection
    # ------------------------------------------------------------------

    def _collect_headlines(self, ticker: str) -> list[str]:
        headlines: list[str] = []
        headlines.extend(self._fetch_rss_headlines(ticker))
        headlines.extend(self._fetch_newsapi_headlines(ticker))
        return headlines

    def _fetch_rss_headlines(self, ticker: str) -> list[str]:
        headlines: list[str] = []
        for template in _RSS_TEMPLATES:
            url = template.format(ticker=ticker)
            try:
                with urllib.request.urlopen(url, timeout=_RSS_TIMEOUT_SECONDS) as resp:
                    body = resp.read()
                root = ET.fromstring(body)
                for item in root.iter("item"):
                    title = item.findtext("title")
                    if title:
                        headlines.append(title.strip())
                        if len(headlines) >= _MAX_TOTAL_RSS_HEADLINES:
                            break
            except (URLError, ET.ParseError, OSError) as exc:
                _LOG.debug("NewsFeatureProvider: RSS fetch failed (%s): %s", url, exc)
        return headlines

    def _fetch_newsapi_headlines(self, ticker: str) -> list[str]:
        api_key = os.getenv(_NEWS_API_KEY_ENV)
        if not api_key:
            return []
        try:
            from newsapi import NewsApiClient

            client = NewsApiClient(api_key=api_key)
            response = client.get_everything(
                q=ticker,
                language="en",
                sort_by="publishedAt",
                page_size=_NEWS_API_MAX_ARTICLES,
            )
            articles = response.get("articles") or []
            return [
                a.get("title") or a.get("description") or ""
                for a in articles
                if a.get("title") or a.get("description")
            ]
        except Exception as exc:
            _LOG.warning("NewsFeatureProvider: NewsAPI fetch failed: %s", exc)
            return []
