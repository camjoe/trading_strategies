# Strategies

Use this file to track possible strategy approaches, assumptions, and next experiments.

Status labels in this document:

- Implemented: available in code and used by CLI/backtesting flows.
- Partial: foundations exist, but this item is still broad or not fully formalized as a standalone model.
- Planned: idea-level only, not currently implemented as a first-class strategy.

## Goals
- Status: Partial

- Define strategy hypotheses before coding.
- Compare multiple approaches with clear evaluation metrics.
- Track trade-offs (risk, complexity, data needs, and maintainability).

## Possible Approaches
- Trend following - Implemented
- Mean reversion - Implemented
- Momentum cross-sectional ranking - Partial (proxies/rotation support exists, no dedicated ranked portfolio engine)
- Volatility breakout - Implemented (`breakout`, plus volatility-gated trend variants)
- Pairs/statistical arbitrage - Planned (no PM task yet; add when ready to research)
- Factor-based signals - Partial (proxy feature strategies exist; no broad multi-factor framework yet)
- Regime-aware models - Implemented (`macro_proxy_regime`, `policy_regime`), broader taxonomy still evolving

## Backtest Strategy IDs (Phase 2)

Status: Implemented

Use explicit strategy ids when creating accounts so behavior is predictable and testable.

- trend: close > SMA10 > SMA20 trend stack.
- mean_reversion: SMA20 mean reversion band model.
- rsi: RSI threshold model (14, 30/70 defaults).
- macd: MACD crossover model.
- breakout: Donchian-style breakout/breakdown.
- pullback_trend: buy pullbacks inside an uptrend regime.
- bollinger_mean_reversion: Bollinger-band mean reversion model.
- ma_crossover: fast/slow moving-average crossover.
- volatility_filtered_trend: trend model gated by max annualized volatility.
- topic_proxy_rotation: sector/theme ETF proxy relative-strength rotation layered on top of a simple price trend filter.
- macro_proxy_regime: macro/policy-adjacent proxy filter using SPY vs TLT leadership and VIX pressure.
- policy_regime: ETF-derived policy environment signal (TLT/GLD/XLU/UUP vs SPY). `strategy_style="alternative"`. Requires `PolicyFeatureProvider`.
- news_sentiment: VADER-scored news headline sentiment from RSS feeds + optional NewsAPI. `strategy_style="alternative"`. Requires `NewsFeatureProvider`.
- social_trend_rotation: Google Trends interest score + Reddit mention/sentiment via praw. `strategy_style="alternative"`. Requires `SocialFeatureProvider`.

Compatibility notes:
- Status: Implemented

- Existing labels such as trend_v1, momentum, mean reversion variants, and macd/rsi labels still resolve through a compatibility matcher.
- Unknown strategy labels currently default to the trend model.

## Proxy Feature Strategies (Phase 3)

Status: Implemented

These strategies use date-indexed proxy features rather than direct NLP or news sentiment.

- topic_proxy_rotation
	- Maps tickers to a sector/theme ETF proxy using trends/assets/ticker_categories.txt plus a small ETF mapping table.
	- Uses the proxy ETF's relative strength vs SPY and the proxy trend gap vs its rolling average.
	- Designed as a free-first stand-in for "what themes are trending" without requiring historical headline archives.

- macro_proxy_regime
	- Uses SPY vs TLT lookback returns and VIX pressure vs its own rolling average.
	- Treats strong equity leadership with contained volatility as a risk-on regime proxy.
	- Serves as a politics/macro-adjacent filter without claiming direct event or policy sentiment measurement.

Limitations and assumptions:
- Status: Current constraints (Implemented behavior)

- These are proxy signals, not direct sentiment or topic measurements.
- Topic mappings depend on the category file and a limited sector-to-ETF map; unmapped tickers default to no topic signal.
- Macro features currently use Yahoo Finance symbols only; no FRED, paid macro archive, or curated event calendar is included yet.
- All proxy inputs are still evaluated on daily closes, so intraday event timing and overnight information shocks are not modeled.

## Alternative Strategies (Phase 4)

Status: Implemented

These strategies use real-time external API calls rather than pre-computed proxy data. They are distinguished by `strategy_style="alternative"` in `STRATEGY_REGISTRY`. All external I/O is isolated in the `trading/features/` package; signal functions only consume normalised `ExternalFeatureBundle` values.

- policy_regime
    - ETF price relatives (TLT, GLD, XLU, UUP vs SPY) fetched live via yfinance.
    - Derives `policy_risk_on_score` (0–1 sigmoid) and `policy_defensive_tilt` (signed float).
    - No API key required. Degrades to "hold" when yfinance data is unavailable or insufficient.
    - Provider: `trading/features/policy_feature_provider.PolicyFeatureProvider`

- news_sentiment
    - Primary: RSS feeds from Yahoo Finance and Google News (no API key required).
    - Optional supplementary: NewsAPI via `NEWS_API_KEY` env var.
    - Headlines scored with VADER; emits `news_sentiment_score` ([-1, 1]) and `news_headline_count`.
    - Degrades to "hold" when fewer than 3 headlines are available.
    - Provider: `trading/features/news_feature_provider.NewsFeatureProvider`

- social_trend_rotation
    - Google Trends 30-day interest index via `pytrends` (no key required).
    - Reddit r/stocks, r/investing, r/wallstreetbets post search + VADER scoring via `praw`.
    - Requires `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` env vars; Reddit component degrades to 0 without them.
    - Emits `social_trend_score` ([0, 1]), `social_mention_count`, `social_reddit_sentiment` ([-1, 1]).
    - Provider: `trading/features/social_feature_provider.SocialFeatureProvider`

Key distinctions from Proxy Feature Strategies (Phase 3):
- Proxy strategies (Phase 3) use yfinance price data only — no new external dependencies.
- Alternative strategies (Phase 4) make live calls to external APIs and require `praw`, `pytrends`, `vaderSentiment`, and optionally `newsapi-python` (all in `requirements-base.txt`).
- All alternative strategies follow the degradation contract: `ExternalFeatureProvider.get_features()` never raises; a bundle with `available=False` causes the signal function to return "hold".
- Architecture rules for alternative strategies are codified in `.github/BOT_ARCHITECTURE_CONVENTIONS.md §External Data Strategies`.

## Evaluation Framework
- Status: Planned/Process guidance

- Universe and timeframe
- Signal definition
- Entry/exit rules
- Position sizing
- Transaction cost assumptions
- Slippage assumptions
- Risk limits
- Validation method (walk-forward, out-of-sample)
- Metrics (Sharpe, max drawdown, turnover, hit rate)