# Strategies

Use this file to track possible strategy approaches, assumptions, and next experiments.

## Goals
- Define strategy hypotheses before coding.
- Compare multiple approaches with clear evaluation metrics.
- Track trade-offs (risk, complexity, data needs, and maintainability).

## Possible Approaches
- Trend following
- Mean reversion
- Momentum cross-sectional ranking
- Volatility breakout
- Pairs/statistical arbitrage
- Factor-based signals
- Regime-aware models

## Backtest Strategy IDs (Phase 2)

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

Compatibility notes:
- Existing labels such as trend_v1, momentum, mean reversion variants, and macd/rsi labels still resolve through a compatibility matcher.
- Unknown strategy labels currently default to the trend model.

## Evaluation Framework
- Universe and timeframe
- Signal definition
- Entry/exit rules
- Position sizing
- Transaction cost assumptions
- Slippage assumptions
- Risk limits
- Validation method (walk-forward, out-of-sample)
- Metrics (Sharpe, max drawdown, turnover, hit rate)