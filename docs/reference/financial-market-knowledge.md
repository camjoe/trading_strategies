# Financial and Market Knowledge

Type: notes
Status: Active
Created: 2026-06-30
Last Reviewed: 2026-07-13
Purpose: Canonical glossary source for financial, market, and strategy terms shown in the documentation UI.
Related: [Strategies](strategies.md), [Backtesting](backtesting.md), [Docs Index](../README.md)

## Purpose

This document is the source of truth for the financial and market knowledge glossary used by the paper trading documentation UI. Edit term names, groups, definitions, display labels, and visibility here, then run the documentation UI sync to regenerate the frontend asset.

## Usage

Run these commands from the repository root:

```sh
python -m scripts.documentation_ui.sync
python -m scripts.documentation_ui.check
```

The `Use` column controls where a term appears:

| Value | Meaning |
|---|---|
| `both` | Show in the UI and keep as glossary knowledge |
| `glossary` | Keep in the docs source but hide from the current UI card |
| `ui` | Show in the UI as product/context guidance |

The optional `UI Label` column overrides the displayed label in the UI while preserving the canonical `Term` value.

## Performance and Risk

| Term | Use | Definition | UI Label |
|---|---|---|---|
| Alpha | both | Excess return of a strategy relative to a benchmark. Positive alpha means outperformance. |  |
| Benchmark | both | A reference index (e.g., SPY, QQQ) used to compare strategy performance. |  |
| Equity Snapshot | both | A point-in-time record of total portfolio value used to build a performance time series. |  |
| PnL (Profit and Loss) | both | Total realized and unrealized gain or loss on a position or portfolio. |  |
| Realized PnL | both | Gain or loss locked in by closing a position. |  |
| Unrealized PnL | both | Gain or loss on a position still open (mark-to-market). |  |
| Beta | glossary | Sensitivity of an asset's returns to market movements. Beta of 1.0 moves in line with the market. |  |
| Hit Rate | glossary | Percentage of trades that are profitable. |  |
| Win Rate | both | Percentage of trades that finish profitable. In the UI this is the same idea as hit rate, surfaced from persisted backtest metrics. |  |
| Max Drawdown | both | Largest peak-to-trough decline in portfolio value. |  |
| Sharpe Ratio | both | Risk-adjusted return: mean excess return divided by standard deviation. Higher is better. |  |
| Sortino Ratio | both | Risk-adjusted return similar to Sharpe, but only penalizes downside volatility. Higher is better when you care more about harmful swings than upside variation. |  |
| Calmar Ratio | both | Return relative to maximum drawdown. Useful for judging whether returns were earned efficiently compared with the worst peak-to-trough decline. |  |
| Profit Factor | both | Gross profits divided by gross losses across trades. Above 1.0 means profits exceeded losses overall. |  |
| Average Trade Return | both | Average percentage return per trade across the measured run. Useful as a rough quality check alongside drawdown and win rate. |  |
| Turnover | glossary | How frequently positions are replaced; high turnover can increase transaction costs. |  |

## Execution and Risk Controls

| Term | Use | Definition | UI Label |
|---|---|---|---|
| Stop-Loss | both | A predefined exit point to limit losses on a trade. |  |
| Take-Profit | both | A predefined exit point to lock in gains on a trade. |  |
| Slippage | both | Difference between the expected execution price and the actual fill price. |  |

## Options and Volatility

| Term | Use | Definition | UI Label |
|---|---|---|---|
| Delta | both | Rate of change in an option's price relative to a $1 move in the underlying asset. Ranges 0-1 for calls, 0 to -1 for puts. |  |
| DTE | both | Number of calendar days until an options contract expires. | DTE (Days to Expiration) |
| IV Rank | both | Normalized 0-100 score for current implied volatility vs. its 1-year range. 0 = near lowest; 100 = near highest. Used to gauge whether options are relatively cheap or expensive. |  |
| LEAPs | both | Long-term Equity Anticipation Securities - options with expirations typically one year or more out. |  |
| Premium | both | The price paid (or received) for an options contract. |  |
| Strike Price | both | The price at which an option contract can be exercised. |  |

## Data and Backtesting Integrity

| Term | Use | Definition | UI Label |
|---|---|---|---|
| Adjusted Close | both | Historical closing price adjusted for corporate actions (splits, dividends) to maintain a consistent series. |  |
| Walk-Forward Validation | both | Backtesting methodology where the model is trained on a rolling window and tested on the next unseen period, reducing overfitting. |  |
| Look-Ahead Bias | glossary | Error where future data leaks into historical signal generation. |  |
| Regime | glossary | Persistent market state (for example trending, mean-reverting, high-volatility). |  |
| Survivorship Bias | glossary | Distortion from only including assets that still exist today. |  |

## Technical Analysis

| Term | Use | Definition | UI Label |
|---|---|---|---|
| EMA | both | Exponential Moving Average - applies more weight to recent prices than older ones. |  |
| MACD | both | Moving Average Convergence Divergence - momentum indicator comparing two EMAs and a signal line. |  |
| Mean Reversion | both | Bet that prices will revert to a historical average after an extreme move. |  |
| Momentum | both | The persistence of price trends - assets that have performed well recently tend to continue doing so over short horizons. |  |
| Moving Average (MA) | both | Smoothed price series over a rolling window (e.g., 50-day MA). Used to identify trend direction. |  |
| RSI | both | Relative Strength Index (0-100) measuring speed and magnitude of recent price changes. Above 70 = overbought; below 30 = oversold. |  |
| Volume | both | Number of shares or contracts traded in a period - a key confirmation signal for price moves. |  |
| ATR | glossary | Average True Range, a volatility measure often used for position sizing and stops. |  |
| Bollinger Bands | glossary | Volatility bands around a moving average. |  |
| Breakout | glossary | Price move beyond support or resistance, often on elevated volume. |  |

## Trading Strategies

| Term | Use | Definition | UI Label |
|---|---|---|---|
| Regime-Aware Models | ui | Adjust strategy behavior based on detected market regime (trending vs. mean-reverting, etc.). |  |
| Trend Following | ui | Enter positions in the direction of an established price trend; exit when the trend weakens. |  |
| Volatility Breakout | ui | Enter positions when price breaks out of a defined volatility range. |  |

## Asset Classes

| Term | Use | Definition | UI Label |
|---|---|---|---|
| Equities | both | Individual stocks - core focus area. |  |
| ETFs | both | Sector, factor, and index ETFs - useful for regime and trend strategies. |  |
| Macro | both | Macro-level signals (rates, volatility indices) for regime context. |  |
| Options / LEAPs | both | Long-dated options used to simulate leveraged equity exposure with defined risk. |  |

## Boundaries

- Keep terminology concise and project-oriented rather than encyclopedic.
- Add terms here before relying on them in UI copy or operator docs.
- Do not edit `apps/paper_trading_web/frontend/src/assets/finance.json` directly; regenerate it with `scripts.documentation_ui.sync`.
