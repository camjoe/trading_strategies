# Trading Package Map

Type: map
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-06-16
Purpose: Explain the trading/ hybrid architecture — layered backbone plus bounded contexts — and list every module with its layer placement.
Related: [Navigation Guide](../architecture/nav-guide.md), [Service Cookbook](../architecture/service-cookbook.md), [Service/Repository Boundary](../architecture/service-repository-boundary.md)

## Purpose

Explain the top-level `trading/` structure as a **hybrid architecture**:

- A horizontal layered backbone for runtime application behavior.
- A few explicit bounded contexts kept top-level because they encapsulate unique workflows or external integrations.

## Top-Level Shape

### Layered Backbone

- `trading/interfaces/`: transport and operator entrypoints (`cli`, `runtime/jobs`, `runtime/data_ops`)
- `trading/services/`: orchestration/composition workflows
- `trading/repositories/`: SQL persistence adapters
- `trading/domain/`: side-effect-free policy/math/state-transition logic and shared DI contracts (`BrokerConnection`, `FeatureFetcherSet`)
- `trading/database/`: DB infrastructure/config/coercion
- `trading/models/`: shared passive data contracts (`*Config`, `*Insert`, `*Record`, state/order models)
- `trading/config/`: static file-backed configuration assets

### Bounded Contexts

- `trading/backtesting/`: a self-contained layered subsystem with its own `domain/services/repositories`
- `brokers/` (repo root): broker adapters and factory boundary (paper + live integrations); injected at the interface layer (`trading/interfaces/`); `trading/` must never import from `brokers/` except at the interface layer
- `features/` (repo root): external-data feature-provider boundary for alternative strategies

## Placement Rules

- Use the layered backbone by default.
- Use top-level bounded contexts only when isolation materially improves clarity and safety.
- Keep `trading/models/` passive; move parsing/validation orchestration into services/domain helpers.
- Avoid adding facades that only forward imports unless they are deliberate public entrypoints.

## Module Directory

One-liner per module. For layering rules, allowed imports, and placement decisions see the sections above and `.github/BOT_ARCHITECTURE_CONVENTIONS.md`.

### `trading/interfaces/`

Entry points and transport. Nothing below this layer should know about CLI args, HTTP, or scheduled job runners.

**CLI** (`trading/interfaces/cli/`)

| Module | Responsibility |
|---|---|
| `commands/accounts.py` | Click commands for account actions |
| `commands/backtesting.py` | Click commands for backtesting |
| `commands/reporting.py` | Click commands for reporting |
| `commands/builder.py` | Shared Click group/command builder helpers |
| `commands/options.py` | Reusable Click option definitions |
| `handlers/accounts_handlers.py` | Business dispatch for account CLI commands |
| `handlers/backtesting_handlers.py` | Business dispatch for backtesting CLI commands |
| `handlers/reporting_handlers.py` | Business dispatch for reporting CLI commands |
| `handlers/router.py` | Top-level command-to-handler routing |
| `handlers/shared.py` | Shared handler utilities |
| `main.py` | CLI entry point (`@click.group`) |

**Runtime jobs** (`trading/interfaces/runtime/jobs/`)

| Module | Responsibility |
|---|---|
| `daily/paper_trading.py` | Main daily paper-trading execution job |
| `daily/paper_trading_dag.py` | DAG/sequencing logic for the daily job |
| `daily/snapshot.py` | Daily equity snapshot job |
| `daily/paper_trading_reporting.py` | Daily reporting artifact generation job |
| `daily/paper_trading_caps.py` | Daily trade-cap enforcement job |
| `daily/backtest_refresh.py` | Daily backtest result refresh job |
| `daily/challenger_shadow_eval.py` | Daily challenger shadow evaluation job |
| `daily/trader_health.py` | Daily health-check job |
| `governance/weekly/w1_leaderboard.py` | Weekly leaderboard governance job |
| `governance/weekly/w2_promotion_review.py` | Weekly promotion review governance job |
| `governance/weekly/w3_allocation_review.py` | Weekly allocation review governance job |
| `governance/monthly/m1_risk_rebaseline.py` | Monthly risk rebaseline governance job |
| `governance/monthly/m2_parameter_governance.py` | Monthly parameter governance job |
| `governance/monthly/m3_performance_audit.py` | Monthly performance audit governance job |
| `governance/payload_models.py` | Governance job payload models |
| `maintenance/burn_in_status.py` | Burn-in protocol status job |
| `maintenance/replay_daily_runs.py` | Replay/backfill historical daily runs |
| `maintenance/weekly_db_backup.py` | Weekly database backup job |
| `job_helpers.py` | Shared job utilities (timing, status writing) |
| `manage_job_schedules.py` | Install/update OS-level job schedules |
| `run_auto_trades.py` | Auto-trade execution runner |
| `scheduler_installer.py` | Scheduler installation logic |
| `job_status.py` | Job status tracking models |
| `notifications.py` | Notification/alerting dispatch from jobs |

