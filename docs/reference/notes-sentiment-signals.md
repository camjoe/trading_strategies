# Sentiment/Topic Signal Integration Notes

Status: Active reference — Phase 4 implementation complete; remaining backlog tracked in project manager (Strategies / Technical Analysis boards)
Date: 2026-07-14 (updated from 2026-03-27 to reflect Phase 4 implementation)

Purpose: save the current-state map and integration path for sentiment, topic, and politics-driven trading strategies so future sessions and bots have the context to continue without re-auditing the codebase.

## 1. Current Signal Architecture

**Signal dispatch:**
- `trading/backtesting/domain/strategy_signals.py` — `resolve_signal()` dispatches signals via a `STRATEGY_REGISTRY`. The registry now covers 14 strategy IDs across four families: trend (SMA-based, MACD, breakout, pullback, ma_crossover, volatility_filtered_trend), mean_reversion (RSI, Bollinger, mean_reversion), neutral proxy (topic_proxy_rotation, macro_proxy_regime), and **alternative** external-data strategies (policy_regime, news_sentiment, social_trend_rotation). Strategy names are matched by exact ID, alias, or keyword fallback.
- `trading/backtesting/backtest.py` — calls signal resolver in the main simulation loop.
- `trading/features/` — new package introduced in Phase 4; houses all external-data feature providers consumed by alternative strategies (see §§ 2a and 3 below).
- `trends/indicators.py` — calculates MA20/50/200, RS/RSI14, MACD, daily returns.
- `trends/data.py` — fetches OHLCV via `get_provider().fetch_ohlcv()`.
- `common/market_data.py` — provider abstraction (currently only `YFinanceProvider`).

**Account/strategy configuration:**
- `trading/accounts.py` — creates accounts with strategy name stored in DB.
- `trading/config/account_profiles/default.json` — templates with strategies "Momentum", "Mean Reversion".

**Backtesting loop:**
- Loads price history for all tickers (start–end range).
- Each trading day: loops over active tickers, calculates signal from historical price series, executes buy/sell.
- Position sizing: 10% of equity, fees + slippage applied.
- Records trades and daily snapshots to DB via `trading/database/db.py`.

## 2. Existing Data Sources and Signals

**Current:**
- Source: yfinance (OHLCV, adjusted close). Daily bars only.
- Signals available:
  - Trend: `close > SMA10 > SMA20` → buy (30-bar lookback)
  - Mean Reversion: `close < SMA20 * 0.98` → buy (30-bar lookback)
  - RSI: RSI < 30 → buy, RSI > 70 → sell
  - MACD: MACD crosses above/below signal line

**Now also available (Phase 4 — trading/features/):**
- News headline sentiment via VADER (`news_sentiment` strategy):
  - Primary: RSS feeds from Yahoo Finance and Google News (no API key required).
  - Optional supplementary: NewsAPI (requires `NEWS_API_KEY` env var).
  - Provider: `trading/features/news_feature_provider.NewsFeatureProvider`
- Social / Reddit sentiment and Google Trends (`social_trend_rotation` strategy):
  - Google Trends 30-day interest index via `pytrends` (no key required).
  - Reddit r/stocks, r/investing, r/wallstreetbets post mentions + VADER scoring via `praw`.
  - Requires `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` env vars; degrades gracefully without them.
  - Provider: `trading/features/social_feature_provider.SocialFeatureProvider`
- Policy/macro regime via ETF price relatives (`policy_regime` strategy):
  - Uses TLT, GLD, XLU, UUP vs SPY trailing returns as a risk-on/risk-off proxy.
  - No API key required (yfinance).
  - Provider: `trading/features/policy_feature_provider.PolicyFeatureProvider`

**What is still NOT available:**
- Macro/political event calendars (policy_regime uses ETF proxies, not calendar-based event data)
- Earnings/event drivers
- Insider transactions
- Unusual options activity
- No momentum ranking across multiple securities
- No volatility or correlation features
- No intraday microstructure
- Portfolio trend inferred only from equity snapshots in `trading/reporting.py` via `infer_overall_trend`

## 3. Implemented in Phase 4 — Alternative Strategies

The following items from the original "missing pieces" list are now implemented via the `trading/features/` package:

