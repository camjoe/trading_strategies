# Scripts

Automation helpers for repository operations and CI/local quality checks.

## Purpose

Define and document repository-level automation commands for validation, data operations, and bot-assisted maintenance workflows.

## Ownership Boundaries

- `scripts/`: repository-level automation and developer workflows (CI smoke, docs checks, exports, launch helpers).
- `trading/interfaces/runtime/jobs/`: trading runtime operations and scheduler tasks (daily trading, health checks, backup registration).
- `trading/interfaces/runtime/data_ops/`: interactive/local database administration and export utilities.
- `trading/database/`: database infrastructure only (schema, backend, config, coercion).

Keep new scripts in the narrowest folder that matches their purpose so runtime operations and maintenance tooling do not drift together.

## Script Catalog

Repository workflow scripts (`scripts/`):

- `run_checks.py`: unified entrypoint for quick and CI-style checks via `--profile quick|ci`.
- `check_jobs.py`: operator tool to inspect daily trading and weekly backup job status; pass `--run-missing` to trigger outstanding jobs.
- `launch_ui.py`: convenience launcher for the paper-trading UI stack.

Documentation page workflows:

Software (`scripts/documentation_ui/software/`):

- `build_registry.py`: rebuilds `docs/reference/software.json` from `requirements-base.txt` and `requirements-dev.txt` while preserving curated package purposes.
- `sync_markdown.py`: syncs `docs/reference/Software.md` from canonical values in `docs/reference/software.json`.
- `sync_ui_docs.py`: syncs the Software card's Key Python Packages tables in the UI docs page from `docs/reference/software.json`.
- `check.py`: standalone sync check that validates requirements, markdown, and UI docs match the canonical software registry.

API Reference (`scripts/documentation_ui/api/`):

- `build_registry.py`: rebuilds `paper_trading_ui/frontend/src/assets/api.json` from FastAPI route decorators while preserving curated endpoint descriptions.
Reference orchestration (`scripts/documentation_ui/`):

- `check.py`: runs Software and API reference checks together.
- `sync.py`: syncs assets/api.json from FastAPI routes and assets/software.json from requirements.

Modular check scripts (`scripts/checks/`):

- `readme_check.py`: standalone README consistency runner. Ignores vendored or local
  virtualenv trees such as `.venv/` and `venv/` so third-party README files do not
  pollute repository documentation audits.
- `mypy_check.py`: standalone mypy runner with default backend/trading targets.
- `pytest_check.py`: standalone pytest runner with passthrough args.
- `quick.py`: fast aggregate checks (README consistency + mypy + pytest, optional frontend).
- `ci.py`: broader CI-shaped checks (docs, installs, ruff, mypy, pytest, frontend).

Data operation scripts (`scripts/data_ops/`):

- `backup_db.py`: convenience wrapper for the canonical backup flow in `trading.interfaces.runtime.data_ops.admin`, writing to `local/db_backups/`.
- `export_db_csv.py`: convenience wrapper for the canonical CSV export flow in `trading.interfaces.runtime.data_ops.csv_export`.
- `export_db_csv_zip.py`: convenience wrapper that packages exported CSV output as ZIP.

**Execution:**

```sh
# Canonical operator-facing entrypoints
python -m trading.interfaces.runtime.data_ops.admin backup-db
python -m trading.interfaces.runtime.data_ops.csv_export

# Convenience wrappers
python -m scripts.data_ops.backup_db
python -m scripts.data_ops.export_db_csv --tables accounts,trades
python -m scripts.data_ops.export_db_csv_zip
```

Treat `trading/interfaces/runtime/data_ops/` as the canonical home for backup,
export, and delete flows. The `scripts.data_ops.*` modules exist as convenience
entrypoints, not as the primary ownership location.

What should not go here:

- Trading runtime schedulers and health checks belong in `trading/interfaces/runtime/jobs/`.
- Interactive/local DB admin workflows belong in `trading/interfaces/runtime/data_ops/`.

If a script changes trading runtime behavior, place it in `trading/interfaces/runtime/jobs/` and document it in `trading/README.md`.

## README Quality

- Default check entrypoint: `run_checks.py`.
- Focused docs quality audit: `scripts.checks.readme_check`.

### Usage

```sh
# Unified top-level entrypoint
python -m scripts.run_checks --profile quick
python -m scripts.run_checks --profile quick --with-frontend
python -m scripts.run_checks --profile quick --with-reference-doc-checks
python -m scripts.run_checks --profile ci
python -m scripts.run_checks --profile ci --skip-frontend
python -m scripts.run_checks --profile ci --with-reference-doc-checks

# Combined reference-doc tools (default user-facing workflow)
python -m scripts.documentation_ui.check
python -m scripts.documentation_ui.sync

# Underlying section workflows (for automation/internal use)
python -m scripts.documentation_ui.software.build_registry
python -m scripts.documentation_ui.software.check
python -m scripts.documentation_ui.api.build_registry
python -m scripts.documentation_ui.api.check

# Modular checks (direct use)
python -m scripts.checks.readme_check
python -m scripts.checks.mypy_check
python -m scripts.checks.pytest_check -- -q
python -m scripts.checks.quick
python -m scripts.checks.ci --skip-frontend

# Focused docs checker
python -m scripts.checks.readme_check
python -m scripts.checks.readme_check --max-age-days 90
python -m scripts.checks.readme_check --enforce-style --enforce-staleness
```
