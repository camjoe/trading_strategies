# Docs Index

---

## Section 1: Financial & Market Knowledge

### Financial Terms and Phrases

| Term | Definition |
|---|---|
| **Alpha** | Excess return of a strategy relative to a benchmark. Positive alpha means outperformance. |
| **Beta** | Sensitivity of an asset's returns to market movements. Beta of 1.0 moves in line with the market. |
| **Sharpe Ratio** | Risk-adjusted return: mean excess return divided by its standard deviation. Higher is better. |
| **Max Drawdown** | Largest peak-to-trough decline in portfolio value — a key measure of downside risk. |
| **PnL (Profit and Loss)** | Total realized and unrealized gain or loss on a position or portfolio. |
| **Realized PnL** | Gain or loss locked in by closing a position. |
| **Unrealized PnL** | Gain or loss on a position that is still open (mark-to-market). |
| **Equity Snapshot** | A point-in-time record of total portfolio value used to build a performance time series. |
| **Benchmark** | A reference index (e.g., SPY, QQQ) used to compare strategy performance. |
| **Hit Rate** | Percentage of trades that are profitable. |
| **Turnover** | How frequently positions are replaced; high turnover increases transaction costs. |
| **Slippage** | Difference between the expected execution price and the actual fill price. |
| **IV Rank (Implied Volatility Rank)** | A normalized 0–100 score showing where current implied volatility sits relative to its own 1-year range. `0` = near lowest IV; `100` = near highest IV. Used to gauge whether options are relatively cheap or expensive. |
| **LEAPs** | Long-term Equity Anticipation Securities — options with expirations typically one year or more out. |
| **DTE (Days to Expiration)** | Number of calendar days until an options contract expires. |
| **Delta** | Rate of change in an option's price relative to a $1 move in the underlying asset. Ranges 0–1 for calls and 0 to -1 for puts. |
| **Strike Price** | The price at which an option contract can be exercised. |
| **Premium** | The price paid (or received) for an options contract. |
| **Stop-Loss** | A predefined exit point to limit losses on a trade. |
| **Take-Profit** | A predefined exit point to lock in gains on a trade. |
| **Walk-Forward Validation** | A backtesting methodology where the model is trained on a rolling window and tested on the next unseen period — reducing overfitting. |
| **Look-Ahead Bias** | An error where future data is inadvertently used when generating historical signals. |
| **Survivorship Bias** | Distortion in backtests caused by only including assets that still exist today, ignoring delisted companies. |
| **Adjusted Close** | Historical closing price adjusted for corporate actions (splits, dividends) to maintain a consistent series. |
| **Regime** | A persistent market state (e.g., trending, mean-reverting, high-volatility) that affects strategy performance. |

---

### Technical Analysis Concepts

| Concept | Description |
|---|---|
| **Moving Average (MA)** | Smoothed price series over a rolling window (e.g., 50-day MA). Used to identify trend direction. |
| **EMA (Exponential Moving Average)** | A moving average that applies more weight to recent prices than older ones. |
| **MACD** | Moving Average Convergence Divergence — momentum indicator comparing two EMAs and a signal line. |
| **RSI (Relative Strength Index)** | Momentum oscillator (0–100) measuring the speed and magnitude of recent price changes. Above 70 = overbought; below 30 = oversold. |
| **Bollinger Bands** | Volatility bands placed two standard deviations above and below a moving average. |
| **ATR (Average True Range)** | Measures market volatility; useful for position sizing and stop placement. |
| **Volume** | Number of shares or contracts traded in a period — a key confirmation signal for price moves. |
| **Breakout** | When price moves beyond a defined resistance or support level, often on elevated volume. |
| **Mean Reversion** | The tendency of prices to return to a historical average after deviating from it. |
| **Momentum** | The persistence of price trends — assets that have performed well recently tend to continue doing so over short horizons. |

---

### Trading Strategies

Strategy hypotheses tracked and evaluated in this project:

| Strategy | Description |
|---|---|
| **Trend Following** | Enter positions in the direction of an established price trend; exit when the trend weakens. |
| **Mean Reversion** | Bet that prices will revert to a historical average after an extreme move. |
| **Momentum (Cross-Sectional)** | Rank assets by recent relative performance and go long the top performers. |
| **Volatility Breakout** | Enter positions when price breaks out of a defined volatility range. |
| **Pairs / Statistical Arbitrage** | Exploit temporary divergences in the price spread between historically correlated instruments. |
| **Factor-Based Signals** | Use quantitative factors (value, quality, momentum, low-volatility) to rank and select assets. |
| **Regime-Aware Models** | Adjust strategy behavior based on detected market regime (trending vs. mean-reverting, etc.). |

**Evaluation framework for any strategy:**
- Universe and timeframe
- Signal definition
- Entry/exit rules
- Position sizing
- Transaction cost and slippage assumptions
- Risk limits
- Validation method (walk-forward, out-of-sample)
- Metrics: Sharpe ratio, max drawdown, turnover, hit rate

---

### Areas of Focus

Asset classes under consideration:

