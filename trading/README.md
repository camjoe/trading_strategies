# Trading Module

Core paper trading and backtesting engine for the repository.

## Purpose

Provide the core runtime and tooling for paper trading, reporting, promotion review workflows, scheduler operations, and backtesting support.

## Scope

The `trading/` module handles:

- Account lifecycle (create, configure, benchmark, profiles)
- Trade simulation and position tracking
- Live broker integration (Interactive Brokers via TWS/IB Gateway; paper broker by default)
- Snapshot history and reporting
- Promotion review request / approve / reject / note workflows with persisted audit history
- Auto-trading simulation runs
- Backtesting and walk-forward analysis support, including persisted per-window detail reporting
- **Alternative strategy external-data features** — real-time signal enrichment via news, social, and policy providers in `trading/features/`

Data is stored in SQLite, defaulting to `local/paper_trading.db`.

**DB path resolution:** `TRADING_DB_PATH` env var → `db_path` in `local/db_config.json` → `local/paper_trading.db`

When `db_path` in `local/db_config.json` is relative, it is resolved from the
repository root.

**Market data:** defaults to `yfinance`. Override via `TRADING_MARKET_DATA_PROVIDER` env var or `provider` in `local/market_data_config.json`. See `common/market_data_config.example.json` for the config format.

## Commands

All commands accept `--help` for the full flag reference.

```sh
python -m trading.interfaces.cli.main init
python -m trading.interfaces.cli.main create-account --name momentum_5k --strategy "Momentum" --initial-cash 5000
python -m trading.interfaces.cli.main report --account momentum_5k
python -m trading.interfaces.cli.main snapshot --account momentum_5k
python -m trading.interfaces.cli.main compare-strategies --lookback 10
python -m trading.interfaces.cli.main promotion-status --account momentum_5k
python -m trading.interfaces.cli.main promotion-request-review --account momentum_5k --requested-by operator
python -m trading.interfaces.runtime.jobs.daily_auto_trader --accounts momentum_5k,meanrev_5k
```

Backup and export:

```sh
python -m trading.interfaces.runtime.data_ops.admin backup-db
python -m trading.interfaces.runtime.data_ops.csv_export
python -m scripts.data_ops.backup_db
python -m scripts.data_ops.export_db_csv
```

Canonical admin/export modules live in `trading/interfaces/runtime/data_ops/`.
The `scripts.data_ops.*` commands are convenience wrappers around those
canonical runtime data-op modules and should not be treated as the ownership
source.

## Script Boundaries

- `trading/interfaces/runtime/jobs/`: production-like trading runtime tasks and schedulers.
- `trading/interfaces/runtime/data_ops/`: operator-facing DB admin and export utilities.
- `scripts/`: repository automation and CI/developer workflows.
- `trading/database/`: database infrastructure (schema init, backend, config, coercion).

Use `trading/interfaces/runtime/jobs/` for schedulers and `trading/interfaces/runtime/data_ops/` for operator-facing DB utilities.

### Runtime Script Catalog

- `daily_paper_trading.py`: orchestrates scheduled daily paper-trading run.
- `check_daily_trader_health.py`: verifies recency/health of daily trading runs.
- `daily_snapshot.py`: scheduled snapshot runner with duplicate-run guards and retry.
- `scheduled_backtest_refresh.py`: scheduled recurring backtest refresh runner with duplicate-run guards, transient retry handling, and JSON artifact output under `local/exports/scheduled_backtest_refresh/`.
- `weekly_db_backup.py`: scheduled weekly backup execution.
- `register_weekly_backup.py`: schedule registration helper for weekly backups.
- `trading/config/account_trade_caps.json`: per-account trade caps configuration used by the runtime scheduler. Supports per-account `min`/`max` trade counts, a `default` fallback, and an `excluded` list of account names that are automatically skipped when running with `--accounts all`.

## Auto-Trading

Trade universe files live under `trading/config/`. The default is `trade_universe.txt`. Two additional presets are provided:

| File | Description |
|------|-------------|
| `trading/config/trade_universe.txt` | Default universe (general-purpose) |
| `trading/config/trade_universe_test_account.txt` | Smaller universe for test accounts (~21 tickers) |
| `trading/config/trade_universe_sp500_broad.txt` | Broad S&P 500 universe (~50 tickers across all 11 GICS sectors) |

Pass `--tickers-file` to use a non-default universe. Use `python -m trading.interfaces.runtime.jobs.daily_auto_trader --help` for all options.

```sh
# Default universe
python -m trading.interfaces.runtime.jobs.daily_auto_trader --accounts momentum_5k,meanrev_5k

# S&P 500 broad universe
python -m trading.interfaces.runtime.jobs.daily_auto_trader --accounts momentum_5k,meanrev_5k --tickers-file trading/config/trade_universe_sp500_broad.txt
```

### Rotation overlays

Regime-rotation accounts can also enable `rotation_overlay_mode` (`news`, `social`, or `news_social`) to let alternative-data signals nudge the base policy regime.

