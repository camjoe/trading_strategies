# Scripts

Automation helpers for repository operations and CI/local quality checks.

## Ownership Boundaries

- `scripts/`: repository-level automation and developer workflows (CI smoke, docs checks, exports, launch helpers).
- `trading/scripts/`: trading runtime operations and scheduler tasks (daily trading, health checks, backup registration).
- `dev_tools/`: interactive/local database administration utilities.

Keep new scripts in the narrowest folder that matches their purpose so runtime operations and maintenance tooling do not drift together.

## Script Catalog

Repository workflow scripts (`scripts/`):

- `check_docs_freshness.py`: validates docs updates for changed areas.
- `ci_smoke.py`: aggregate smoke checks for docs, Python, tests, and optional frontend.
- `prepare_cleanup_bot_run.py`: builds cleanup-agent prompts from repo change scope.
- `launch_ui.py`: convenience launcher for the paper-trading UI stack.

Data operation scripts (`scripts/data_ops/`):

- `backup_db.py`: retention-oriented backup helper writing to `local/db_backups/`.
- `export_db_csv.py`: table export to timestamped CSV directory.
- `export_db_csv_zip.py`: CSV export with ZIP packaging.

**Execution:**

```powershell
# Backup database
python -m scripts.data_ops.backup_db

# Export selected tables to CSV
python -m scripts.data_ops.export_db_csv --tables accounts,trades

# Export all tables and create ZIP archive
python -m scripts.data_ops.export_db_csv_zip
```

What should not go here:

- Trading runtime schedulers and health checks belong in `trading/scripts/`.
- Interactive/local DB admin workflows belong in `dev_tools/`.

If a script changes trading runtime behavior, place it in `trading/scripts/` and document it in `trading/README.md`.

## Docs Freshness

- `check_docs_freshness.py`: checks changed areas for missing documentation updates.
- `ci_smoke.py`: runs docs freshness, Python quality checks, tests, and optional frontend checks.

### Usage

```powershell
python -m scripts.check_docs_freshness
python -m scripts.check_docs_freshness --base-ref origin/main --head-ref HEAD
python -m scripts.ci_smoke --skip-frontend
```

## Cleanup Bot Prompt Prep

- `prepare_cleanup_bot_run.py`: builds a copy/paste-ready prompt for cleanup agents.

### Usage

```powershell
# Python bot on uncommitted files
python -m scripts.prepare_cleanup_bot_run --bot python --scope uncommitted

# Frontend bot on files changed since origin/main
python -m scripts.prepare_cleanup_bot_run --bot frontend --scope recent --base-ref origin/main

# Cross-stack bot on all relevant files
python -m scripts.prepare_cleanup_bot_run --bot both --scope all

# Project structure bot on recent changes
python -m scripts.prepare_cleanup_bot_run --bot structure --scope recent --base-ref origin/main
```

Optional JSON output:

```powershell
python -m scripts.prepare_cleanup_bot_run --bot both --scope uncommitted --json
```
