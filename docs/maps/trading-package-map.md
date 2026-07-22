# Trading Package Map

Type: map
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-07-21
Purpose: Explain the src/trading/ hybrid architecture — layered backbone plus bounded contexts — and list every module with its layer placement. Infrastructure adapters live in the sibling [Infrastructure Map](infrastructure-map.md).
Related: [Navigation Guide](../architecture/nav-guide.md), [Service Cookbook](../architecture/service-cookbook.md), [Service/Repository Boundary](../architecture/service-repository-boundary.md)

## Purpose

Explain the top-level `src/trading/` structure as a **hybrid architecture**:

- A horizontal layered backbone for runtime application behavior.
- A few explicit bounded contexts kept top-level because they encapsulate unique workflows or external integrations.

## Top-Level Shape

### Layered Backbone

- `src/trading/interfaces/`: transport and operator entrypoints (`cli`, `runtime/jobs`, `runtime/scheduling`, `runtime/data_ops`)
- `src/trading/services/`: orchestration/composition workflows
- `src/trading/repositories/`: SQL persistence adapters
- `src/trading/domain/`: side-effect-free policy/math/state-transition logic and DI contracts (`BrokerConnection`, `FeatureFetcherSet`, `StrategySpec`)
- `src/trading/models/`: all passive data contracts (`*Config`, `*Insert`, `*Record`, state/order models, and domain value objects), organized into feature subfolders. The **lowest layer** — imports nothing from other trading layers or infrastructure.

Concrete infrastructure (database, brokers, feature providers, the market-data adapter, and static config assets) lives in the sibling `src/infrastructure/` package — see the [Infrastructure Map](infrastructure-map.md). Persistence flows through `src/trading/repositories/` into `src/infrastructure/database/`; the other adapters are injected at the interface layer.

### Bounded Contexts

- `src/trading/backtesting/`: a self-contained layered subsystem with its own `domain/services/repositories`

## Placement Rules

- Use the layered backbone by default.
- Use top-level bounded contexts only when isolation materially improves clarity and safety.
- Keep `src/trading/models/` passive; move parsing/validation orchestration into services/domain helpers.
- Avoid adding facades that only forward imports unless they are deliberate public entrypoints.

## Module Directory

One-liner per module. For layering rules, allowed imports, and placement decisions see the sections above and `docs/architecture/architecture-conventions.md`.

### `src/trading/interfaces/`

Entry points and transport. Nothing below this layer should know about CLI args, HTTP, or scheduled job runners.

**CLI** (`src/trading/interfaces/cli/`)

| Module | Responsibility |
|---|---|
| `commands/accounts.py` | argparse subcommands for account actions |
| `commands/backtesting.py` | argparse subcommands for backtesting |
| `commands/reporting.py` | argparse subcommands for reporting |
| `commands/settings.py` | argparse subcommands for operational-settings and rotation-policy edits |
| `commands/strategy_catalog.py` | argparse subcommands for strategy-catalog editing (variant, configure, freeze) |
| `commands/builder.py` | Assembles the argparse parser + subcommand groups |
| `commands/options.py` | Reusable argparse option definitions |
| `handlers/accounts_handlers.py` | Business dispatch for account CLI commands |
| `handlers/backtesting_handlers.py` | Business dispatch for backtesting CLI commands |
| `handlers/reporting_handlers.py` | Business dispatch for reporting CLI commands |
| `handlers/settings_handlers.py` | Business dispatch for settings edit commands — merges partial flags over current effective values |
| `handlers/strategy_catalog_handlers.py` | Business dispatch for strategy-catalog CLI commands |
| `handlers/router.py` | Top-level command-to-handler routing |
| `handlers/shared.py` | Shared handler utilities |
| `main.py` | CLI entrypoint (argparse); builds the parser, injects service deps, dispatches to handlers |

**Runtime jobs** (`src/trading/interfaces/runtime/jobs/`)

| Module | Responsibility |
|---|---|
| `daily/paper_trading/` | Daily paper-trading job package; job logic in `__init__`, run via `-m …daily.paper_trading` |
| `daily/paper_trading/__main__.py` | Entrypoint shim that runs the package job |
| `daily/paper_trading/dag.py` | DAG/sequencing logic for the daily job |
| `daily/paper_trading/caps.py` | Daily trade-cap enforcement |
| `daily/paper_trading/reporting.py` | Daily reporting artifact generation |
| `daily/paper_trading/run_auto_trades.py` | Auto-trade execution worker the daily job shells out to (also runnable standalone) |
| `daily/snapshot.py` | Daily equity snapshot job |
| `daily/backtest_refresh.py` | Daily job that re-runs only stale/missing backtests across each account's rotation candidates (incumbent + challengers) |
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
| `job_runner/_core.py` | Private shared job-lifecycle core (parser, dedup, DB session, flows) behind the decorators (ADR 006) |
| `job_runner/governance.py` | `governance_job` decorator — whole-run governance jobs |
| `job_runner/daily.py` | `daily_account_job` decorator — per-account daily jobs |
| `job_runner/maintenance.py` | `maintenance_job` decorator — non-account maintenance jobs |

