# Scripts Map — `scripts/`

Type: map
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-10-15
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

## Forge Interface (`scripts/forge/`)

Platform-neutral pull-request operations for the readiness workflow. Run via
`python -m scripts.forge <operation>`; every operation prints JSON, and the only comment it writes is the
`<!-- pr-readiness -->` readiness comment. The GitHub adapter calls `gh`; another host needs one new adapter.

| Operation | What it returns or does |
|---|---|
| `pr-info [--pr N]` | Number, refs, head sha, draft flag, state, and `diff_base_ref` (`origin/<base>`) |
| `comment-get [--pr N] [--author L]` | The readiness comment from a trusted author, or `null` |
| `comment-upsert --body-file F [--pr N]` | Edits the readiness comment in place or creates it; refuses a body without the marker |
| `implement-plan --plan F [--base develop] [--model sonnet] [--depends-ok] [--no-ready] [--no-fix] [--no-container] [--agent-container] [--wait-minutes 45]` | Claims a plan from `plan/` with a draft pull request, has an agent implement it, runs the gate, and takes the pull request out of draft only when nothing needs the owner, then waits for the first review and runs the fixer loop unless `--no-fix` |
| `fix-loop --pr N [--max-rounds 3] [--wait-minutes 45] [--model sonnet] [--agent-container]` | Runs fixer rounds on a pull request from the owner's machine until its comment says READY, only owner decisions are left, or the round cap is reached; at READY it first removes the plan file the branch claimed (and its index row), pushes, and waits for the confirming pass; emails the owner at the end |
| `review-context [--pr N] [--expect-sha S] [--max-passes N]` | Pull request, previous readiness comment and its pass number, CI state, and whether the pass cap is reached; fails if the head is not `S` or the previous pass cannot be read |
| `check-body --body-file F [--previous-pass N \| --edit-of OLD] [--forbid-env NAME]` | Refuses a comment body with no marker, a wrong pass number, a local path, or credential-like text; with `--edit-of`, the pass must be unchanged and only status lines may be added to `OLD` |

| Module | Responsibility |
|---|---|
| `base.py` | Forge-neutral types, the `Forge` interface, CI aggregation, and the marker rule |
| `github.py` | GitHub adapter over the `gh` CLI |
| `service.py` | Trusted-author resolution, CI waiting, and the review context |
| `readiness.py` | Pass-number parsing, the pre-post checks on a comment body, and the scan of an agent's commits and changed paths for the Claude token |
| `findings.py` | The verdict and findings of a readiness comment, and which open findings a fixer can still work |
| `guarded_paths.py` | Paths an unattended fixer must never change |
| `plans.py` | Reading a plan and its index row, deciding whether it can be picked up, marking it claimed, and finding the plans a branch claimed |
| `implement.py` | The plan pickup: claim, agent, push, gate, path check, a scan of the agent's commits for the Claude token, plain-file reads of its summary and questions, and the decision to leave draft |
| `pipeline.py` | The join: pickup, then the wait for the first review, then the fixer loop, with one final notification |
| `fix_loop.py` | The fixer loop: one round, its checks (path guard, token scan, plain-file read of the comment body), the post and push, the wait for the next pass |
| `sandbox.py` | A throwaway clone with its own venv for the agent to work in; only its commits come back. `harden_clone` resets the clone's git configuration and hooks before the controller runs git there, `read_agent_text` reads a file the agent wrote only when it is a plain file, and the no-exec git options and secret-name pattern live here |
| `container.py` | Runs the gate (no network, no credentials) and the agent (open network, one Claude token) in Docker containers with only the clone mounted; builds the images from the owner's checkout through an injected Docker runner |
| `local.py` | The owner's real git (importing and fast-forwarding a sandbox's commits, and `outgoing_text`, the added lines and messages the token scan reads), the headless `claude` runner with a scrubbed environment, the result reporting the container runner shares, the gate runner, and the email notifier |
| `tools.py` | What an unattended agent may run: the allow and deny tool lists, the prompt note that names them, and the options that make the runners deny-by-default, built from one set of constants |
| `cli.py` | Argument parsing and JSON output |
| `__main__.py` | Entry point for `python -m scripts.forge` |

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
| `pr.py` | Pre-PR gate: enforced docs + repo + branch-targeted Python, plus frontend when the diff touches it |
| `run_suite.py` | Targeted suite runner — run tests for a specific path prefix (e.g. `src/trading/services/reporting`) |
| `_runner.py` | Internal shared check-runner helpers for steps and tool executable resolution |

