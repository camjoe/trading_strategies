# Trading Module

Core paper trading and backtesting engine for the repository.

## Quick Links

- [Scope](#scope)
- [Main commands](#main-commands)
- [Auto-trading](#auto-trading)
- [Daily scheduler (Windows)](#daily-scheduler-windows)
- [Notes](#notes)
- [Related docs](#related-docs)

## Scope

The `trading/` module handles:

- Account lifecycle (create, configure, benchmark, profiles)
- Trade simulation and position tracking
- Snapshot history and reporting
- Auto-trading simulation runs
- Backtesting and walk-forward analysis support

Data is stored in `trading/database/paper_trading.db`.

## Main Commands

### Initialize

```powershell
python trading/paper_trading.py init
```

### Create Accounts

```powershell
python trading/paper_trading.py create-account --name trend_v1 --strategy "Trend Following" --initial-cash 100000
python trading/paper_trading.py create-account --name meanrev_v1 --strategy "Mean Reversion" --initial-cash 100000
```

With benchmark and configuration:

```powershell
python trading/paper_trading.py create-account --name crypto_momo_v1 --strategy "Crypto Momentum" --initial-cash 50000 --benchmark BTC-USD
```

With display name, return goals, learning mode, and benchmark:

```powershell
python trading/paper_trading.py create-account --name momentum_5k --display-name "Momentum Growth Account" --strategy "Momentum" --initial-cash 5000 --goal-min-return-pct 2 --goal-max-return-pct 4 --goal-period monthly --learning-enabled
```

### Configure Accounts

```powershell
python trading/paper_trading.py configure-account --account momentum_5k --goal-min-return-pct 5 --goal-max-return-pct 10 --goal-period monthly
python trading/paper_trading.py configure-account --account meanrev_5k --display-name "Mean Reversion Income" --learning-enabled
```

Set benchmark:

```powershell
python trading/paper_trading.py set-benchmark --account trend_v1 --benchmark QQQ
```

### Apply Account Profiles

Apply profile file:

```powershell
python trading/paper_trading.py apply-account-profiles --file trading/account_profiles/default.json
```

Apply built-in preset:

```powershell
python trading/paper_trading.py apply-account-preset --preset aggressive
python trading/paper_trading.py apply-account-preset --preset conservative
```

Preset files:

- `trading/account_profiles/default.json` (recommended source of truth)
- `trading/account_profiles/aggressive.json`
- `trading/account_profiles/conservative.json`

### Record and Review Trading Activity

Record mock trades:

```powershell
python trading/paper_trading.py trade --account trend_v1 --side buy --ticker NVDA --qty 10 --price 185.20 --fee 1.00 --note "breakout"
python trading/paper_trading.py trade --account trend_v1 --side sell --ticker NVDA --qty 5 --price 191.80 --fee 1.00 --note "partial take profit"
```

View report:

```powershell
python trading/paper_trading.py report --account trend_v1
```

Save and inspect snapshots:

```powershell
python trading/paper_trading.py snapshot --account trend_v1
python trading/paper_trading.py snapshot-history --account trend_v1 --limit 20
```

Compare strategies:

```powershell
python trading/paper_trading.py compare-strategies --lookback 10
```

## Auto-Trading

Default trade universe file: `trading/trade_universe.txt`.

Run generated daily trades:

```powershell
python trading/auto_trader.py --accounts momentum_5k,meanrev_5k --min-trades 1 --max-trades 5
```

Deterministic simulation run:

```powershell
python trading/auto_trader.py --accounts momentum_5k,meanrev_5k --seed 42
```

## Daily Scheduler (Windows)

Scheduler script: `trading/scripts/daily_paper_trading.ps1`

Behavior:

- Runs auto-trader for configured accounts
- Saves snapshots
- Prints strategy comparison
- Writes logs to `local/logs/`
- Stores run metadata including `RunSource`
- Skips duplicate successful same-day runs unless `-ForceRun`

Manual runs:

```powershell
# Normal run
powershell -NoProfile -ExecutionPolicy Bypass -File .\trading\scripts\daily_paper_trading.ps1 -RunSource manual

# Force extra same-day run
powershell -NoProfile -ExecutionPolicy Bypass -File .\trading\scripts\daily_paper_trading.ps1 -RunSource manual -ForceRun
```

Task Scheduler recommendation:

- `Trading\DailyPaperTrading` (daily)
- `Trading\DailyPaperTradingFallback` (startup fallback)

Create startup fallback task:

```powershell
$scriptPath = Join-Path (Get-Location) "trading\scripts\daily_paper_trading.ps1"
$action = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
schtasks /Create /TN "Trading\DailyPaperTradingFallback" /SC ONSTART /DELAY 0000:10 /TR $action /F
```

Query tasks:

```powershell
schtasks /Query /TN "Trading\DailyPaperTrading" /V /FO LIST
schtasks /Query /TN "Trading\DailyPaperTradingFallback" /V /FO LIST
```

Change daily time:

```powershell
schtasks /Change /TN "Trading\DailyPaperTrading" /ST 15:45
```

Delete fallback task:

```powershell
schtasks /Delete /TN "Trading\DailyPaperTradingFallback" /F
```

Startup-folder fallback option:

```powershell
$startupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$repoRoot = Get-Location
$cmdPath = Join-Path $startupDir "daily_paper_trading_fallback.cmd"
$content = "@echo off`r`ncd /d `"$repoRoot`"`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File .\trading\scripts\daily_paper_trading.ps1 -RunSource startup-fallback`r`n"
Set-Content -Path $cmdPath -Value $content -Encoding ASCII
```

## Notes

- Sells are restricted to current holdings (no shorting in this version).
- Buys require enough available cash.
- Latest prices for unrealized PnL are fetched via `yfinance`.
- You can pass custom ISO timestamps with `--time` on trade and snapshot commands.
- Trend classification uses snapshot history plus current equity (`up`, `flat`, `down`, or `insufficient-data`).

## Related Docs

- Backtesting: `docs/backtesting/README.md`
- UI dashboard: `paper_trading_ui/README.md`