**Runtime scheduling** (`src/trading/interfaces/runtime/scheduling/`)

| Module | Responsibility |
|---|---|
| `manage_job_schedules.py` | Operator entrypoint: install/remove OS-level schedules that invoke the runtime jobs |
| `scheduler_installer.py` | Platform schedule-installation logic (cron, systemd timers, Windows Task Scheduler) |

**Runtime data ops** (`src/trading/interfaces/runtime/data_ops/`)

| Module | Responsibility |
|---|---|
| `admin.py` | One-off admin data operations (schema init, cleanup) |
| `csv_export.py` | One-off CSV export operation |
| `seed_clean_schema.py` | Seed clean-schema strategy catalog and default strategy books bootstrap |

**Runtime (shared)** (`src/trading/interfaces/runtime/`)

| Module | Responsibility |
|---|---|
| `job_status.py` | Job status tracking models |
| `notifications.py` | Notification/alerting dispatch from runtime jobs |

---

### `src/trading/services/`

Orchestration and composition. Calls repositories and domain; never builds SQL or imports from `src/infrastructure/database/` directly (see `runtime_loader.py` exception below).

| Module | Responsibility |
|---|---|
| `accounting/mutations.py` | Cash/equity accounting write operations |
| `accounting/queries.py` | Cash/equity accounting read operations |
| `accounts/listing.py` | Account listing and filtering |
| `accounts/mutations.py` | Account create/update operations |
| `accounts/queries.py` | Account read queries (snapshots, config) |
| `accounts/config.py` | Account configuration helpers |
| `accounts/deletions.py` | Account deletion workflow (dry-run counts + cascade-backed delete) |
| `accounts/runtime_loader.py` | Load runtime-eligible account names; has documented layer-boundary exception to import from `src/infrastructure/database/` |
| `analysis/position.py` | Position analysis calculations |
| `analysis/queries.py` | Analysis data queries |
| `analysis/performance.py` | Book performance window queries (reads daily metrics) |
| `analysis/risk_snapshots.py` | Latest account risk snapshot access (clean risk_snapshots) |
| `analysis/exposure.py` | Cross-account exposure rollup over latest equity snapshots + open positions |
| `analysis/concentration.py` | Cross-account symbol/sector concentration rollup over persisted positions |
| `auto_trading/execution.py` | Trade execution orchestration |
| `auto_trading/inputs.py` | Auto-trading input assembly |
| `auto_trading/market.py` | Market state helpers |
| `auto_trading/runtime_reconciliation.py` | Runtime order/fill reconciliation |
| `auto_trading/runtime_book_risk.py` | Book-keyed runtime risk persistence (exposure snapshot + normalized decisions to the clean risk tables) |
| `auto_trading/runtime.py` | Auto-trading runtime coordination |
| `backtesting/stale_backtests.py` | Enumerate (account, strategy) pairs whose backtest is stale or missing across each account's rotation candidates (backtest-freshness remediation) |
| `evaluation/evidence.py` | Strategy evaluation evidence assembly (backtest, walk-forward, paper/live windows) + the advisory backtest-freshness diagnostic |
| `evaluation/queries.py` | Evaluation data queries |
| `demo/seeding.py` | Atomic application-owned synthetic account, trading, backtest, and promotion demo story |
| `execution/constants.py` | Kill-switch reasons + reconciliation thresholds for the shared execution path |
| `execution/gate.py` | Pre-submit safety-gate protocol + pass-through gate + audit-sink protocol — the injected kill-switch seam for book submission |
| `execution/nav.py` | Book NAV marking: re-mark a book's/account's positions to current prices and refresh `current_equity` |
| `execution/pre_submit_gate.py` | `BookPreSubmitGate`: book-as-bucket gate reusing the domain notional risk gate + stale-price/reconciliation kill switches |
| `execution/reconciliation.py` | Book equity reconciliation: NAV-marked book equity vs latest snapshot → kill-switch reasons (the gate delegates here) |
| `execution/submission.py` | Shared book order-submission service: gate → broker place → persist clean orders/fills/positions/ledger |
| `autonomy_monitor/artifacts.py` | Autonomy-monitor artifact assembly |
| `autonomy_monitor/queries.py` | Autonomy-monitor data queries |
| `market_data/features.py` | `ProxyFeatureDataProvider` — free-first proxy feature computation over an injected provider |
| `market_data/protocols.py` | Market-data + feature ports (`MarketDataProvider`, `FeatureDataProvider`, `FeatureBundle`) and the `require_*` injection guards |
| `market_data/factory.py` | `build_feature_provider` (the concrete market-data adapter + factory live in `src/infrastructure/market_data/`) |
| `pricing/lookups.py` | Price lookup queries |
| `profiles/application.py` | Account profile application logic |
| `profiles/rotation_config_parser.py` | Parse the profile's nested `rotation` object into a `BookRotationConfig` (book-owned scheduling, ADR 014) |
| `profiles/source.py` | Profile source loading |
| `promotion/actions.py` | Promotion action execution |
| `promotion/assessment.py` | Promotion eligibility assessment |
| `promotion/helpers.py` | Promotion workflow helpers |
| `promotion/history.py` | Promotion history queries |
| `promotion/presentation.py` | Promotion result formatting |
| `reporting/benchmark.py` | Benchmark comparison reporting |
| `reporting/math.py` | Reporting math utilities |
| `reporting/portfolio.py` | Portfolio reporting |
| `reporting/presentation.py` | Report presentation formatting |
| `reporting/exposure.py` | Printed view of the cross-account exposure rollup (payload lives in `analysis/exposure.py`) |
| `reporting/concentration.py` | Printed view of the cross-account concentration rollup (payload lives in `analysis/concentration.py`) |
| `operational_settings/models.py` | Operational setting models |
| `operational_settings/mutations.py` | Operational setting write operations |
| `operational_settings/queries.py` | Operational setting read operations |
| `operational_settings/enforcement.py` | Trade throttle enforcement logic |
| `books/book_assignments.py` | Book strategy assignments — the single live assignment record + trading/report book enumerations |
| `books/challenger_evaluation.py` | Per-book challenger enumeration for the daily shadow-eval job (`ChallengerEvaluationRun`) |
| `books/daily_report.py` | Multi-book daily operator report assembly |
| `books/execution.py` | Multi-book trade-candidate generation (`generate_book_trade_intents`) |
| `books/helpers.py` | Shared book service helpers (window math) |
| `books/rotation.py` | Book rotation apply + shared book-keyed rotation core (`RotationPolicyConfig`, `evaluate_book_rotation`, cooldown, per-book policy resolution `resolve_rotation_policy_config`) |
| `parameters/view.py` | Unified parameter source: read-through view over global settings, book settings, and strategy rows |
| `parameters/presentation.py` | Printed view of the unified parameter source |
| `parameters/mutations.py` | Targeted book rotation-policy edit workflow |
| `books/rotation_metrics.py` | Paradigm-neutral rotation strategy-metrics builder (decision score → `RotationStrategyMetrics`) |
| `books/sector_config.py` | Operator-editable symbol-sector config loading |
| `strategy_catalog/seeding.py` | Seed strategies catalog and per-account default books from code |
| `strategy_catalog/resolution.py` | Resolve a catalog strategy key to its primitive + effective knobs (canonical runtime read path) |
| `strategy_catalog/mutations.py` | Operator edits: create variant, configure draft knobs, freeze |
| `universe/resolver.py` | Trade-universe name resolution |

