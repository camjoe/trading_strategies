# Paper Trading

`trading/paper_trading.py` creates strategy-specific paper accounts, records mock trades, and stores equity snapshots over time.

## What It Tracks

- Separate accounts by strategy
- Cash balance and open positions
- Realized and unrealized PnL
- Historical equity snapshots
- Per-strategy benchmark comparison (e.g., SPY)

Data is stored in: `trading/database/paper_trading.db`

## Quick Start

Initialize database:

```powershell
python trading/paper_trading.py init
```

Create two strategy accounts:

```powershell
python trading/paper_trading.py create-account --name trend_v1 --strategy "Trend Following" --initial-cash 100000
python trading/paper_trading.py create-account --name meanrev_v1 --strategy "Mean Reversion" --initial-cash 100000
```

Create account with explicit benchmark:

```powershell
python trading/paper_trading.py create-account --name crypto_momo_v1 --strategy "Crypto Momentum" --initial-cash 50000 --benchmark BTC-USD
```

Update benchmark on an existing account:

```powershell
python trading/paper_trading.py set-benchmark --account trend_v1 --benchmark QQQ
```

Record mock trades:

```powershell
python trading/paper_trading.py trade --account trend_v1 --side buy --ticker NVDA --qty 10 --price 185.20 --fee 1.00 --note "breakout"
python trading/paper_trading.py trade --account trend_v1 --side sell --ticker NVDA --qty 5 --price 191.80 --fee 1.00 --note "partial take profit"
```

View account report:

```powershell
python trading/paper_trading.py report --account trend_v1
```

Save a snapshot (for time-series tracking):

```powershell
python trading/paper_trading.py snapshot --account trend_v1
```

See snapshot history:

```powershell
python trading/paper_trading.py snapshot-history --account trend_v1 --limit 20
```

Compare all strategies (labels, positions, benchmark, alpha, trend):

```powershell
python trading/paper_trading.py compare-strategies --lookback 10
```

## Notes

- Sells are restricted to current holdings (no shorting in this version).
- Buys require enough available cash.
- Latest prices for unrealized PnL are fetched via `yfinance`.
- You can pass custom ISO timestamps with `--time` on trade/snapshot commands.
- Trend classification uses snapshot history plus current equity (`up`, `flat`, `down`, or `insufficient-data`).
