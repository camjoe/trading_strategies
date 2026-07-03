# Scripts Map — `scripts/`

Type: map
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-07-02
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
| `python` | Python quality gate | Python conventions, ruff, mypy, pytest or targeted suites |
| `quick` | Day-to-day, before committing | `repo` + `python` (optional frontend and targeted suites) |
| `ci` | CI-shaped smoke before a PR | `docs` + `repo` + `python` + frontend lint/typecheck/tests |

---

## Fix Runner (`scripts/fix_checks.py`)

Applies deterministic, behavior-preserving cleanup before re-running checks.

| Command | What it fixes |
|---|---|
| `python -m scripts.fix_checks` | Runs `ruff check --fix`, `ruff format`, and generated API/software reference-doc asset sync |
| `python -m scripts.fix_checks <path> [...]` | Runs the same fixes on selected Python paths, plus generated reference-doc asset sync |
| `python -m scripts.fix_checks --skip-reference-doc-sync` | Runs Python lint/format fixes without generated reference-doc asset sync |

---

## Checks (`scripts/checks/`)

Individual check modules. Each is also usable directly.

| Module | Responsibility |
|---|---|
| `quick.py` | Quick aggregate: repository checks + Python checks, with optional frontend |
| `ci.py` | CI aggregate: docs + repo + Python + frontend |
| `docs_check.py` | Human-facing aggregate documentation check: README, maps, links, `-m` refs, DB schema, doc headers, doc naming, and generated in-app doc assets |
| `repo_check.py` | Human-facing aggregate repository check: layer boundaries, skills drift, live-trading safety, path safety, and secret hygiene |
| `python_check.py` | Human-facing aggregate Python check: conventions, ruff, mypy, and pytest or targeted suites |
| `ruff_check.py` | Ruff linting runner |
| `layer_check.py` | Import/path boundary enforcement — verifies layering, SDK ownership, and retired package-name rules |
| `path_safety_check.py` | Cross-platform path safety checker — flags clear `os.path.join`, `os.sep`, and hardcoded backslash path hazards |
| `python_conventions_check.py` | Python convention checker — verifies future annotations and public function return annotations in production/tooling modules |
| `secret_hygiene_check.py` | Secret hygiene checker — flags committed literal credentials in source/config files |
| `mypy_check.py` | Mypy type-check runner (`src/trading/` + `apps/paper_trading_web/backend/`) |
| `pytest_check.py` | Pytest runner (full suite) |
| `run_suite.py` | Targeted suite runner — run tests for a specific path prefix (e.g. `src/trading/services/reporting`) |
| `readme_check.py` | README freshness checker — flags docs older than a configurable age threshold |
| `maps_check.py` | Map drift checker — flags modules on disk missing from (or stale in) the structural maps; advisory |
| `link_check.py` | Doc link checker — flags broken markdown links and repo-root path references in docs; advisory |
| `module_ref_check.py` | Doc `-m` module-reference checker — flags `python -m <module>` invocations in docs whose first-party module does not resolve; advisory |
| `db_schema_check.py` | DB schema drift checker — verifies db-schema.md's Quick Reference covers every live table; advisory |
| `doc_header_check.py` | Doc header checker — required fields + Type/Status vocabulary across `docs/` per docs-authoring.md; enforced in CI profile |
| `doc_naming_check.py` | Doc filename checker — kebab-case docs names + sequential ADR numbering per naming.md; enforced in CI profile |
| `live_safety_check.py` | Live-trading safety checker — blocks automated `live_trading_enabled = 1` code paths |
| `skills_check.py` | Skills drift checker — AGENTS.md skill inventory ↔ `.ai/skills/` folders + SKILL.md frontmatter completeness; enforced in CI profile |
| `pr_ready.py` | Deterministic pre-PR gate — runs layer check, ruff, mypy, and branch-targeted tests in order (fail-fast) |
| `_runner.py` | Internal shared check-runner helpers for steps and tool executable resolution |
| `shared.py` | Compatibility re-export for older imports of check-runner helpers |

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
python -m scripts.run_checks python --suite scripts/test_run_checks.py --no-cov
python -m scripts.run_checks ci
```

**Deterministic pre-PR gate (no AI, no tokens):**
```
python -m scripts.checks.pr_ready
python -m scripts.checks.pr_ready --base main --no-cov
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
| `finance/` | Finance/strategy documentation source content |

---

## Root Scripts

| Script | Responsibility |
|---|---|
| `run_checks.py` | Check runner entry point (see above) |
| `fix_checks.py` | Deterministic local auto-fix entry point for Python lint/format drift and generated API/software reference-doc assets |
| `launch_ui.py` | Launch the paper trading UI (backend + frontend dev server) |
| `ui_config.py` | UI launch configuration (ports, paths) |
| `screenshot_ui.py` | Capture UI screenshots (used for docs/reference) |
| `check_jobs.py` | Check scheduled job status (installed OS-level schedules) |
| `ibkr_web_api_smoke_test.py` | IBKR Web API connectivity smoke test |

---

## Related References

- [`docs/architecture/nav-guide.md`](../architecture/nav-guide.md) — When to use which script
- [`docs/maps/trading-package-map.md`](trading-package-map.md) — Layer rules enforced by `layer_check.py`
