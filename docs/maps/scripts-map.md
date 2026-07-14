# Scripts Map — `scripts/`

Type: map
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-07-13
Purpose: Inventory of all scripts/ modules — what each does and when to reach for it.
Related: [Docs Map](docs-map.md), [Navigation Guide](../architecture/nav-guide.md)

Dev and ops tooling. Not part of the application runtime — these are invoked by developers and CI.

---

## Check Runner (`scripts/run_checks.py`)

Entry point for aggregate validation checks. Run via `python -m scripts.run_checks <command>`.

| Command | When to use | What it runs |
|---|---|---|
| `docs` | Documentation drift checks | README consistency, maps, links, `-m` refs, DB schema docs, doc headers, doc naming, generated in-app doc assets |
| `repo` | Repository safety and structure checks | Layer boundaries, skills drift, live-trading safety, path safety, secret hygiene |
| `python` | Python quality gate | Python conventions, public API test-evidence advisory, function complexity advisory, ruff, mypy, pytest or targeted suites |
| `quick` | Day-to-day, before committing | `repo` + `python` (optional frontend and targeted suites) |
| `ci` | CI-shaped smoke before a PR | `docs` + `repo` + `python` + frontend lint/typecheck/tests |

---

## Fix Runner (`scripts/fix_checks.py`)

Applies deterministic, behavior-preserving cleanup before re-running checks.

| Command | What it fixes |
|---|---|
| `python -m scripts.fix_checks` | Runs `ruff check --fix`, `ruff format`, generated API/software reference-doc asset sync, and docs drift fixes (`scripts/fixes/`) |
| `python -m scripts.fix_checks <path> [...]` | Runs the same fixes with the Python steps limited to selected paths |

---

## Fixes (`scripts/fixes/`)

Fix counterparts of checks under `scripts/checks/`. Each fixer applies only the mechanical
half of its paired check's findings and reports anything that still needs human prose.

| Module | Responsibility |
|---|---|
| `db_schema_fix.py` | Sync the db-schema.md Quick Reference with the live schema: remove stale rows, append TODO scaffold rows, refresh the table count (pairs with `scripts/checks/docs/db_schema_check.py`) |
| `maps_fix.py` | Remove structural-map table rows whose files no longer exist; rows mixing live and stale paths are reported for manual edit (pairs with `scripts/checks/docs/maps_check.py`) |

---

## Checks (`scripts/checks/`)

Root files are orchestration and shared helpers. Concrete checks live under `docs/`, `repo/`, or `python/`.

| Module | Responsibility |
|---|---|
| `quick.py` | Quick aggregate: repository checks + Python checks, with optional frontend |
| `ci.py` | CI aggregate: docs + repo + Python + frontend |
| `run_suite.py` | Targeted suite runner — run tests for a specific path prefix (e.g. `src/trading/services/reporting`) |
| `_runner.py` | Internal shared check-runner helpers for steps and tool executable resolution |

| Package | Checks |
|---|---|
| `scripts/checks/docs/` | `scripts/checks/docs/docs_check.py`, `scripts/checks/docs/readme_check.py`, `scripts/checks/docs/maps_check.py`, `scripts/checks/docs/link_check.py`, `scripts/checks/docs/module_ref_check.py`, `scripts/checks/docs/db_schema_check.py`, `scripts/checks/docs/doc_header_check.py`, `scripts/checks/docs/doc_naming_check.py` |
| `scripts/checks/repo/` | `scripts/checks/repo/repo_check.py`, `scripts/checks/repo/layer_check.py`, `scripts/checks/repo/skills_check.py`, `scripts/checks/repo/live_safety_check.py`, `scripts/checks/repo/path_safety_check.py`, `scripts/checks/repo/secret_hygiene_check.py`, `scripts/checks/repo/review_scope_check.py` |
| `scripts/checks/python/` | `scripts/checks/python/python_check.py`, `scripts/checks/python/python_conventions_check.py`, `scripts/checks/python/public_api_test_evidence_check.py`, `scripts/checks/python/function_complexity_check.py`, `scripts/checks/python/ruff_check.py`, `scripts/checks/python/mypy_check.py`, `scripts/checks/python/pytest_check.py` |

**Run a targeted suite:**
```
python -m scripts.checks.run_suite src/trading/services/reporting --no-cov
```

**Run checks:**
```
python -m scripts.run_checks quick
python -m scripts.run_checks docs
python -m scripts.run_checks repo
python -m scripts.run_checks python
python -m scripts.run_checks ci
```

**Deterministic pre-PR gate (no AI, no tokens):**
```
python -m scripts.run_checks repo
python -m scripts.run_checks python --base main --no-cov
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

Tools for syncing the in-app documentation assets (`apps/paper_trading_web/frontend/src/assets/`).

| Module | Responsibility |
|---|---|
| `sync.py` | Syncs documentation source content to frontend static JSON assets |
| `check.py` | Validates documentation registry completeness |
| `registry_utils.py` | Shared registry lookup utilities |
| `finance/` | Finance and market terminology documentation source sync |
| `api/` | API documentation source content |
| `software/` | Software/architecture documentation source content |

---

## Root Scripts

| Script | Responsibility |
|---|---|
| `run_checks.py` | Check runner entry point (see above) |
| `fix_checks.py` | Deterministic local auto-fix entry point: Python lint/format drift, generated API/software reference-doc assets, and docs drift fixers under `scripts/fixes/` |
| `launch_ui.py` | Launch the paper trading UI (backend + frontend dev server) |
| `ui_config.py` | UI launch configuration (ports, paths) |
| `screenshot_ui.py` | Capture UI screenshots (used for docs/reference) |
| `check_jobs.py` | Check scheduled job status (installed OS-level schedules) |
| `ibkr_web_api_smoke_test.py` | IBKR Web API connectivity smoke test |

---

## Related References

- [`docs/architecture/nav-guide.md`](../architecture/nav-guide.md) — When to use which script
- [`docs/maps/trading-package-map.md`](trading-package-map.md) — Layer rules enforced by `layer_check.py`
