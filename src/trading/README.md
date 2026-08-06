# Trading Module

Core paper trading and backtesting engine for the repository.

## Purpose

Provide the core runtime and tooling for paper trading, reporting, promotion review workflows, scheduler operations, and backtesting support.

## Scope

The `src/trading/` module handles:

- Account lifecycle (create, configure, benchmark, profiles)
- Trade simulation and position tracking
- Live broker integration (Interactive Brokers via Client Portal/Web API or the TWS/IB Gateway socket API; paper broker by default)
- Snapshot history and reporting
- Promotion review request / approve / reject / note workflows with persisted audit history
- Auto-trading simulation runs
- Backtesting and walk-forward optimization, including persisted per-window and per-candidate audit trails
- **Alternative strategy external-data features** — real-time signal enrichment via news, social, and policy providers in `src/infrastructure/feature_providers/` (repo root)

## Architecture Shape

`src/trading/` uses a **hybrid structure**:

- A layered backbone for most runtime behavior:
  - `interfaces -> services -> repositories/domain -> database`
- Explicit top-level bounded contexts where isolation is valuable:
  - `src/trading/backtesting/`
  - `src/infrastructure/brokers/` (repo root — broker adapters)
  - `src/infrastructure/feature_providers/` (repo root — external-data feature providers)

`src/trading/models/` is reserved for passive shared data contracts (`*Config`, `*Insert`, `*Record`, state/order models). Parsing and validation orchestration belongs in services/domain helpers.

For the concise package map, see `docs/maps/trading-package-map.md`.
For a task-oriented API reference ("what do I call to do X?"), see `docs/architecture/service-cookbook.md`.
For a "where do I put X" placement guide, see `docs/architecture/nav-guide.md`.

Data is stored in SQLite, defaulting to `local/paper_trading.db`.

**DB path resolution:** `TRADING_DB_PATH` env var → `local/paper_trading.db`

To point tooling at a disposable database, run `scripts/launch_sandbox.py` or
`scripts/launch_demo.py`, which set `TRADING_DB_PATH` for you.

**Market data:** defaults to `yfinance`. Override via the `TRADING_MARKET_DATA_PROVIDER` env var (`yfinance` or `demo`); any other value raises at `build_provider()`.

## Quick Start

Run these common commands from the repository root with the virtual environment created in the root
README active.

```sh
python -m scripts.data_ops.manage_db_migrations upgrade
python -m trading.interfaces.cli.main apply-account-preset --preset default
python -m trading.interfaces.runtime.jobs.daily.paper_trading.run_auto_trades --accounts momentum_5k,meanrev_5k
```

The migration command creates a missing database or upgrades an existing one. Application commands
verify the schema version and never apply migrations automatically. The tracked presets contain
synthetic examples only.

For scheduler operations, promotion review flows, and data-ops commands, use the detailed sections below.

## Commands

All commands accept `--help` for the full flag reference.

```sh
python -m trading.interfaces.cli.main create-account --name momentum_5k --strategy "Momentum" --initial-cash 5000
python -m trading.interfaces.cli.main report --account momentum_5k
python -m trading.interfaces.cli.main snapshot --account momentum_5k
python -m trading.interfaces.cli.main compare-strategies --lookback 10
python -m trading.interfaces.cli.main promotion-status --account momentum_5k
python -m trading.interfaces.cli.main promotion-request-review --account momentum_5k --requested-by operator
python -m trading.interfaces.runtime.jobs.daily.paper_trading.run_auto_trades --accounts momentum_5k,meanrev_5k
```

Backup and export:

```sh
python -m trading.interfaces.runtime.data_ops.admin backup-db
python -m scripts.data_ops.backup_db
python -m scripts.data_ops.export_db_csv --table accounts
```

`export_db_csv` generates CSV on demand from the live database (one table per
invocation); pass `--out <path>` to save it, or omit `--out` to print to stdout.
Nothing is written to disk unless `--out` is given.

Canonical admin/export modules live in `src/trading/interfaces/runtime/data_ops/`.
The `scripts.data_ops.*` commands are convenience wrappers around those
canonical runtime data-op modules and should not be treated as the ownership
source.

## Script Boundaries

