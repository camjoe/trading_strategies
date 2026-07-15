# Navigation Guide

Type: architecture
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-07-13
Purpose: Task-oriented lookup table — given "I want to X", tells you which file to touch.
Related: [Service Cookbook](service-cookbook.md), [Trading Package Map](../maps/trading-package-map.md), [UI Map](../maps/ui-map.md)

**Start here.** Given a task, this guide tells you which file to touch. Once you have a file, follow the links below to the structural maps if you need surrounding context about that module or package.

The maps and this guide serve different questions:

| Question | Go to |
|---|---|
| "I want to do X — which file do I touch?" | This file |
| "What does every file in `src/trading/` do?" | [`trading-package-map.md`](../maps/trading-package-map.md) |
| "What does every file in `apps/paper_trading_web/` do?" | [`ui-map.md`](../maps/ui-map.md) |
| "What does every script do?" | [`scripts-map.md`](../maps/scripts-map.md) |
| "Which docs might be stale after my change?" | [`docs-map.md`](../maps/docs-map.md) |

---

## Trading / Backend

### Persistence (SQL)

| Task | Where |
|---|---|
| Add or modify a SQL query | `src/trading/repositories/<area>.py` |
| Change the DB schema | New numbered revision in `src/infrastructure/database/alembic/versions/` + bump `schema_version.EXPECTED_HEAD_REVISION` (use the `db-migration` skill) |
| Inspect the current schema at runtime | `python -m scripts.data_ops.describe_db_schema` |
| Change DB connection/path config | `src/infrastructure/database/config.py` and `src/infrastructure/database/backend.py` |

### Business Logic

| Task | Where |
|---|---|
| Add/change service-layer orchestration | `src/trading/services/<domain>/` |
| Add/change pure domain logic or math | `src/trading/domain/` |
| Change account listing or filtering | `src/trading/services/accounts/listing.py` |
| Change account snapshot logic | `src/trading/services/accounts/queries.py` + `src/trading/repositories/accounts.py` |
| Change auto-trading execution flow | `src/trading/services/auto_trading/` |
| Change shared book order submission, fill handling, reconciliation, or pre-submit gates | `src/trading/services/execution/` |
| Change rotation logic | `src/trading/services/books/rotation.py` + `src/trading/domain/rotation.py` |
| Change promotion logic | `src/trading/services/promotion/` |
| Change evaluation/evidence gathering | `src/trading/services/evaluation/evidence.py` |
| Change strategy catalog seeding, resolution, variants, configuration, or freezing | `src/trading/services/strategy_catalog/` |
| Change reporting math or presentation | `src/trading/services/reporting/` |
| Change operational settings | `src/trading/services/operational_settings/` |
| Change the unified parameter view or its edit workflows | `src/trading/services/parameters/` |
| Change per-book rotation policy resolution | `src/trading/services/books/rotation.py` (`resolve_rotation_policy_config`) |
| Change trade throttling | `src/trading/services/operational_settings/enforcement.py` |
| Change book logic (accounting, execution, rotation, risk) | `src/trading/services/books/` |
| Change book performance queries | `src/trading/services/analysis/performance.py` (reads daily metrics) |
| Change portfolio risk-snapshot access | `src/trading/services/analysis/risk_snapshots.py` |
| Change the cross-account exposure rollup | `src/trading/services/analysis/exposure.py` (payload) + `src/trading/services/reporting/exposure.py` (printed view) |
| Change cross-account concentration (symbol/sector) | `src/trading/services/analysis/concentration.py` (payload) + `src/trading/services/reporting/concentration.py` (printed view) |
| Change trade-universe resolution | `src/trading/services/universe/resolver.py` |
| Change stale-backtest target discovery/remediation support | `src/trading/services/backtesting/` |
| Change IBKR paper monitor operator/dashboard queries or artifacts | `src/trading/services/ibkr_paper_monitor/` |

### Configuration

| Task | Where |
|---|---|
| Change an account profile (strategy params, caps) | `src/infrastructure/config/account_profiles/<profile>.json` |
| Change trade universe tickers | `src/infrastructure/config/trade_universes/` |
| Change account-level trade caps | `src/infrastructure/config/account_trade_caps.json` |

### Models / Data Contracts

| Task | Where |
|---|---|
| Add/change a shared data model (`*Config`, `*Insert`, `*Record`) | `src/trading/models/` |
| Add/change a domain protocol or DI contract | `src/trading/domain/broker_connection.py` or `src/trading/domain/feature_provider.py` |

---

## Runtime Jobs

| Task | Where |
|---|---|
| Add a new daily job | `src/trading/interfaces/runtime/jobs/daily/` |
| Add a governance review job | `src/trading/interfaces/runtime/jobs/governance/weekly/` or `monthly/` |
| Add a maintenance job | `src/trading/interfaces/runtime/jobs/maintenance/` |
| Change daily DAG sequencing | `src/trading/interfaces/runtime/jobs/daily/paper_trading/dag.py` |
| Install/update job schedules | `src/trading/interfaces/runtime/scheduling/manage_job_schedules.py` |
| Check current job status | `python -m scripts.check_jobs` |

