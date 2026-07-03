# Scripts

Automation helpers for repository operations and CI/local quality checks.

## Purpose

Define and document repository-level automation commands for validation, data operations, and bot-assisted maintenance workflows.

## Ownership Boundaries

- `scripts/`: repository-level automation and developer workflows (CI smoke, docs checks, exports, launch helpers).
- `src/trading/interfaces/runtime/jobs/`: trading runtime operations and scheduler tasks (daily trading, health checks, backup registration).
- `src/trading/interfaces/runtime/data_ops/`: interactive/local database administration and export utilities.
- `src/infrastructure/database/`: database infrastructure only (schema, backend, config, coercion).

Keep new scripts in the narrowest folder that matches their purpose so runtime operations and maintenance tooling do not drift together.

## Quick Start

Run these from the repository root:

```sh
python -m scripts.run_checks quick
python -m scripts.fix_checks
python -m scripts.checks.readme_check --max-age-days 90
python -m scripts.documentation_ui.check
```

## Script Catalog

For the complete inventory of every script and when to reach for it, see
[`docs/maps/scripts-map.md`](../docs/maps/scripts-map.md); for task-oriented "I want to X → run Y"
lookup, see [`docs/architecture/nav-guide.md`](../docs/architecture/nav-guide.md). This README
highlights the most common entrypoints.

Repository workflow scripts (`scripts/`):

- `run_checks.py`: unified entrypoint for aggregate checks (`docs`, `repo`, `python`, `quick`, `ci`).
- `fix_checks.py`: deterministic local auto-fix command for safe mechanical drift (`ruff check --fix`, `ruff format`, generated API/software reference-doc asset sync).
- `check_jobs.py`: operator tool to inspect daily trading and weekly backup job status; pass `--run-missing` to trigger outstanding jobs.
- `launch_ui.py`: convenience launcher for the paper-trading UI stack.
- `ibkr_web_api_smoke_test.py`: manual IBKR Client Portal Gateway smoke test. Keep detailed setup, safety notes, and usage in `docs/reference/broker-integration.md`; this README only lists the entrypoint.

Documentation page workflows:

Finance (`scripts/documentation_ui/finance/`):

- `build_registry.py`: rebuilds `apps/paper_trading_web/frontend/src/assets/finance.json` from `docs/reference/financial-market-knowledge.md`.
- `check.py`: standalone sync check that validates the finance UI asset matches the canonical reference doc.

Software (`scripts/documentation_ui/software/`):

- `build_registry.py`: rebuilds `apps/paper_trading_web/frontend/src/assets/software.json` from `requirements-base.txt` and `requirements-dev.txt` while preserving curated package purposes.
- `check.py`: standalone sync check that validates requirements and UI docs match the canonical software registry.

API Reference (`scripts/documentation_ui/api/`):

- `build_registry.py`: rebuilds `apps/paper_trading_web/frontend/src/assets/api.json` from FastAPI route decorators while preserving curated endpoint descriptions.

Reference orchestration (`scripts/documentation_ui/`):

- `check.py`: runs Finance, Software, and API reference checks together.
- `sync.py`: syncs assets/finance.json from the reference doc, assets/api.json from FastAPI routes, and assets/software.json from requirements.

Modular check scripts (`scripts/checks/`):

- `docs_check.py`: human-facing aggregate runner for documentation and documentation-drift checks.
- `repo_check.py`: human-facing aggregate runner for repository safety and structure checks.
- `python_check.py`: human-facing aggregate runner for Python conventions, lint, types, and tests.
- `readme_check.py`: standalone README consistency runner. Ignores vendored or local
  virtualenv trees such as `.venv/` and `venv/` so third-party README files do not
  pollute repository documentation audits.
