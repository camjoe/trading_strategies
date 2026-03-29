# Finance

Reference terms used across paper trading and backtesting workflows.

## Performance and Risk

| Term | Definition |
|---|---|
| Alpha | Excess return of a strategy relative to a benchmark. Positive alpha means outperformance. |
| Beta | Sensitivity of an asset's returns to market movements. Beta of 1.0 moves in line with the market. |
| Sharpe Ratio | Risk-adjusted return: mean excess return divided by standard deviation. Higher is better. |
| Max Drawdown | Largest peak-to-trough decline in portfolio value. |
| PnL (Profit and Loss) | Total realized and unrealized gain or loss on a position or portfolio. |
| Realized PnL | Gain or loss locked in by closing a position. |
| Unrealized PnL | Gain or loss on a position still open (mark-to-market). |
| Equity Snapshot | A point-in-time record of total portfolio value used to build a performance time series. |
| Benchmark | A reference index (e.g., SPY, QQQ) used to compare strategy performance. |
| Hit Rate | Percentage of trades that are profitable. |
| Turnover | How frequently positions are replaced; high turnover can increase transaction costs. |
| Slippage | Difference between the expected execution price and the actual fill price. |

## Options and Volatility

| Term | Definition |
|---|---|
| IV Rank | Normalized 0–100 score for current implied volatility vs. its 1-year range. 0 = near lowest; 100 = near highest. Used to gauge whether options are relatively cheap or expensive. |
| LEAPs | Long-term Equity Anticipation Securities — options with expirations typically one year or more out. |
| DTE | Number of calendar days until an options contract expires. |
| Delta | Rate of change in an option's price relative to a $1 move in the underlying asset. Ranges 0–1 for calls, 0 to -1 for puts. |
| Strike Price | The price at which an option contract can be exercised. |
| Premium | The price paid (or received) for an options contract. |
| Stop-Loss | A predefined exit point to limit losses on a trade. |
| Take-Profit | A predefined exit point to lock in gains on a trade. |

## Backtesting and Validation

| Term | Definition |
|---|---|
| Walk-Forward Validation | Backtesting methodology where the model is trained on a rolling window and tested on the next unseen period, reducing overfitting. |
| Look-Ahead Bias | Error where future data leaks into historical signal generation. |
| Survivorship Bias | Distortion from only including assets that still exist today. |
| Adjusted Close | Historical closing price adjusted for corporate actions (splits, dividends) to maintain a consistent series. |
| Regime | Persistent market state (for example trending, mean-reverting, high-volatility). |

## Technical Analysis

| Concept | Description |
|---|---|
| Moving Average (MA) | Smoothed price series over a rolling window (e.g., 50-day MA). Used to identify trend direction. |
| EMA | Exponential Moving Average — applies more weight to recent prices than older ones. |
| MACD | Moving Average Convergence Divergence — momentum indicator comparing two EMAs and a signal line. |
| RSI | Relative Strength Index (0–100) measuring speed and magnitude of recent price changes. Above 70 = overbought; below 30 = oversold. |
| Bollinger Bands | Volatility bands around a moving average. |
| ATR | Average True Range, a volatility measure often used for position sizing and stops. |
| Volume | Number of shares or contracts traded in a period — a key confirmation signal for price moves. |
| Breakout | Price move beyond support or resistance, often on elevated volume. |
| Mean Reversion | Bet that prices will revert to a historical average after an extreme move. |
| Momentum | The persistence of price trends — assets that have performed well recently tend to continue doing so over short horizons. |