**Runtime data ops** (`trading/interfaces/runtime/data_ops/`)

| Module | Responsibility |
|---|---|
| `admin.py` | One-off admin data operations (schema init, cleanup) |
| `csv_export.py` | One-off CSV export operation |

---

### `trading/services/`

Orchestration and composition. Calls repositories and domain; never builds SQL or imports from `trading/database/` directly (see `runtime_loader.py` exception below).

| Module | Responsibility |
|---|---|
| `accounting/mutations.py` | Cash/equity accounting write operations |
| `accounting/queries.py` | Cash/equity accounting read operations |
| `accounts/listing.py` | Account listing and filtering |
| `accounts/mutations.py` | Account create/update operations |
| `accounts/queries.py` | Account read queries (snapshots, config) |
| `accounts/config.py` | Account configuration helpers |
| `accounts/runtime_loader.py` | Load runtime-eligible account names; has documented layer-boundary exception to import from `trading.database` |
| `admin/deletions.py` | Admin bulk-deletion workflows |
| `analysis/position.py` | Position analysis calculations |
| `analysis/queries.py` | Analysis data queries |
| `auto_trading/execution.py` | Trade execution orchestration |
| `auto_trading/inputs.py` | Auto-trading input assembly |
| `auto_trading/market.py` | Market state helpers |
| `auto_trading/rotation_bridge.py` | Connects auto-trading to rotation domain logic |
| `auto_trading/rotation.py` | Rotation decision service |
| `auto_trading/runtime_reconciliation.py` | Runtime order/fill reconciliation |
| `auto_trading/runtime_rotation.py` | Runtime rotation execution |
| `auto_trading/runtime_sleeve_risk.py` | Runtime sleeve-level risk enforcement |
| `auto_trading/runtime.py` | Auto-trading runtime coordination |
| `evaluation/evidence.py` | Rotation episode evidence assembly |
| `evaluation/queries.py` | Evaluation data queries |
| `ibkr_paper_monitor/artifacts.py` | IBKR paper-monitor artifact assembly |
| `ibkr_paper_monitor/queries.py` | IBKR paper-monitor data queries |
| `market_data/cache.py` | Market data caching layer |
| `market_data/features.py` | Feature data fetching and assembly |
| `market_data/market_hours.py` | Market hours/calendar helpers |
| `market_data/protocols.py` | Market data protocol definitions |
| `market_data/providers.py` | Market data provider implementations |
| `market_data/registry.py` | Feature provider registry |
| `pricing/lookups.py` | Price lookup queries |
| `profiles/application.py` | Account profile application logic |
| `profiles/rotation_config_parser.py` | TOML rotation config parser |
| `profiles/source.py` | Profile source loading |
| `promotion/actions.py` | Promotion action execution |
| `promotion/assessment.py` | Promotion eligibility assessment |
| `promotion/helpers.py` | Promotion workflow helpers |
| `promotion/history.py` | Promotion history queries |
| `promotion/presentation.py` | Promotion result formatting |
| `reporting/backtest_returns.py` | Backtest return calculations for reporting |
| `reporting/benchmark.py` | Benchmark comparison reporting |
| `reporting/math.py` | Reporting math utilities |
| `reporting/portfolio.py` | Portfolio reporting |
| `reporting/presentation.py` | Report presentation formatting |
| `runtime_settings/models.py` | Runtime setting models |
| `runtime_settings/mutations.py` | Runtime setting write operations |
| `runtime_settings/queries.py` | Runtime setting read operations |
| `runtime_throttle/enforcement.py` | Runtime throttle enforcement logic |

---

### `trading/repositories/`

SQL persistence adapters only. Each file owns one logical data area. Builds SQL internally; callers pass plain data, not SQL fragments.

