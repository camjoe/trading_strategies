# Sentiment/Topic Signal Integration Notes

Status: Active reference — implementation backlog tracked in project manager (Strategies / Technical Analysis boards)
Date: 2026-03-27

Purpose: save the current-state map and integration path for sentiment, topic, and politics-driven trading strategies so future sessions and bots have the context to continue without re-auditing the codebase.

## 1. Current Signal Architecture

**Signal dispatch:**
- `trading/backtesting/domain/strategy_signals.py` — `resolve_signal()` dispatches 4 signal types: trend (SMA-based), mean_reversion, RSI, MACD. Strategy names are matched by substring.
- `trading/backtesting/backtest.py` — calls signal resolver in the main simulation loop.
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

**What is NOT available:**
- No momentum ranking across multiple securities
- No volatility or correlation features
- No intraday microstructure
- Portfolio trend inferred only from equity snapshots in `trading/reporting.py` via `infer_overall_trend`

## 3. Missing Pieces for Sentiment/Topic/Politics Strategies

No implementation exists for:
- News/headline sentiment (no NewsAPI, GDELT, etc.)
- Social media sentiment (no Twitter/Reddit APIs)
- Macro/political event calendars
- Trending topics or sector momentum
- Search trends (Google Trends, etc.)
- Earnings/event drivers
- Insider transactions
- Unusual options activity

Alternative data sources are listed in docs as unevaluated candidates:
- `alpha_vantage` (not integrated)
- `tiingo` (not integrated)
- `polygon-api-client` (not integrated)

No feature store, ML model validation, or experiment tracking infrastructure yet.

## 4. Integration Path

### Step 1: Expand Signal Generator (low friction)
- Add new signal types to `trading/backtesting/domain/strategy_signals.py`.
- Pattern: `def _sentiment_signal(history: pd.Series) -> str:` returning "buy", "sell", or "hold".
- Register matching on strategy_name in `resolve_signal()` dispatcher.

### Step 2: Add Sentiment Data Provider (moderate friction)
- Create a new provider interface — either extend `common/market_data.py` or add `common/sentiment_data.py`.
- Interface needs: sentiment score + aggregate across tickers.
- For backtesting: requires historical sentiment data.
  - Option A: pre-compute and cache sentiment snapshots like price history.
  - Option B: third-party API with backfill (alpha_vantage, tiingo, GDELT).
  - Option C: mock/synthetic sentiment data for initial research phase.

### Step 3: Create Trends Module Parallel (cleanest pattern)
- Create `trends/sentiment.py` parallel to `trends/indicators.py`.
- Functions: `fetch_sentiment_data()`, `add_sentiment_features(df)`, `sentiment_signal_score()`.
- Optionally add `trends/sentiment_cli.py` following the existing CLI pattern.

### Step 4: Database Schema Updates (if persisting signals)
- `trading/backtesting/repositories/` currently stores only price/qty/fee in backtest_trades.
- May need: new columns for signal metadata or a separate signal_history table.
- Schema in `trading/database/db.py`.

### Step 5: Universe and Sector Logic (for topic-driven strategies)
- Currently: static ticker file OR monthly reconstitution from snapshots.
- Topics/themes could extend this with a category → ticker mapping by trending topic.
- Leverage `trading/config/trade_universe.txt` and `trends/` patterns.

## 5. Implementation Backlog

See project manager items:
- "React to Policy/Political Changes" — MVP politics-driven sentinel signal using FRED/VIX proxies.
- "News Sentiment Integration (Phase 2)" — newsapi.org or alpha_vantage daily sentiment aggregates.
- "Search social media for trending topics/companies" — Phase 3, Stocktwits/Reddit ticker mentions.
- "Feature Store and Experiment Tracking" — long-term MLflow/W&B infrastructure.

Implementation backlog items are tracked in the project manager under the **Strategies** and **Technical Analysis** boards.