---

## CLI

| Task | Where |
|---|---|
| Add a new CLI command | `src/trading/interfaces/cli/commands/<area>.py` + matching handler in `src/trading/interfaces/cli/handlers/` |
| Change CLI dispatch routing | `src/trading/interfaces/cli/handlers/router.py` |

---

## Backtesting

| Task | Where |
|---|---|
| Change backtesting engine | `src/trading/backtesting/backtest.py` |
| Change backtest result models | `src/trading/backtesting/models.py` and `src/trading/backtesting/report_models.py` |
| Change backtest persistence | `src/trading/backtesting/repositories/` |
| Change backtesting services | `src/trading/backtesting/services/` |

---

## Broker Integration

| Task | Where |
|---|---|
| Change broker adapter (paper or live) | `src/infrastructure/brokers/` (repo root — not inside `src/trading/`) |
| Change broker DI contract | `src/trading/domain/broker_connection.py` |

---

## Operator UI — Backend

| Task | Where |
|---|---|
| Add a new API route | `apps/paper_trading_web/backend/routes/<area>.py` + register in `main.py` |
| Change request/response schema | `apps/paper_trading_web/backend/schemas/<area>.py` |
| Change what account data the frontend receives | `apps/paper_trading_web/backend/account_contract/` |
| Change backend service logic | `apps/paper_trading_web/backend/services/<area>.py` |
| Change backend DB connection | `apps/paper_trading_web/backend/services/db.py` |
| Change backend config (ports, paths, env) | `apps/paper_trading_web/backend/config.py` |

---

## Operator UI — Frontend

| Task | Where |
|---|---|
| Add a new page/view | `apps/paper_trading_web/frontend/src/views/<name>.html` + new feature in `apps/paper_trading_web/frontend/src/features/<area>/` |
| Add or change a feature module | `apps/paper_trading_web/frontend/src/features/<area>/` |
| Add or change a reusable component | `apps/paper_trading_web/frontend/src/components/` |
| Add shared utility (HTTP, formatting, DOM) | `apps/paper_trading_web/frontend/src/lib/` |
| Add/change an API response type | `apps/paper_trading_web/frontend/src/types/<area>.ts` |
| Change design tokens or base styles | `apps/paper_trading_web/frontend/src/styles/tokens.css` or `base.css` |

---

## Checks and CI

| Task | Where |
|---|---|
| Run quick local validation | `python -m scripts.run_checks quick` |
| Run documentation validation | `python -m scripts.run_checks docs` |
| Run repository safety and structure validation | `python -m scripts.run_checks repo` |
| Run Python lint/type/test validation | `python -m scripts.run_checks python` |
| Run full CI validation | `python -m scripts.run_checks ci` |
| Run tests for a specific area | `python -m scripts.checks.run_suite <path-prefix> --no-cov` |
| Add a new check to CI | `scripts/checks/<new_check>.py` + register in `scripts/checks/ci.py` |
| Change layer/import boundary rules | `scripts/checks/repo/layer_check.py` |
| Check README freshness only | `python -m scripts.checks.docs.readme_check --repo-root . --max-age-days 90` |

---

## Tests

Tests mirror the source tree. If you edit `src/trading/services/reporting/`, the tests are in `tests/src/trading/services/reporting/`.

| Task | Where |
|---|---|
| Tests for `src/trading/` | `tests/src/trading/` (mirrors source path) |
| Tests for `apps/paper_trading_web/backend/` | `tests/apps/paper_trading_web/` |
| Tests for `src/trading/interfaces/` | `tests/src/trading/interfaces/` |
| Tests for `src/trading/repositories/` | `tests/src/trading/repositories/` |

---

## Data Operations

| Task | Where |
|---|---|
| Back up the DB | `python -m scripts.data_ops.backup_db` |
| Export DB to CSV | `python -m scripts.data_ops.export_db_csv` |
| Inspect schema | `python -m scripts.data_ops.describe_db_schema` |
| Launch the UI | `python -m scripts.launch_ui` |

---

## Documentation

| Task | Where |
|---|---|
| Find which docs to update after a code change | [`docs/maps/docs-map.md`](../maps/docs-map.md) — "Goes stale when" column |
| Update finance/market terms in the in-app docs | `docs/reference/financial-market-knowledge.md`, then run `python -m scripts.documentation_ui.sync` |
| Update API or software reference content in the in-app docs | `scripts/documentation_ui/api/` or `scripts/documentation_ui/software/`, then run `python -m scripts.documentation_ui.sync` |
| Add a new reference note or ADR | `docs/reference/` — use the inline reference-note template in `docs/conventions/docs-authoring.md` or `docs/adr/TEMPLATE.adr.md` |
| Update a runbook | `docs/runbooks/<runbook>.md` |
| Check README freshness | `python -m scripts.checks.docs.readme_check --repo-root . --max-age-days 90` |