- `mypy_check.py`: standalone mypy runner with default backend/trading targets.
- `pytest_check.py`: standalone pytest runner with passthrough args.
- `quick.py`: fast aggregate checks (README consistency + layer check + ruff + mypy + pytest, optional frontend).
- `ci.py`: broader CI-shaped checks (documentation drift, repo safety, dependency installs, ruff, mypy, pytest, frontend).
- `_runner.py`: internal check-runner helpers for step execution and tool resolution.
- `shared.py`: compatibility re-export for older imports of check-runner helpers.

Data operation scripts (`scripts/data_ops/`):

- `backup_db.py`: convenience wrapper for the canonical backup flow in `trading.interfaces.runtime.data_ops.admin`, writing to `local/db_backups/`.
- `describe_db_schema.py`: prints the current database schema from either an in-memory database initialized from `schema.py` + migrations or the configured live SQLite database.
- `export_db_csv.py`: convenience wrapper for the canonical CSV export flow in `trading.interfaces.runtime.data_ops.csv_export`.
- `export_db_csv_zip.py`: convenience wrapper that packages exported CSV output as ZIP.

**Execution:**

```sh
# Canonical operator-facing entrypoints
python -m trading.interfaces.runtime.data_ops.admin backup-db
python -m trading.interfaces.runtime.data_ops.csv_export

# Convenience wrappers
python -m scripts.data_ops.backup_db
python -m scripts.data_ops.describe_db_schema
python -m scripts.data_ops.describe_db_schema --source live
python -m scripts.data_ops.export_db_csv --tables accounts,trades
python -m scripts.data_ops.export_db_csv_zip
```

Treat `src/trading/interfaces/runtime/data_ops/` as the canonical home for backup,
export, and delete flows. The `scripts.data_ops.*` modules exist as convenience
entrypoints, not as the primary ownership location.

What should not go here:

- Trading runtime schedulers and health checks belong in `src/trading/interfaces/runtime/jobs/`.
- Interactive/local DB admin workflows belong in `src/trading/interfaces/runtime/data_ops/`.

If a script changes trading runtime behavior, place it in `src/trading/interfaces/runtime/jobs/` and document it in `src/trading/README.md`.

## README Quality

- Default check entrypoint: `run_checks.py`.
- Focused docs quality audit: `scripts.checks.readme_check`.

### Usage

```sh
# Unified top-level entrypoint
python -m scripts.run_checks
python -m scripts.run_checks docs
python -m scripts.run_checks repo
python -m scripts.run_checks python
python -m scripts.run_checks python --suite scripts/test_run_checks.py --no-cov
python -m scripts.run_checks quick
python -m scripts.run_checks quick --with-frontend
python -m scripts.run_checks ci
python -m scripts.run_checks ci --skip-frontend
python -m scripts.fix_checks
python -m scripts.fix_checks --skip-reference-doc-sync

# Manual IBKR Web API smoke test
# See docs/reference/broker-integration.md for private config setup,
# paper-account-only guidance, and the full operator workflow.
python -m scripts.ibkr_web_api_smoke_test
python -m scripts.ibkr_web_api_smoke_test --paper-order-check --paper-order-symbol AAPL --paper-order-limit-price 1.00

# Combined reference-doc tools (default user-facing workflow)
python -m scripts.documentation_ui.check
python -m scripts.documentation_ui.sync

# Underlying section workflows (for automation/internal use)
python -m scripts.documentation_ui.finance.build_registry
python -m scripts.documentation_ui.finance.check
python -m scripts.documentation_ui.software.build_registry
python -m scripts.documentation_ui.software.check
python -m scripts.documentation_ui.api.build_registry
python -m scripts.documentation_ui.api.check

# Modular checks (direct use)
python -m scripts.checks.mypy_check
python -m scripts.checks.pytest_check -- -q
python -m scripts.checks.docs_check
python -m scripts.checks.repo_check
python -m scripts.checks.python_check
python -m scripts.checks.quick
python -m scripts.checks.ci --skip-frontend

# Focused docs checker
python -m scripts.checks.readme_check --max-age-days 90
python -m scripts.checks.readme_check --enforce-style --enforce-staleness
```
