# Navigation Guide

Type: architecture
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-06-17
Purpose: Task-oriented lookup table — given "I want to X", tells you which file to touch.
Related: [Service Cookbook](service-cookbook.md), [Trading Package Map](../maps/trading-package-map.md), [UI Map](../maps/ui-map.md)

**Start here.** Given a task, this guide tells you which file to touch. Once you have a file, follow the links below to the structural maps if you need surrounding context about that module or package.

The maps and this guide serve different questions:

| Question | Go to |
|---|---|
| "I want to do X — which file do I touch?" | This file |
| "What does every file in `trading/` do?" | [`trading-package-map.md`](../maps/trading-package-map.md) |
| "What does every file in `paper_trading_ui/` do?" | [`ui-map.md`](../maps/ui-map.md) |
| "What does every script do?" | [`scripts-map.md`](../maps/scripts-map.md) |
| "Which docs might be stale after my change?" | [`docs-map.md`](../maps/docs-map.md) |

---

## Trading / Backend

### Persistence (SQL)

| Task | Where |
|---|---|
| Add or modify a SQL query | `trading/repositories/<area>.py` |
| Change the DB schema | `trading/database/db_schema.py` + add a migration in `trading/database/db_migrations.py` |
| Inspect the current schema at runtime | `python -m scripts.data_ops.describe_db_schema` |
| Change DB connection/path config | `trading/database/db_config.py` and `trading/database/db_backend.py` |

### Business Logic

| Task | Where |
|---|---|
| Add/change service-layer orchestration | `trading/services/<domain>/` |
| Add/change pure domain logic or math | `trading/domain/` |
| Change account listing or filtering | `trading/services/accounts/listing.py` |
| Change account snapshot logic | `trading/services/accounts/queries.py` + `trading/repositories/accounts.py` |
| Change auto-trading execution flow | `trading/services/auto_trading/` |
| Change rotation logic | `trading/services/auto_trading/rotation.py` + `trading/domain/rotation.py` |
| Change promotion logic | `trading/services/promotion/` |
| Change evaluation/evidence gathering | `trading/services/evaluation/evidence.py` |
| Change reporting math or presentation | `trading/services/reporting/` |
| Change runtime settings | `trading/services/runtime_settings/` |
| Change runtime throttling | `trading/services/runtime_throttle/enforcement.py` |
| Change sleeve logic (accounting, execution, rotation, risk) | `trading/services/sleeves/` |
| Change sleeve performance queries | `trading/services/performance.py` (flat file — reads daily metrics) |
| Change portfolio risk-snapshot access | `trading/services/risk_snapshots.py` (flat file) |
| Change trade-universe resolution | `trading/services/universe/resolver.py` |

### Configuration

| Task | Where |
|---|---|
| Change an account profile (strategy params, caps) | `trading/config/account_profiles/<profile>.toml` |
| Change trade universe tickers | `trading/config/trade_universes/` |
| Change account-level trade caps | `trading/config/account_trade_caps.json` |

### Models / Data Contracts

| Task | Where |
|---|---|
| Add/change a shared data model (`*Config`, `*Insert`, `*Record`) | `trading/models/` |
| Add/change a domain protocol or DI contract | `trading/domain/broker_connection.py` or `trading/domain/feature_provider.py` |

---

## Runtime Jobs

| Task | Where |
|---|---|
| Add a new daily job | `trading/interfaces/runtime/jobs/daily/` |
| Add a governance review job | `trading/interfaces/runtime/jobs/governance/weekly/` or `monthly/` |
| Add a maintenance job | `trading/interfaces/runtime/jobs/maintenance/` |
| Change daily DAG sequencing | `trading/interfaces/runtime/jobs/daily/paper_trading_dag.py` |
| Install/update job schedules | `trading/interfaces/runtime/jobs/manage_job_schedules.py` |
| Check current job status | `python scripts/check_jobs.py` |

---

## CLI

| Task | Where |
|---|---|
| Add a new CLI command | `trading/interfaces/cli/commands/<area>.py` + matching handler in `trading/interfaces/cli/handlers/` |
| Change CLI dispatch routing | `trading/interfaces/cli/handlers/router.py` |

