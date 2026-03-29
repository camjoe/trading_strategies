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
- `launch_ui.py`: convenience launcher for the paper-trading UI stack.

Term registry scripts (`scripts/terms/`):

- `build_registry.py`: rebuilds `docs/reference/term_definitions.json` from Glossary + UI docs while preserving per-term visibility (`both`, `glossary`, `ui`).
- `sync_glossary.py`: syncs Glossary definitions from canonical values in `docs/reference/term_definitions.json`.
- `sync_ui_docs.py`: syncs the Financial & Market Knowledge tables in the UI docs page from canonical values in `docs/reference/term_definitions.json`.
- `check.py`: standalone sync check that validates Glossary/UI docs match the canonical term registry.

Modular check scripts (`scripts/checks/`):

- `readme_check.py`: standalone README consistency runner.
- `mypy_check.py`: standalone mypy runner with default backend/trading targets.
- `pytest_check.py`: standalone pytest runner with passthrough args.
- `quick.py`: fast aggregate checks (README consistency + mypy + pytest, optional frontend).
- `ci.py`: broader CI-shaped checks (docs, installs, ruff, mypy, pytest, frontend).

Data operation scripts (`scripts/data_ops/`):

- `backup_db.py`: retention-oriented backup helper writing to `local/db_backups/`.
- `export_db_csv.py`: table export to timestamped CSV directory.
- `export_db_csv_zip.py`: CSV export with ZIP packaging.

**Execution:**

```sh
# Backup database
python -m scripts.data_ops.backup_db

# Export selected tables to CSV
python -m scripts.data_ops.export_db_csv --tables accounts,trades

# Export all tables and create ZIP archive
python -m scripts.data_ops.export_db_csv_zip
```

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
python -m scripts.run_checks --profile quick --with-term-definitions-check
python -m scripts.run_checks --profile ci
python -m scripts.run_checks --profile ci --skip-frontend
python -m scripts.run_checks --profile ci --with-term-definitions-check

# Term registry tools
python -m scripts.terms.build_registry
python -m scripts.terms.sync_glossary
python -m scripts.terms.sync_ui_docs
python -m scripts.terms.check

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


