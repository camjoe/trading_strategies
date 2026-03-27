# Trading Module

Core paper trading and backtesting engine for the repository.

## Quick Links

- [Scope](#scope)
- [Main commands](#main-commands)
- [Auto-trading](#auto-trading)
- [Daily scheduler (Windows)](#daily-scheduler-windows)
- [Script Boundaries](#script-boundaries)
- [Notes](#notes)
- [Related docs](#related-docs)

## Scope

The `trading/` module handles:

- Account lifecycle (create, configure, benchmark, profiles)
- Trade simulation and position tracking
- Snapshot history and reporting
- Auto-trading simulation runs
- Backtesting and walk-forward analysis support

Data is stored in SQLite with a default runtime location of `local/paper_trading.db`.

Runtime DB location is config-driven and defaults to `local/paper_trading.db`.

Resolution order:

- `TRADING_DB_PATH` environment variable
- `db_path` in `local/db_config.json`
- built-in fallback to `local/paper_trading.db`

DB abstraction notes:

- UI/backend code now handles account-create uniqueness failures through a backend-agnostic `DuplicateRecordError` instead of catching `sqlite3.IntegrityError` directly.
- CSV export now opens connections through the configured database backend path; when `db_path` is explicitly passed, export uses a backend instance bound to that path.

Market data provider notes:

- Runtime market data provider is configurable and currently defaults to `yfinance`.
- Resolution order:
	- `TRADING_MARKET_DATA_PROVIDER` environment variable
	- `provider` in `local/market_data_config.json` (or alternate path via `TRADING_MARKET_DATA_CONFIG`)
	- built-in fallback to `yfinance`
- Planned provider names are pre-wired for config/runtime selection but intentionally not implemented yet:
	- `yahooquery`, `pandas-datareader`, `alpha_vantage`, `tiingo`, `polygon-api-client`, `ccxt`
- Until those providers are implemented, use `yfinance` for live runs.

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

## Script Boundaries

- `trading/scripts/`: production-like trading runtime tasks and schedulers.
- `scripts/`: repository automation and CI/developer workflows.
- `dev_tools/`: local maintenance/admin tasks for the trading database.

Use `trading/scripts/` for anything that is part of trading runtime behavior; keep maintenance and repo workflows out of that folder.

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

Runtime script inventory: `trading/scripts/README.md`

Scheduler script: `trading/scripts/daily_paper_trading.py`

**Execution:**

```powershell
python -m trading.scripts.daily_paper_trading --accounts momentum_5k,meanrev_5k
python -m trading.scripts.daily_snapshot --enable-run
```

Behavior:

- Runs auto-trader for configured accounts
- Defaults to all accounts in the DB (`--accounts all`)
- Applies per-account trade caps from JSON config: `trading/scripts/account_trade_caps.json`
- Supports per-account overrides with `--account-trade-caps account:min-max,...`
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

# Example custom per-account caps
python trading/scripts/daily_paper_trading.py --run-source manual --account-trade-caps momentum_5k:1-5,core_growth_20k:1-8,rotation_optimal_5k:1-6

# Use a custom caps config file
python trading/scripts/daily_paper_trading.py --run-source manual --trade-caps-config local/my_trade_caps.json
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

Health check (fails if no recent successful daily run):

```powershell
python trading/scripts/check_daily_trader_health.py --max-age-hours 24
```

JSON output for automation/alerts:

```powershell
python trading/scripts/check_daily_trader_health.py --max-age-hours 24 --json
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

Manual retention backup (keeps rolling recent backups plus monthly archives):

```powershell
python scripts/data_ops/backup_db.py
```

CSV export snapshot (timestamped folder under `local/exports/`):

```powershell
python scripts/data_ops/export_db_csv.py
```

CSV export + ZIP archive (same folder plus `.zip`):

```powershell
python scripts/data_ops/export_db_csv_zip.py
```

Export specific tables only:

```powershell
python scripts/data_ops/export_db_csv.py --tables accounts,trades,equity_snapshots
```

Backup destinations:

- `python -m trading.database.admin backup-db` defaults to `local/backups/`
- `python scripts/data_ops/backup_db.py` defaults to `local/db_backups/`

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

## Daily Snapshot Scheduler (Cross-Platform)

Snapshot script: `trading/scripts/daily_snapshot.py`

Behavior:

- Runs `snapshot` for selected accounts (default: all accounts in DB)
- Writes log output to `local/logs/`
- Writes timestamped run artifact metadata to `local/exports/daily_snapshots/`
- Disabled by default until explicitly enabled with `--enable-run` or `DAILY_SNAPSHOT_ENABLED=1`
- Skips duplicate successful same-day runs unless `--force-run` is supplied
- Retries transient snapshot failures with exponential backoff

Manual run:

```powershell
python trading/scripts/daily_snapshot.py --run-source manual --enable-run
```

Force same-day rerun:

```powershell
python trading/scripts/daily_snapshot.py --run-source manual --force-run --enable-run
```

Tune retry/backoff behavior:

```powershell
python trading/scripts/daily_snapshot.py --max-attempts 4 --backoff-seconds 3.0 --enable-run
```

Windows Task Scheduler recommendation:

- `Trading\DailySnapshot` (daily)

Example registration:

```powershell
$repoRoot = Get-Location
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$scriptPath = Join-Path $repoRoot "trading\scripts\daily_snapshot.py"
$action = "`"$pythonExe`" `"$scriptPath`" --run-source scheduled-daily-snapshot --enable-run"
schtasks /Create /TN "Trading\DailySnapshot" /SC DAILY /ST 16:00 /TR $action /F
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
