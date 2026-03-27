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
- Pairs/statistical arbitrage - Planned
- Factor-based signals - Partial (proxy feature strategies exist; no broad multi-factor framework yet)
- Regime-aware models - Implemented (`macro_proxy_regime`), broader taxonomy still evolving

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