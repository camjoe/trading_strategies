# Scripts Map — `scripts/`

Type: map
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-06-19
Purpose: Inventory of all scripts/ modules — what each does and when to reach for it.
Related: [Docs Map](docs-map.md), [Navigation Guide](../architecture/nav-guide.md)

Dev and ops tooling. Not part of the application runtime — these are invoked by developers and CI.

---

## Check Runner (`scripts/run_checks.py`)

Entry point for all validation checks. Run via `python -m scripts.run_checks --profile <name>`.

| Profile | What it runs |
|---|---|
| `quick` | `ruff` + `layer_check` |
| `ci` | `ruff` + `layer_check` + `mypy` + `pytest` |

---

## Checks (`scripts/checks/`)

Individual check modules. Each is also usable directly.

| Module | Responsibility |
|---|---|
| `quick.py` | Quick profile definition (ruff + layer_check) |
| `ci.py` | CI profile definition (all checks) |
| `ruff_check.py` | Ruff linting runner |
| `layer_check.py` | Import boundary enforcement — verifies layering rules (services → no database imports, etc.) |
| `mypy_check.py` | Mypy type-check runner (`trading/` + `paper_trading_ui/backend/`) |
| `pytest_check.py` | Pytest runner (full suite) |
| `run_suite.py` | Targeted suite runner — run tests for a specific path prefix (e.g. `trading/services/reporting`) |
| `readme_check.py` | README freshness checker — flags docs older than a configurable age threshold |
| `maps_check.py` | Map drift checker — flags modules on disk missing from (or stale in) the structural maps; advisory |
| `link_check.py` | Doc link checker — flags broken markdown links and repo-root path references in docs; advisory |
| `db_schema_check.py` | DB schema drift checker — verifies db-schema.md's Quick Reference covers every live table; advisory |
| `pr_ready.py` | Deterministic pre-PR gate — runs layer check, ruff, mypy, and branch-targeted tests in order (fail-fast) |
| `shared.py` | Shared utilities for check modules (result types, formatting) |

**Run a targeted suite:**
```
python -m scripts.checks.run_suite trading/services/reporting --no-cov
```

**Run checks:**
```
python -m scripts.run_checks --profile quick
python -m scripts.run_checks --profile ci
```

---

## Data Ops (`scripts/data_ops/`)

One-off data operations. Safe to run on the live DB when noted.

| Module | Responsibility |
|---|---|
| `backup_db.py` | SQLite DB backup — copies the live DB to a timestamped backup file |
| `describe_db_schema.py` | Print current DB schema (tables, columns, types); use `--source live` for the live DB |
| `export_db_csv.py` | Export all DB tables to individual CSV files |
| `export_db_csv_zip.py` | Export all DB tables to a single zipped CSV archive |

**Inspect current schema:**
```
python -m scripts.data_ops.describe_db_schema
python -m scripts.data_ops.describe_db_schema --source live
```

---

## Documentation UI (`scripts/documentation_ui/`)

Tools for syncing the in-app documentation assets (`paper_trading_ui/frontend/src/assets/`).

| Module | Responsibility |
|---|---|
| `sync.py` | Syncs documentation source content to frontend static JSON assets |
| `check.py` | Validates documentation registry completeness |
| `registry_utils.py` | Shared registry lookup utilities |
| `api/` | API documentation source content |
| `software/` | Software/architecture documentation source content |

---

## Root Scripts

| Script | Responsibility |
|---|---|
| `run_checks.py` | Check runner entry point (see above) |
| `launch_ui.py` | Launch the paper trading UI (backend + frontend dev server) |
| `ui_config.py` | UI launch configuration (ports, paths) |
| `screenshot_ui.py` | Capture UI screenshots (used for docs/reference) |
| `check_jobs.py` | Check scheduled job status (installed OS-level schedules) |
| `ibkr_web_api_smoke_test.py` | IBKR Web API connectivity smoke test |

---

## Related References

- [`docs/architecture/nav-guide.md`](../architecture/nav-guide.md) — When to use which script
- [`docs/maps/trading-package-map.md`](trading-package-map.md) — Layer rules enforced by `layer_check.py`
