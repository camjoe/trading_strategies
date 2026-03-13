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

Create account with descriptive name, return goal range, and learning mode:

```powershell
python trading/paper_trading.py create-account --name momentum_5k --display-name "Momentum Growth Account" --strategy "Momentum" --initial-cash 5000 --goal-min-return-pct 2 --goal-max-return-pct 4 --goal-period monthly --learning-enabled
```

Update account goals/settings later (easy per-account configuration):

```powershell
python trading/paper_trading.py configure-account --account momentum_5k --goal-min-return-pct 5 --goal-max-return-pct 10 --goal-period monthly
python trading/paper_trading.py configure-account --account meanrev_5k --display-name "Mean Reversion Income" --learning-enabled
```

Bulk apply account profiles from one JSON file:

```powershell
python trading/paper_trading.py apply-account-profiles --file trading/account_profiles.json
```

Apply built-in presets:

```powershell
python trading/paper_trading.py apply-account-preset --preset aggressive
python trading/paper_trading.py apply-account-preset --preset conservative
```

Preset files:
- `trading/account_profiles.aggressive.json`
- `trading/account_profiles.conservative.json`

`trading/account_profiles.json` is the recommended single source of truth for account strategy metadata:
- `name`
- `descriptive_name`
- `strategy`
- `initial_cash` (used when creating missing accounts)
- `benchmark_ticker`
- `goal_min_return_pct`
- `goal_max_return_pct`
- `goal_period`
- `learning_enabled`

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

## Daily Auto Trades

Default 12-stock trade universe is in `trading/trade_universe.txt`.

Run 1 to 5 auto-generated trades per account for the day:

```powershell
python trading/auto_trader.py --accounts momentum_5k,meanrev_5k --min-trades 1 --max-trades 5
```

Optional deterministic run (for repeatable simulations):

```powershell
python trading/auto_trader.py --accounts momentum_5k,meanrev_5k --seed 42
```

## Windows Daily Scheduler

Automated runner script:
- `trading/daily_paper_trading.ps1`

What it does each run:
- Executes auto trades for configured accounts (1-5 trades per account by default)
- Saves a snapshot for each account
- Prints strategy comparison
- Writes a timestamped log to `logs/`

Learning mode behavior:
- If `learning_enabled` is on for an account, auto-trader biases buys toward better-performing holdings and biases sells toward weaker holdings.

Registered scheduled task:
- Name: `Trading\DailyPaperTrading`
- Time: daily at `4:10 PM`

Useful commands:

```powershell
# Run once immediately
powershell -NoProfile -ExecutionPolicy Bypass -File .\trading\daily_paper_trading.ps1

# View task details
schtasks /Query /TN "Trading\DailyPaperTrading" /V /FO LIST

# Change schedule time (example: 3:45 PM)
schtasks /Change /TN "Trading\DailyPaperTrading" /ST 15:45
```

## Notes

- Sells are restricted to current holdings (no shorting in this version).
- Buys require enough available cash.
- Latest prices for unrealized PnL are fetched via `yfinance`.
- You can pass custom ISO timestamps with `--time` on trade/snapshot commands.
- Trend classification uses snapshot history plus current equity (`up`, `flat`, `down`, or `insufficient-data`).