| Module | Responsibility |
|---|---|
| `accounts.py` | Equity snapshot and account snapshot persistence |
| `admin.py` | Admin/maintenance DB operations (row counts, deletions) |
| `backtest_history.py` | Backtest run history records |
| `broker_orders.py` | Broker-submitted order records |
| `daily_metrics.py` | Daily performance metric snapshots |
| `global_settings.py` | Key-value global settings table |
| `portfolio_risk_snapshots.py` | Portfolio risk snapshot records |
| `promotion.py` | Promotion decision records |
| `rotation_decisions.py` | Rotation decision records |
| `rotation.py` | Rotation state records |
| `sleeve_ledger.py` | Sleeve transaction ledger |
| `sleeve_orders.py` | Sleeve-level order records |
| `sleeve_positions.py` | Sleeve position records |
| `sleeve_risk_decisions.py` | Sleeve-level risk decision records |
| `sleeves.py` | Sleeve configuration and state |
| `snapshots.py` | Equity snapshot records (`EquitySnapshotRecord`) |
| `trades.py` | Trade execution records |

---

### `trading/domain/`

Side-effect-free logic: policy, math, state transitions, and DI contracts. No I/O, no SQL, no service calls.

| Module | Responsibility |
|---|---|
| `accounting.py` | Cash and equity accounting rules |
| `auto_trading_policy.py` | Auto-trading eligibility and policy rules |
| `broker_connection.py` | `BrokerConnection` protocol (DI contract) |
| `evaluation_confidence.py` | Evaluation confidence scoring logic |
| `evaluation_models.py` | Evaluation data models |
| `exceptions.py` | Domain-level exception types |
| `feature_provider.py` | `FeatureFetcherSet` protocol (DI contract) |
| `indicators_adapter.py` | Technical indicator adapters |
| `promotion_models.py` | Promotion state and result models |
| `promotion_policy.py` | Promotion eligibility rules |
| `returns.py` | Return calculation math |
| `rotation.py` | Rotation state-transition logic |
| `sleeve_accounting.py` | Sleeve-level accounting math |
| `sleeve_rotation.py` | Sleeve rotation rules |
| `strategy_signals.py` | Strategy signal models and processing |

---

### `trading/database/`

DB infrastructure. Only `trading/repositories/` and the documented `runtime_loader.py` exception should import from here.

| Module | Responsibility |
|---|---|
| `db_backend.py` | DB connection/backend factory |
| `db_config.py` | DB path and environment config |
| `db_init.py` | DB initialization (`ensure_db`) |
| `db_migrations.py` | Schema migration runner |
| `db_schema.py` | Table DDL definitions |
| `sql_helpers.py` | Low-level SQL utilities (`in_placeholders`, coercion helpers) |

---

### `trading/models/`

Passive data contracts. No business logic, no I/O.

| Module | Responsibility |
|---|---|
| `account_config.py` | `AccountConfig` configuration model |
| `account_insert.py` | `AccountInsert` creation input model |
| `account_record.py` | `AccountRecord` read model (implements `Mapping[str, object]`) |
| `account_state.py` | `AccountState` runtime state aggregation |
| `broker_order.py` | `BrokerOrder` model |
| `rotation_config.py` | `RotationConfig` data model |

---

### `trading/backtesting/` (bounded context)

Self-contained backtest subsystem with its own layered sub-packages.

| Module | Responsibility |
|---|---|
| `backtest.py` | Backtest execution engine |
| `trading_bridge.py` | Bridge to live trading domain logic |
| `models.py` | Backtest input/output models |
| `report_models.py` | Backtest report models |
| `domain/` | Backtesting-specific domain logic |
| `repositories/` | Backtest result persistence |
| `services/` | Backtest orchestration services |

---

### `trading/config/`

Static file-backed configuration assets. Read at runtime; not imported as Python modules (except by services/profiles).

| Asset | Description |
|---|---|
| `account_profiles/` | TOML account profile configs |
| `trade_universes/` | Trade universe definition files |
| `account_trade_caps.json` | Account-level trade cap limits |
| `trade_universe.txt` | Default trade universe ticker list |
| `trade_universe_sp500_broad.txt` | Broad S&P 500 trade universe |

---

## Related References

- [service-cookbook.md](../architecture/service-cookbook.md) — task-oriented API reference ("what function do I call to do X?")
- [nav-guide.md](../architecture/nav-guide.md) — "I want to X → look/edit Y" lookup table
- `.github/BOT_ARCHITECTURE_CONVENTIONS.md` — authoritative import boundary and layering rules
- `docs/reference/adr-backtesting-layering.md`
