# Strategy Catalog Reference

Type: notes
Status: Active
Created: 2026-03-11
Last Reviewed: 2026-04-25
Purpose: Catalog of strategy signal families, compatibility behavior, and evaluation workflow.
Related: [Backtesting](notes-backtesting.md), [Sentiment Signals](notes-sentiment-signals.md), [Trading Package Map](../maps/trading-package-map.md)

## Purpose

Provide the current strategy catalog, compatibility behavior, and evaluation
checklist for research/backtesting flows.

## Canonical Source

Canonical strategy registration lives in:

- `trading/backtesting/domain/strategy_signals.py` (`STRATEGY_REGISTRY`)

## Strategy Families

### Trend family

- `trend`
- `macd`
- `breakout`
- `pullback_trend`
- `ma_crossover`
- `volatility_filtered_trend`

### Mean-reversion family

- `mean_reversion`
- `rsi`
- `bollinger_mean_reversion`

### Proxy-feature family (price-derived features)

- `topic_proxy_rotation`
- `macro_proxy_regime`

### Alternative-data family (external providers)

- `policy_regime`
- `news_sentiment`
- `social_trend_rotation`

## Strategy Resolution Behavior

Resolution is handled by `resolve_strategy(...)` in
`trading/backtesting/domain/strategy_signals.py`.

Order of resolution:

1. exact strategy id
2. registered aliases
3. keyword compatibility matching

Unknown labels raise `ValueError` (they do not silently fall back).

Examples of compatibility labels that still resolve:

- trend/momentum variants -> `trend`
- mean-reversion variants -> `mean_reversion`
- `topic_rotation` / `theme_proxy` -> `topic_proxy_rotation`
- `policy_etf` / `political_regime` -> `policy_regime`

## Data and Dependency Notes

Price-based and proxy-feature strategies:

- depend on configured market-data provider (default `yfinance`)
- run on daily-bar assumptions in current backtesting/runtime flows

Alternative-data strategies:

- depend on `trading/features/` providers
- use `ExternalFeatureBundle` inputs and degrade conservatively when data is unavailable
- runtime deps in `requirements-base.txt` include:
  - `praw`
  - `pytrends`
  - `vaderSentiment`
  - optional `newsapi-python`

Credential notes (alternative-data paths):

- `NEWS_API_KEY` (optional for NewsAPI supplementation)
- `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` (required for Reddit component)

## Evaluation Checklist

Use this checklist when proposing new strategies:

- strategy hypothesis and intended market regime
- required data sources and fallback behavior
- entry/exit rules and position sizing
- transaction-cost and slippage assumptions
- risk limits and failure modes
- validation plan (walk-forward/out-of-sample)
- comparable baseline(s)
- reporting metrics (return, drawdown, turnover, hit rate, etc.)

## Research Candidates (Not Implemented as First-Class Strategies)

- pairs/statistical arbitrage
- broader multi-factor framework
- richer cross-sectional momentum ranking engine

## Related References

- `docs/reference/notes-backtesting.md`
- `docs/reference/notes-sentiment-signals.md`
- `trading/backtesting/README.md`