- `src/trading/interfaces/runtime/jobs/`: direct runtime job entrypoints plus thin scheduler-install helpers.
- `src/trading/interfaces/runtime/data_ops/`: operator-facing DB admin and export utilities.
- `scripts/`: repository automation and CI/developer workflows.
- `src/infrastructure/database/`: database migrations, schema-version verification, backend, and config.

Use `src/trading/interfaces/runtime/jobs/` for schedulers and `src/trading/interfaces/runtime/data_ops/` for operator-facing DB utilities.

### Runtime Script Catalog

The full module inventory is the [Trading Package Map](../../docs/maps/trading-package-map.md) — the
single source of truth for `src/trading/` modules and their responsibilities. For how to run or
schedule the runtime job entrypoints, see the [Runtime Jobs Reference](../../docs/reference/runtime-jobs.md).

## Auto-Trading

Trade universe files live under `src/infrastructure/config/`. The default is `trade_universe.txt`.

Pass `--tickers-file` to use a non-default universe. Run
`python -m trading.interfaces.runtime.jobs.daily.paper_trading.run_auto_trades --help`
for all options.

```sh
python -m trading.interfaces.runtime.jobs.daily.paper_trading.run_auto_trades --accounts momentum_5k,meanrev_5k
```

For live broker accounts, each account run now reuses a single broker
connection for the full trade loop. This lets session-backed adapters such as
the IBKR Web API client keep their connection alive across multiple trades in
one autoscript run.

Auto-trader order submission is now also gated to regular U.S. equity market
hours. When the market is closed, autonomous trade runs skip broker order
placement instead of submitting paper or live orders outside the session. The
guard includes major full-day NYSE holidays plus scheduled 1:00 PM Eastern
early closes for the day after Thanksgiving, eligible July 3 sessions, and
eligible Christmas Eve sessions.

## Scheduler Operations

Runtime job entrypoints, how to run them directly, and how to register or remove scheduler entries
are documented in the [Runtime Jobs Reference](../../docs/reference/runtime-jobs.md). For monitoring
and recovery, see the [Runtime Operations Runbook](../../docs/runbooks/runtime-operations.md).

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

- `python -m trading.interfaces.cli.main backtest-optimize-show <experiment_id>`
  shows a stored optimization experiment: winner params, OOS/holdout evidence, the per-window and
  per-candidate audit trail, and the promotion-gate preview.

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

- Backtesting: [docs/reference/backtesting.md](../../docs/reference/backtesting.md)
- UI dashboard: [apps/paper_trading_web/README.md](../../apps/paper_trading_web/README.md)
- Broker integration: [docs/reference/broker-integration.md](../../docs/reference/broker-integration.md)
- Trading architecture guide: [docs/architecture/architecture-conventions.md](../../docs/architecture/architecture-conventions.md)

## Preset Profiles

Built-in account profile presets now live under:

- `src/infrastructure/config/account_profiles/`

CLI defaults use `src/infrastructure/config/account_profiles/default.json`.

These tracked presets are synthetic examples for testing and demonstration. Their account names,
capital amounts, return goals, risk limits, and strategy schedules do not represent actual accounts,
validated performance expectations, or recommended settings.

Keep real strategy parameters, operator profiles, and research notes under the gitignored
`local/strategies/` workspace. Do not replace the tracked presets with personal operating
configuration. If private strategy implementation code later needs to run as part of the application,
move it into a separately distributed private package or repository rather than importing code from
`local/`.

## Boundary Snapshot

- The CLI entry point is `src/trading/interfaces/cli/main.py`
  (`python -m trading.interfaces.cli.main`). The auto-trader entry point is
  `src/trading/interfaces/runtime/jobs/daily/paper_trading/run_auto_trades.py`
  (`python -m trading.interfaces.runtime.jobs.daily.paper_trading.run_auto_trades`).
  There are no top-level facade modules in `src/trading/`.
- SQL access is owned by repository modules under `src/trading/repositories/`.
- Orchestration and composition are owned by service modules under `src/trading/services/`.
- Policy logic is owned by domain modules under `src/trading/domain/`.
- Concrete broker, market-data, and external-data adapters live in `src/infrastructure/`; import
  ownership is enforced by `scripts/checks/repo/layer_check.py`.