---

### `src/trading/repositories/`

SQL persistence adapters only. Each file owns one logical data area. Builds SQL internally; callers pass plain data, not SQL fragments.

| Module | Responsibility |
|---|---|
| `accounts.py` | Account records, deletion-count queries, and cascade-backed account deletion |
| `daily_metrics.py` | Daily performance metric snapshots |
| `demo_seed.py` | Persistence operations for the synthetic offline demo story |
| `feature_providers.py` | Feature provider enablement and config records |
| `global_settings.py` | Key-value global settings table |
| `ledger.py` | Clean-schema book-keyed ledger entry records |
| `orders.py` | Clean-schema orders table (unifies broker + book orders) |
| `positions.py` | Clean-schema position records keyed by (book_id, symbol) |
| `promotion.py` | Promotion decision records |
| `risk.py` | Clean-schema risk snapshots and risk decision records |
| `rotation_decisions.py` | Rotation decision records |
| `snapshots.py` | Equity snapshot records (`EquitySnapshotRecord`) |
| `strategies.py` | Clean-schema strategies catalog (primitive + knobs) |
| `books.py` | Clean-schema strategy books — execution primitives |
| `book_settings.py` | Per-concern typed book settings (execution, rotation, options) |
| `book_assignments.py` | Book-strategy assignment and lifecycle records |
| `book_bridge.py` | Interim bridges reaching clean-schema tables from legacy account/label access paths |
| `unit_of_work.py` | Re-entrant transaction scope and commit helper for grouping repository writes atomically |