---

## Backtesting

| Task | Where |
|---|---|
| Change backtesting engine | `trading/backtesting/backtest.py` |
| Change backtest result models | `trading/backtesting/models.py` and `trading/backtesting/report_models.py` |
| Change backtest persistence | `trading/backtesting/repositories/` |
| Change backtesting services | `trading/backtesting/services/` |

---

## Broker Integration

| Task | Where |
|---|---|
| Change broker adapter (paper or live) | `brokers/` (repo root — not inside `trading/`) |
| Change broker DI contract | `trading/domain/broker_connection.py` |

---

## Operator UI — Backend

| Task | Where |
|---|---|
| Add a new API route | `paper_trading_ui/backend/routes/<area>.py` + register in `main.py` |
| Change request/response schema | `paper_trading_ui/backend/schemas/<area>.py` |
| Change what account data the frontend receives | `paper_trading_ui/backend/account_contract/` |
| Change backend service logic | `paper_trading_ui/backend/services/<area>.py` |
| Change backend DB connection | `paper_trading_ui/backend/services/db.py` |
| Change backend config (ports, paths, env) | `paper_trading_ui/backend/config.py` |

---

## Operator UI — Frontend

| Task | Where |
|---|---|
| Add a new page/view | `paper_trading_ui/frontend/src/views/<name>.html` + new feature in `features/` |
| Add or change a feature module | `paper_trading_ui/frontend/src/features/<area>/` |
| Add or change a reusable component | `paper_trading_ui/frontend/src/components/` |
| Add shared utility (HTTP, formatting, DOM) | `paper_trading_ui/frontend/src/lib/` |
| Add/change an API response type | `paper_trading_ui/frontend/src/types/<area>.ts` |
| Change design tokens or base styles | `paper_trading_ui/frontend/src/styles/tokens.css` or `base.css` |
| Update in-app documentation content | `scripts/documentation_ui/api/` or `scripts/documentation_ui/software/`, then run `python -m scripts.documentation_ui.sync` |

---

## Checks and CI

| Task | Where |
|---|---|
| Run quick validation (ruff + layer check) | `python -m scripts.run_checks --profile quick` |
| Run full CI validation | `python -m scripts.run_checks --profile ci` |
| Run tests for a specific area | `python -m scripts.checks.run_suite <path-prefix> --no-cov` |
| Add a new check to CI | `scripts/checks/<new_check>.py` + register in `scripts/checks/ci.py` |
| Change layer/import boundary rules | `scripts/checks/layer_check.py` |
| Check README freshness | `python -m scripts.checks.readme_check --repo-root . --max-age-days 90` |

---

## Tests

Tests mirror the source tree. If you edit `trading/services/reporting/`, the tests are in `tests/trading/services/reporting/`.

| Task | Where |
|---|---|
| Tests for `trading/` | `tests/trading/` (mirrors source path) |
| Tests for `paper_trading_ui/backend/` | `tests/paper_trading_ui/` |
| Tests for `trading/interfaces/` | `tests/trading/interfaces/` |
| Tests for `trading/repositories/` | `tests/trading/repositories/` |

---

## Data Operations

| Task | Where |
|---|---|
| Back up the DB | `python -m scripts.data_ops.backup_db` |
| Export DB to CSV | `python -m scripts.data_ops.export_db_csv` |
| Inspect schema | `python -m scripts.data_ops.describe_db_schema` |
| Launch the UI | `python scripts/launch_ui.py` |

---

## Documentation

| Task | Where |
|---|---|
| Find which docs to update after a code change | [`docs/maps/docs-map.md`](../maps/docs-map.md) — "Goes stale when" column |
| Update in-app documentation content | `scripts/documentation_ui/api/` or `scripts/documentation_ui/software/`, then run `python -m scripts.documentation_ui.sync` |
| Add a new reference note or ADR | `docs/reference/` — use `TEMPLATE.notes.md` or `TEMPLATE.adr.md` |
| Update a runbook | `docs/runbooks/<runbook>.md` |
| Check README freshness | `python -m scripts.checks.readme_check --repo-root . --max-age-days 90` |
