# Trading Module

Core paper trading and backtesting engine for the repository.

## Scope

The `trading/` module handles:

- Account lifecycle (create, configure, benchmark, profiles)
- Trade simulation and position tracking
- Snapshot history and reporting
- Auto-trading simulation runs
- Backtesting and walk-forward analysis support

Data is stored in SQLite, defaulting to `local/paper_trading.db`.

**DB path resolution:** `TRADING_DB_PATH` env var → `db_path` in `local/db_config.json` → `local/paper_trading.db`

**Market data:** defaults to `yfinance`. Override via `TRADING_MARKET_DATA_PROVIDER` env var or `provider` in `local/market_data_config.json`. See `common/market_data_config.example.json` for the config format.

## Common Operations

All commands accept `--help` for the full flag reference.

```sh
python -m trading.paper_trading init
python -m trading.paper_trading create-account --name momentum_5k --strategy "Momentum" --initial-cash 5000
python -m trading.paper_trading report --account momentum_5k
python -m trading.paper_trading snapshot --account momentum_5k
python -m trading.paper_trading compare-strategies --lookback 10
python -m trading.auto_trader --accounts momentum_5k,meanrev_5k
```

Backup and export:

```sh
python -m scripts.data_ops.backup_db
python -m scripts.data_ops.export_db_csv
```

## Script Boundaries

- `trading/interfaces/runtime/jobs/`: production-like trading runtime tasks and schedulers.
- `scripts/`: repository automation and CI/developer workflows.
- `trading/database/admin.py`: local DB maintenance/admin tasks (CLI: `python -m trading.database.admin`).

Use `trading/interfaces/runtime/jobs/` for runtime scheduler jobs; keep maintenance and repo workflows out of that folder.

### Runtime Script Catalog

- `daily_paper_trading.py`: orchestrates scheduled daily paper-trading run.
- `check_daily_trader_health.py`: verifies recency/health of daily trading runs.
- `daily_snapshot.py`: scheduled snapshot runner with duplicate-run guards and retry.
- `weekly_db_backup.py`: scheduled weekly backup execution.
- `register_weekly_backup.py`: schedule registration helper for weekly backups.
- `../interfaces/runtime/config/account_trade_caps.json`: per-account trade caps configuration used by the runtime scheduler.

## Auto-Trading

Trade universe: `trading/trade_universe.txt`. Use `python -m trading.auto_trader --help` for all options.

```sh
python -m trading.auto_trader --accounts momentum_5k,meanrev_5k
```

## Scheduler Operations

Runtime jobs in `trading/interfaces/runtime/jobs/` all accept `--help` for the full flag reference. Common manual invocations:

```sh
# Daily paper trading
python -m trading.interfaces.runtime.jobs.daily_paper_trading --run-source manual

# Daily snapshot
python -m trading.interfaces.runtime.jobs.daily_snapshot --run-source manual --enable-run

# Weekly DB backup
python -m trading.interfaces.runtime.jobs.weekly_db_backup

# Health check
python -m trading.interfaces.runtime.jobs.check_daily_trader_health --max-age-hours 24

# Register weekly backup on scheduler (Windows Task Scheduler / Linux cron)
python -m trading.interfaces.runtime.jobs.register_weekly_backup --day-of-week Sunday --time 02:00
```

Windows Task Scheduler task names: `Trading\DailyPaperTrading`, `Trading\DailyPaperTradingFallback`, `Trading\DailySnapshot`.

## Notes

- Sells are restricted to current holdings (no shorting).
- Buys require sufficient available cash.
- Latest prices for unrealized PnL via `yfinance`.
- Trend classification: `up`, `flat`, `down`, or `insufficient-data`.

## Related Docs

- Backtesting: `docs/backtesting.md`
- UI dashboard: `paper_trading_ui/README.md`
- Structure migration plan: `docs/architecture/trading-structure-migration-plan.md`

## Preset Profiles

Built-in account profile presets now live under:

- `trading/config/account_profiles/`

CLI defaults use `trading/config/account_profiles/default.json`. Legacy `trading/account_profiles/...` paths are still resolved for compatibility.