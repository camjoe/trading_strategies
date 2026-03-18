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
python -m trading.paper_trading init
```

### Create Accounts

```powershell
python -m trading.paper_trading create-account --name trend_v1 --strategy "Trend Following" --initial-cash 100000
python -m trading.paper_trading create-account --name meanrev_v1 --strategy "Mean Reversion" --initial-cash 100000
```

With benchmark and configuration:

```powershell
python -m trading.paper_trading create-account --name crypto_momo_v1 --strategy "Crypto Momentum" --initial-cash 50000 --benchmark BTC-USD
```

With display name, return goals, learning mode, and benchmark:

```powershell
python -m trading.paper_trading create-account --name momentum_5k --display-name "Momentum Growth Account" --strategy "Momentum" --initial-cash 5000 --goal-min-return-pct 2 --goal-max-return-pct 4 --goal-period monthly --learning-enabled
```

### Configure Accounts

```powershell
python -m trading.paper_trading configure-account --account momentum_5k --goal-min-return-pct 5 --goal-max-return-pct 10 --goal-period monthly
python -m trading.paper_trading configure-account --account meanrev_5k --display-name "Mean Reversion Income" --learning-enabled
```

Set benchmark:

```powershell
python -m trading.paper_trading set-benchmark --account trend_v1 --benchmark QQQ
```

### Apply Account Profiles

Apply profile file:

```powershell
python -m trading.paper_trading apply-account-profiles --file trading/account_profiles/default.json
```

Apply built-in preset:

```powershell
python -m trading.paper_trading apply-account-preset --preset aggressive
python -m trading.paper_trading apply-account-preset --preset conservative
```

Rotation fields supported in account profile JSON:

- `rotation_enabled` (bool)
- `rotation_interval_days` (int)
- `rotation_schedule` (array of strategy ids)
- `rotation_mode` (`time` or `optimal`, optional; default `time`)
- `rotation_optimality_mode` (`previous_period_best` or `average_return`, optional; default `previous_period_best`)
- `rotation_lookback_days` (int, optional; default `180`)
- `rotation_active_index` (int, optional)
- `rotation_last_at` (ISO datetime, optional)
- `rotation_active_strategy` (string, optional)

Notes:

- If `rotation_schedule` is provided and `rotation_active_strategy` is omitted, the active strategy is derived from `rotation_active_index` (or index 0).
- `rotation_mode=time` rotates through the schedule in order when due.
- `rotation_mode=optimal` picks a strategy from the schedule using historical backtest performance over `rotation_lookback_days`.
- Auto-trader persists the chosen active strategy and updates rotation state when due.

Preset files:

- `trading/account_profiles/default.json` (recommended source of truth)
- `trading/account_profiles/aggressive.json`
- `trading/account_profiles/conservative.json`

### Record and Review Trading Activity

Record mock trades:

```powershell
python -m trading.paper_trading trade --account trend_v1 --side buy --ticker NVDA --qty 10 --price 185.20 --fee 1.00 --note "breakout"
python -m trading.paper_trading trade --account trend_v1 --side sell --ticker NVDA --qty 5 --price 191.80 --fee 1.00 --note "partial take profit"
```

View report:

```powershell
python -m trading.paper_trading report --account trend_v1
```

Save and inspect snapshots:

```powershell
python -m trading.paper_trading snapshot --account trend_v1
python -m trading.paper_trading snapshot-history --account trend_v1 --limit 20
```

Compare strategies:

```powershell
python -m trading.paper_trading compare-strategies --lookback 10
```

Backtest comparison commands:

```powershell
python -m trading.paper_trading backtest --account trend_v1 --lookback-months 12
python -m trading.paper_trading backtest-report --run-id 1
python -m trading.paper_trading backtest-leaderboard --limit 10
python -m trading.paper_trading backtest-batch --accounts trend_v1,meanrev_v1 --lookback-months 12 --run-name-prefix exp01
python -m trading.paper_trading backtest-walk-forward --account trend_v1 --start 2025-01-01 --end 2025-12-31 --test-months 1 --step-months 1
```

## Auto-Trading

Default trade universe file: `trading/trade_universe.txt`.

Run generated daily trades:

```powershell
python -m trading.auto_trader --accounts momentum_5k,meanrev_5k --min-trades 1 --max-trades 5
```

Deterministic simulation run:

```powershell
python -m trading.auto_trader --accounts momentum_5k,meanrev_5k --seed 42
```

## Daily Scheduler (Cross-Platform)

Scheduler script: `trading/scripts/daily_paper_trading.py`

Behavior:

- Runs auto-trader for configured accounts
- Saves snapshots
- Prints strategy comparison
- Writes logs to `local/logs/`
- Stores run metadata including `RunSource`
- Skips duplicate successful same-day runs unless `--force-run`

Manual runs:

```powershell
# Normal run
python trading/scripts/daily_paper_trading.py --run-source manual

# Force extra same-day run
python trading/scripts/daily_paper_trading.py --run-source manual --force-run
```

Task Scheduler recommendation:

- `Trading\DailyPaperTrading` (daily)
- `Trading\DailyPaperTradingFallback` (startup fallback)

Create startup fallback task (Windows):

```powershell
$repoRoot = Get-Location
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$scriptPath = Join-Path $repoRoot "trading\scripts\daily_paper_trading.py"
$action = "`"$pythonExe`" `"$scriptPath`" --run-source startup-fallback"
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

Startup-folder fallback option (Windows):

```powershell
$startupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$repoRoot = Get-Location
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$cmdPath = Join-Path $startupDir "daily_paper_trading_fallback.cmd"
$content = "@echo off`r`ncd /d `"$repoRoot`"`r`n`"$pythonExe`" .\trading\scripts\daily_paper_trading.py --run-source startup-fallback`r`n"
Set-Content -Path $cmdPath -Value $content -Encoding ASCII
```

## Weekly DB Backup Scheduler (Cross-Platform)

Backup script: `trading/scripts/weekly_db_backup.py`

Scheduler registration script: `trading/scripts/register_weekly_backup.py`

Manual backup run:

```powershell
python trading/scripts/weekly_db_backup.py
```

Force a second backup in the same ISO week:

```powershell
python trading/scripts/weekly_db_backup.py --force-run
```

Register weekly schedule (uses Task Scheduler on Windows, cron on Linux):

```powershell
python trading/scripts/register_weekly_backup.py --day-of-week Sunday --time 02:00
```

Remove weekly schedule:

```powershell
python trading/scripts/register_weekly_backup.py --unregister
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