- Overlay coverage is computed from the union of the account's current holdings and its per-account `rotation_overlay_watchlist`.
- New accounts and migrated existing accounts seed `rotation_overlay_watchlist` from `trading/config/trade_universe.txt`, providing a stable default universe before positions are opened.
- That seed is stored in the database schema/defaults at migration time. If you later change `trading/config/trade_universe.txt` and want that new list to propagate, you must also run an explicit DB update or migration/backfill for `rotation_overlay_watchlist`.
- Override the seeded watchlist per account through account profiles or the UI/API account-parameter endpoints when a narrower overlay universe is needed.

## Scheduler Operations

Runtime jobs in `trading/interfaces/runtime/jobs/` all accept `--help` for the full flag reference. Common manual invocations:

```sh
# Daily paper trading
python -m trading.interfaces.runtime.jobs.daily_paper_trading --run-source manual

# Daily snapshot
python -m trading.interfaces.runtime.jobs.daily_snapshot --run-source manual --enable-run

# Scheduled backtest refresh
python -m trading.interfaces.runtime.jobs.scheduled_backtest_refresh --accounts all --enable-run

# Weekly DB backup
python -m trading.interfaces.runtime.jobs.weekly_db_backup

# Health check
python -m trading.interfaces.runtime.jobs.check_daily_trader_health --max-age-hours 24

# Register weekly backup on scheduler (Windows Task Scheduler / Linux cron)
python -m trading.interfaces.runtime.jobs.register_weekly_backup --day-of-week Sunday --time 02:00
```

Windows Task Scheduler task names: `Trading\DailyPaperTrading`, `Trading\DailyPaperTradingFallback`, `Trading\DailySnapshot`.

## Promotion Review Workflow

Promotion readiness can now be reviewed through persisted operator workflows instead of read-only status checks only.

```sh
# Current computed readiness snapshot
python -m trading.interfaces.cli.main promotion-status --account momentum_5k

# Persist a manual review request with optional operator metadata
python -m trading.interfaces.cli.main promotion-request-review --account momentum_5k --requested-by operator --note "Ready for desk review"

# Inspect append-only review/audit history
python -m trading.interfaces.cli.main promotion-review-history --account momentum_5k --limit 10

# Approve, reject, or annotate an open review
python -m trading.interfaces.cli.main promotion-review-action --review-id 42 --action note --actor operator --note "Need another week of paper evidence"
```

Review requests freeze the current evaluation evidence into a durable record and append operator events for request, note, approve, and reject actions.

## Backtesting Notes

- `python -m trading.interfaces.cli.main backtest-walk-forward-report --group-id <id>` shows persisted walk-forward group details and per-window summaries after a walk-forward run completes.
- Scheduled recurring backtest refreshes are handled by `trading/interfaces/runtime/jobs/scheduled_backtest_refresh.py`, which writes machine-readable artifacts to `local/exports/scheduled_backtest_refresh/`.

## Notes

- Sells are restricted to current holdings (no shorting).
- Buys require sufficient available cash.
- **Deposit model:** Trades whose `ticker` equals the settlement ticker (`"CASH"`) are
  treated as cash inflows/outflows rather than equity position changes. A `CASH` buy adds
  the notional value directly to `state.cash` and `state.total_deposited`; a `CASH` sell
  subtracts it. Accounts that seed capital this way set `initial_cash = 0` in the DB and
  inject funds via `CASH` buy trades. The settlement ticker is configurable via the
  `settlement_ticker` argument of `compute_account_state` (defaults to
  `SETTLEMENT_TICKER = "CASH"`). Pass `None` to treat every ticker as a regular equity.
- `AccountState.total_deposited` accumulates all capital deposited via settlement-ticker
  buys. Services use this as the P&L-percentage denominator for `initial_cash = 0` accounts.
- Latest prices for unrealized PnL via `yfinance`.
- Trend classification: `up`, `flat`, `down`, or `insufficient-data`.

## Related Docs

- Backtesting: `docs/reference/notes-backtesting.md`
- UI dashboard: `paper_trading_ui/README.md`
- Broker integration: `docs/reference/notes-broker-integration.md`
- Trading architecture guide: `.github/BOT_ARCHITECTURE_CONVENTIONS.md`

## Preset Profiles

Built-in account profile presets now live under:

- `trading/config/account_profiles/`

CLI defaults use `trading/config/account_profiles/default.json`.

## Boundary Snapshot

- The CLI entry point is `trading/interfaces/cli/main.py` (`python -m trading.interfaces.cli.main`). The auto-trader entry point is `trading/interfaces/runtime/jobs/daily_auto_trader.py` (`python -m trading.interfaces.runtime.jobs.daily_auto_trader`). There are no top-level facade modules in `trading/`.
- SQL access is owned by repository modules under `trading/repositories/`.
- Orchestration and composition are owned by service modules under `trading/services/`.
- Policy logic is owned by domain modules under `trading/domain/`.
- **External-data feature providers** live in `trading/features/` — the only package permitted to import `praw`, `pytrends`, `vaderSentiment`, `newsapi-python`, or make calls to third-party external data services. Signal functions in `trading/backtesting/domain/strategy_signals.py` consume normalised `ExternalFeatureBundle` values from this package; they never call external APIs directly.
