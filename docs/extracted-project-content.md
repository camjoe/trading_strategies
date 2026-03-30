# Extracted Project Content

Content extracted from `docs.html` that can be derived from project information, code, or existing documentation.

## Finance: Trading Strategies

Source: Could be expanded from `docs/Strategies.md` or derived from trading module analysis.

| Strategy | Description |
|---|---|
| Trend Following | Enter positions in the direction of an established price trend; exit when the trend weakens. |
| Momentum (Cross-Sectional) | Rank assets by recent relative performance and go long the top performers. |
| Volatility Breakout | Enter positions when price breaks out of a defined volatility range. |
| Pairs / Statistical Arbitrage | Exploit temporary divergences in the price spread between historically correlated instruments. |
| Factor-Based Signals | Use quantitative factors (value, quality, momentum, low-volatility) to rank and select assets. |
| Regime-Aware Models | Adjust strategy behavior based on detected market regime (trending vs. mean-reverting, etc.). |

### Evaluation Framework

Criteria used to validate a trading strategy:

- Universe and timeframe
- Signal definition
- Entry / exit rules
- Position sizing
- Transaction cost and slippage assumptions
- Risk limits
- Validation method (walk-forward, out-of-sample)
- Metrics: Sharpe ratio, max drawdown, turnover, hit rate