---

### `src/trading/domain/`

Side-effect-free logic: policy, math, state transitions, and DI contracts. No I/O, no SQL, no service calls.

| Module | Responsibility |
|---|---|
| `accounting.py` | Cash and equity accounting rules |
| `auto_trading_policy.py` | Auto-trading eligibility and policy rules |
| `backtest_freshness.py` | `assess_backtest_freshness` — advisory staleness policy over backtest timestamps |
| `broker_connection.py` | `BrokerConnection` protocol (DI contract) |
| `evaluation_confidence.py` | Evaluation confidence scoring logic + `EvaluationConfidenceSettings` policy knobs |
| `evaluation_decision_score.py` | `derive_decision_score` pure adapter from `StrategyEvaluationArtifact` to the shared `EvaluationDecisionScore` contract |
| `exceptions.py` | Domain-level exception types |
| `feature_provider.py` | `FeatureFetcherSet`/`ExternalFeatureProvider` DI contracts + `ExternalFeatureBundle` |
| `indicators.py` | Technical indicator calculations (MACD, RS/RSI) |
| `market_hours.py` | US-equity market-hours / trading-calendar policy (regular hours, holidays, early closes) |
| `promotion_policy.py` | Promotion eligibility rules + `PromotionPolicySettings` policy knobs |
| `returns.py` | Return calculation math |
| `rotation.py` | Rotation schedule parse/dump helpers (`parse_rotation_schedule`, `dump_rotation_schedule`) |
| `book_accounting.py` | Book-level fill accounting math (builds `models.books.BookFillTransition`) |
| `risk_gate.py` | Book risk-gate decision policy (notional/concentration caps) |
| `rotation_policy.py` | Champion/challenger rotation scoring/decision policy (builds `models.rotation` value objects) |
| `strategy_signals.py` | Strategy signal dispatch + `StrategySpec` registry (DI: holds signal callables) |

---

### `src/trading/models/`

Passive data contracts — the **lowest layer**. No business logic, no I/O, and no
imports from `domain`/`services`/`repositories`/`interfaces`/`infrastructure`
(enforced by `scripts/checks/repo/layer_check.py`). Organized into feature subfolders;
each holds one contract per file. The package root and each subpackage re-export
their public types.

| Subfolder | Contracts |
|---|---|
| `accounts/` | `AccountConfig`, `AccountInsert`, `AccountRecord` (implements `Mapping`), `AccountState` |
| `orders/` | `BrokerOrder` (+ `OrderFill`/`OrderStatus`/`OrderType`/`TimeInForce`), `BrokerOrderRecord` |
| `parameters/` | `ParameterEntry`, `ParameterGroup`, `ParameterSourceView` + source vocabulary constants |
| `portfolio/` | `AccountExposure`, `DailyMetricRecord`, `EquitySnapshotRecord`, `PortfolioConcentration`, `PortfolioExposureRollup`, `PortfolioRiskSnapshotRecord`, `SectorConcentration`, `SymbolConcentration` + rollup vocabulary constants |
| `rotation/` | `RotationConfig` (field→column `to_db_dict`; JSON encoding applied in `domain.rotation`), `RotationDecision`, `RotationStrategyMetrics`, `RotationStrategyScore`, `RotationScoreWeights` |
| `strategy/` | `StrategyRecord` |
| `settings/` | `GlobalSettingsRecord` |
| `evaluation/` | `StrategyEvaluationArtifact` + its parts (`EvaluationMeta`, `EvaluationBasicScope`, `EvaluationBacktestEvidence`, `EvaluationPaperLiveEvidence`, `EvaluationWalkForwardEvidence`, `EvaluationConfidence`, `EvaluationDiagnostics`) + version constants |
| `promotion/` | `PromotionAssessment`, `PromotionReviewRecord`, `PromotionReviewEvent` + stage/status/review vocabulary constants |

---

### `src/trading/backtesting/` (bounded context)

Self-contained backtest subsystem with its own layered sub-packages.

| Module | Responsibility |
|---|---|
| `backtest.py` | Backtest execution engine |
| `models.py` | Backtest input/output models |
| `report_models.py` | Backtest report models |
| `domain/` | Backtesting-specific domain logic |
| `repositories/` | Backtest result persistence |
| `services/` | Backtest orchestration services |

---

## Related References

- [service-cookbook.md](../architecture/service-cookbook.md) — task-oriented API reference ("what function do I call to do X?")
- [nav-guide.md](../architecture/nav-guide.md) — "I want to X → look/edit Y" lookup table
- `docs/architecture/architecture-conventions.md` — authoritative import boundary and layering rules
- `docs/reference/backtesting.md`
- `src/trading/backtesting/README.md`