| Category | Notes |
|---|---|
| **Equities** | Individual stocks, core focus area. |
| **ETFs** | Sector, factor, and index ETFs — useful for regime/trend strategies. |
| **Options / LEAPs** | Long-dated options used to simulate leveraged equity exposure with defined risk. |
| **Macro** | Macro-level signals (rates, volatility indices) for regime context. |
| **Futures** | Commodity and index futures — not currently active. |
| **Forex** | Currency pairs — not currently active. |
| **Crypto** | Digital assets via feeds like `ccxt` — exploratory. |

---

## Section 2: Software

### Languages

| Language | Usage |
|---|---|
| **Python** | Core language for all trading logic, backtesting, data analysis, and the API backend. |
| **TypeScript** | Frontend UI (`paper_trading_ui/frontend/`) — provides type-safe client-side code. |
| **SQL (SQLite)** | Persistent storage for accounts, trades, equity snapshots, and backtest results. |

---

### Frameworks and Tools

| Tool | Role |
|---|---|
| **FastAPI** | REST API backend for the paper trading UI (`paper_trading_ui/backend/`). |
| **Pydantic** | Data validation and settings management used throughout the FastAPI backend. |
| **Vite** | Frontend build tool and dev server for the TypeScript UI. |
| **Peewee** | Lightweight Python ORM used for SQLite database access. |
| **pytest** | Test framework for all unit and integration tests. |
| **pytest-cov** | Code coverage reporting for the test suite. |

---

### Key Python Packages

#### Data and Market Access
| Package | Description |
|---|---|
| `yfinance` | Primary market data source — daily OHLCV and adjusted close via Yahoo Finance. |
| `yahooquery` | Alternative Yahoo Finance client. |
| `pandas-datareader` | Generic financial data reader (FRED, Stooq, etc.). |
| `requests` / `httpx` | HTTP clients for REST API calls. |
| `ccxt` | Crypto exchange data aggregator. |

#### Analysis and Modeling
| Package | Description |
|---|---|
| `pandas` | Core data manipulation and time-series handling. |
| `numpy` | Numerical computing. |
| `scipy` | Scientific computing and statistical tests. |
| `statsmodels` | Statistical models, OLS regression, time-series analysis. |
| `scikit-learn` | Machine learning — classification, regression, preprocessing. |

#### Technical Indicators
| Package | Description |
|---|---|
| `pandas-ta` | 130+ technical indicators built on pandas DataFrames. |
| `ta` | Lightweight technical analysis library. |

#### Visualization
| Package | Description |
|---|---|
| `matplotlib` | Static charting. |
| `plotly` | Interactive charts. |
| `mplfinance` | OHLCV candlestick and financial chart rendering. |

#### Backtesting and Performance
| Package | Description |
|---|---|
| `quantstats` | Portfolio performance and tearsheet reports. |
| `vectorbt` | Vectorized backtesting framework for fast simulation. |
| `backtrader` | Event-driven backtesting framework. |

#### Deep Learning (Optional)
| Package | Description |
|---|---|
| `torch` | PyTorch — deep learning for sequence models and custom architectures. |

---

### Projects in This Repository

#### `trading/`
Core trading engine. Handles paper trading accounts, trade recording, position management, accounting, automated trading, reporting, and backtesting.

Key modules:
- `paper_trading.py` — account lifecycle, mock trade execution, equity snapshots, benchmarking
- `auto_trader.py` — generates and executes automatic daily trades
- `accounting.py` — trade ledger and PnL calculations
- `backtesting/` — backtest runner, walk-forward engine, and strategy signal generation
- `reporting.py` — account stats and strategy comparison reports
- `models.py` — data models shared across the trading module
- `db.py` — database initialization and helpers
- `profiles.py` — account profile management

Account presets live in `trading/account_profiles/`.

---

#### `trends/`
Stock trend analysis module. Fetches price data, computes technical indicators, and generates trend signals for a configurable ticker universe.

Key modules:
- `data.py` — price history fetching and caching
- `indicators.py` — technical indicator computation
- `stock_trends.py` — combines data and indicators into trend summaries
- `tickers.py` — ticker list management
- `charts.py` — trend visualization helpers

---

#### `paper_trading_ui/`
Web interface for monitoring paper trading accounts and triggering backtests.

- **Backend** (`backend/`) — FastAPI REST API serving account stats, trade data, and backtest controls. Reads from the same SQLite database as the trading module.
- **Frontend** (`frontend/`) — TypeScript + Vite single-page app. No external UI framework — plain TypeScript with a modular feature/template structure.

Launch the UI:
```bash
python paper_trading_ui/scripts/launch_ui.py
```

---

#### `common/`
Shared utilities used across multiple modules.

- `tickers.py` — common ticker loading helpers
- `time.py` — date/time utilities

---

### Documentation

#### Core Docs
- `Area of Focus.md`: Current and future research categories.
- `Strategies.md`: Strategy ideas, assumptions, and validation checklist.
- `Paper Trading.md`: Account setup, commands, and operational notes.
- `Paper Trading Scheduler.md`: Windows scheduling workflow for daily paper trading.
- `Tooling and Packages.md`: Package/tool reference for analysis workflows.
- `TODO.md`: Active backlog.

#### Backtesting Docs
- `backtesting/README.md`: Backtesting commands, safeguards, and walk-forward usage.
- `backtesting/Tooling.md`: Backtesting-specific package notes.

#### Suggested Reading Order
1. `Strategies.md`
2. `Paper Trading.md`
3. `backtesting/README.md`
4. `TODO.md`