| Package | Checks |
|---|---|
| `scripts/checks/docs/` | `scripts/checks/docs/docs_check.py`, `scripts/checks/docs/readme_check.py`, `scripts/checks/docs/maps_check.py`, `scripts/checks/docs/link_check.py`, `scripts/checks/docs/module_ref_check.py`, `scripts/checks/docs/db_schema_check.py`, `scripts/checks/docs/doc_header_check.py`, `scripts/checks/docs/doc_naming_check.py` |
| `scripts/checks/repo/` | `scripts/checks/repo/repo_check.py`, `scripts/checks/repo/layer_check.py`, `scripts/checks/repo/skills_check.py`, `scripts/checks/repo/live_safety_check.py`, `scripts/checks/repo/migration_check.py`, `scripts/checks/repo/path_safety_check.py`, `scripts/checks/repo/review_scope_check.py`, `scripts/checks/repo/secret_hygiene_check.py`, `scripts/checks/repo/sector_map_check.py` |
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
python -m scripts.run_checks pr --base develop
```

**Deterministic pre-PR gate (no AI, no tokens):**
```
python -m scripts.run_checks pr --base develop
```

---

## CI Helpers (`scripts/ci/`)

Called from the GitHub workflows with the system Python, so standard library only.

| Module | Responsibility |
|---|---|
| `changed_scope.py` | Prints `<group>=true` or `false` for each group of paths a pull request changed, using `git diff --quiet` against the merge base; a git error counts as changed. The `changes` jobs of `ci.yml` and `security-checks.yml` call it |

---

## Data Ops (`scripts/data_ops/`)

One-off data operations. Safe to run on the live DB when noted.

| Module | Responsibility |
|---|---|
| `backup_db.py` | SQLite DB backup — copies the live DB to a timestamped backup file |
| `check_cash_invariant.py` | Read-only reconciliation report: each book's `current_cash` vs `start_equity` + ledger sum, within a float tolerance |
| `build_database_diagram_viewer.py` | Build the checked-in interactive HTML database diagram viewer at `docs/reference/database-diagram-viewer.html` |
| `capture_scenario_fixture.py` | Capture a real-history scenario-bench fixture into the untracked `local/scenario_bench/` (one episode, or all) |
| `describe_db_schema.py` | Print current DB schema (tables, columns, types); use `--source live` for the live DB |
| `manage_db_migrations.py` | Migration lifecycle: status, upgrade (creates missing/empty DBs, backs up existing ones), downgrade, history |

## Database Diagrams (`scripts/database_diagrams/`)

Project-agnostic diagram tooling. Adapters inspect a database or load a neutral schema JSON payload; the renderer writes a self-contained HTML viewer.

| Module | Responsibility |
|---|---|
| `html_viewer.py` | Assemble the interactive HTML database diagram from a neutral payload and the `assets/` files |
| `assets/` | Viewer markup, styles, and behavior (`viewer.html`, `viewer.css`, `viewer.js`) edited as real HTML/CSS/JS |
| `render_html.py` | CLI for rendering a neutral schema JSON payload to HTML |
| `sqlite.py` | CLI for inspecting a SQLite database file and writing neutral JSON and/or HTML |
| `sqlite_introspection.py` | SQLite schema introspection adapter that builds the neutral payload |

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
| `overview/` | Repository facts for the About page (database tables, strategy count, ADR count, floored test count) written to `assets/overview.json`; the check fails on drift |
| `commands/` | Command catalog registry: `registry.py` reads the CLI `argparse` parser, `entrypoints.py` reads runtime jobs, scripts, and checks, and `introspect.py` holds the shared parser reader. Output is `assets/commands.json` (kind, group, family, risk, schedule, example, arguments). The check fails on drift, an unclassified command, a family with no summary, or a runnable module with no entry |

---

## Root Scripts

| Script | Responsibility |
|---|---|
| `run_checks.py` | Check runner entry point (see above) |
| `fix_checks.py` | Deterministic local auto-fix entry point: Python lint/format drift, generated API/software reference-doc assets, and docs drift fixers under `scripts/fixes/` |
| `launch_ui.py` | Launch the paper trading UI (backend + frontend dev server) |
| `launch_demo.py` | Atomically rebuild `local/demo.db` with synthetic data and launch the offline demo UI |
| `launch_sandbox.py` | Restore the disposable `local/sandbox.db` test bed from its golden build and launch the UI |
| `fixture_db.py` | Build/publish helpers for generated fixture databases (migrate + seed, golden fingerprint, throwaway checkout) |
| `ui_config.py` | UI launch configuration (ports, paths) |
| `screenshot_ui.py` | Capture UI screenshots (used for docs/reference) |
| `check_jobs.py` | Report each monitored runtime job's run status from its logs (shared source with the web Admin panel); `--run-missing` triggers unhealthy jobs |
| `ibkr_web_api_smoke_test.py` | IBKR Web API connectivity smoke test |
| `ibkr_socket_smoke_test.py` | Operator-run IBKR socket/TWS smoke test: read-only connectivity checks against a local TWS/Gateway paper port, with an opt-in paper order round trip |
| `benchmark_sweep.py` | Time the walk-forward optimizer against a DB copy so sweep candidate budgets can be sized from measured cost |

---

## Related References

- [`docs/architecture/nav-guide.md`](../architecture/nav-guide.md) — When to use which script
- [`docs/maps/trading-package-map.md`](trading-package-map.md) — Layer rules enforced by `layer_check.py`
