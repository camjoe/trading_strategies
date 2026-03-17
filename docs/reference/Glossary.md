# Glossary

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
| Unrealized PnL | Gain or loss on a position that is still open (mark-to-market). |
| Equity Snapshot | Point-in-time record of total portfolio value used to build a performance series. |
| Benchmark | Reference index used to compare strategy performance (for example SPY, QQQ). |
| Hit Rate | Percentage of trades that are profitable. |
| Turnover | How frequently positions are replaced; high turnover can increase transaction costs. |
| Slippage | Difference between expected execution price and actual fill price. |

## Options and Volatility

| Term | Definition |
|---|---|
| IV Rank | Normalized 0-100 score showing where current implied volatility sits versus its own 1-year range. |
| LEAPs | Long-term Equity Anticipation Securities, usually options with expirations one year or more out. |
| DTE | Days to expiration of an options contract. |
| Delta | Estimated option price sensitivity to a $1 move in the underlying. |
| Strike Price | Price at which an option can be exercised. |
| Premium | Price paid (or received) for an options contract. |
| Stop-Loss | Predefined exit point to limit losses. |
| Take-Profit | Predefined exit point to lock in gains. |

## Backtesting and Validation

| Term | Definition |
|---|---|
| Walk-Forward Validation | Rolling evaluation where each test window is evaluated after prior data only. |
| Look-Ahead Bias | Error where future data leaks into historical signal generation. |
| Survivorship Bias | Distortion from only including assets that still exist today. |
| Adjusted Close | Close price adjusted for corporate actions like splits and dividends. |
| Regime | Persistent market state (for example trending, mean-reverting, high-volatility). |

## Technical Analysis

| Concept | Description |
|---|---|
| Moving Average (MA) | Smoothed price series over a rolling window. |
| EMA | Moving average with heavier weighting on recent prices. |
| MACD | Momentum indicator using spread between EMAs and a signal line. |
| RSI | Momentum oscillator from 0 to 100 measuring recent move strength. |
| Bollinger Bands | Volatility bands around a moving average. |
| ATR | Average True Range, a volatility measure often used for position sizing and stops. |
| Volume | Number of shares or contracts traded in a period. |
| Breakout | Price move beyond support or resistance, often on elevated volume. |
| Mean Reversion | Tendency of prices to revert toward a historical average. |
| Momentum | Persistence of price trends over a recent window. |