- **News/headline sentiment** — `NewsFeatureProvider` fetches RSS headlines and scores them with VADER. Optionally supplemented by NewsAPI when `NEWS_API_KEY` is set. Signal: `news_sentiment` strategy in `STRATEGY_REGISTRY`.
- **Social media sentiment (Reddit)** — `SocialFeatureProvider` queries r/stocks, r/investing, r/wallstreetbets via `praw` and scores post titles with VADER. Signal: `social_trend_rotation` strategy.
- **Search trends (Google Trends)** — `SocialFeatureProvider` fetches 30-day ticker interest via `pytrends`. Feeds `social_trend_score` feature. Signal: `social_trend_rotation` strategy.
- **Macro/political proxy** — `PolicyFeatureProvider` uses TLT/GLD/XLU/UUP vs SPY trailing returns to derive a `policy_risk_on_score` and `policy_defensive_tilt`. Signal: `policy_regime` strategy. Note: this is an ETF-proxy approach, not a direct FRED/VIX or event-calendar integration.

**Architecture for all three:** every provider subclasses `trading.features.base.ExternalFeatureProvider`, which handles TTL-based per-ticker caching and graceful degradation (returns `ExternalFeatureBundle(available=False)` on any error). Signal functions in `strategy_signals.py` import only feature-name constants and check `bundle.available` before using values. See `.github/BOT_ARCHITECTURE_CONVENTIONS.md §External Data Strategies` for the enforced rules.

**Still not implemented (original list items remaining):**
- Macro/political event calendars (FRED, paid event databases)
- Earnings/event drivers
- Insider transactions
- Unusual options activity
- Feature store, ML model validation, or experiment tracking infrastructure

## 4. Integration Path

### Step 1: Expand Signal Generator ✅ Complete (Phase 4)
- New signal functions added to `trading/backtesting/domain/strategy_signals.py`:
  `_policy_regime_signal`, `_news_sentiment_signal`, `_social_trend_rotation_signal`.
- All three are registered in `STRATEGY_REGISTRY` with `strategy_style="alternative"`.
- `resolve_signal()` dispatcher updated with keyword matching for `policy_regime`, `news_sentiment`, `social_trend_rotation`.

### Step 2: Add External Feature Provider Package ✅ Complete (Phase 4)
- `trading/features/` package created with `base.py` (ABC + bundle) and three concrete providers.
- All providers subclass `ExternalFeatureProvider`; caching, TTL, and degradation handled in base class.
- API credentials sourced from env vars only (`NEWS_API_KEY`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`).
- New runtime dependencies in `requirements-base.txt`: `praw`, `pytrends`, `vaderSentiment`, `newsapi-python`.

### Step 3: Create Trends Module Parallel — Not taken
- Decided to isolate external-data providers in `trading/features/` rather than `trends/sentiment.py`.
- This keeps the dependency direction clean: features package is only ever imported by `backtesting/domain/`, never by `trends/`.

### Step 4: Database Schema Updates — Not required for current phase
- Current alternative strategies consume real-time/live provider bundles; no historical sentiment persistence needed yet.
- May be revisited if backtesting over historical sentiment data is added.

### Step 5: Universe and Sector Logic — Not required for current phase
- Alternative strategies operate on individual tickers without topic-to-ticker mapping.
- Sector rotation logic remains in `topic_proxy_rotation` (proxy-based, no external API).

## 5. Implementation Backlog

See project manager items:
- ✅ "React to Policy/Political Changes" — **Implemented** as `policy_regime` strategy via `PolicyFeatureProvider` (TLT/GLD/XLU/UUP vs SPY ETF proxies). FRED/VIX direct integration still not included.
- ✅ "News Sentiment Integration (Phase 2)" — **Implemented** as `news_sentiment` strategy via `NewsFeatureProvider` (RSS feeds + optional NewsAPI). Historical backfill not included.
- ✅ "Search social media for trending topics/companies" — **Implemented** as `social_trend_rotation` strategy via `SocialFeatureProvider` (Reddit praw + Google Trends pytrends).
- "Feature Store and Experiment Tracking" — long-term MLflow/W&B infrastructure. Still planned/not started.

Implementation backlog items are tracked in the project manager under the **Strategies** and **Technical Analysis** boards.
