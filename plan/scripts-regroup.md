# Plan: group this project's own scripts apart from the tooling in `scripts/`

Status (2026-11-11): drafted. Nothing built. The folder name is decided (`scripts/app/`). One owner question is
open: whether the production host calls any of these scripts by path. Item 1 can start; answer the question
before anything merges.

Keep this file until the "Left to do" list is empty.

## Left to do
Check these off in the pull request that does each one; delete this file when none remain.
1. **Item 1, move the eleven loose top-level scripts** into `scripts/app/`.
2. **Item 2, move `scripts/data_ops/`** into `scripts/app/`.
3. **Item 3, say which is which** in `scripts/README.md` and `docs/maps/scripts-map.md`.

## Goal
Opening `scripts/` should show at a glance what is tooling (the quality gate and the AI pipeline, which would
work on another repository) and what belongs to this trading project (launchers, fixtures, broker smoke tests,
database commands). Today eleven project scripts sit loose at the top level beside `run_checks.py` and
`fix_checks.py`.

File moves only. **No script changes what it does**, with one mechanical exception named in item 1: five
scripts find the repository root by counting parent folders and must stop doing that before they move a level
deeper. The tooling (`forge/`, `checks/`, `fixes/`, `ci/`, `run_checks.py`, `fix_checks.py`) does not move;
its paths carry most of the references in the repository.

## What exists (verified, 2026-11-11)
- **`scripts/` is 98 Python files, about 14,200 lines, in four groups.**

  | Group | Where | Lines | Imports `trading` / `backtesting` / `infrastructure`? |
  |---|---|---|---|
  | AI pipeline | `forge/` | 4,133 | One place: `forge/local.py` imports the runtime email notifier inside a function |
  | Quality gate | `checks/`, `fixes/`, `ci/`, `run_checks.py`, `fix_checks.py` | about 5,190 | Two checks: `checks/repo/migration_check.py`, `checks/docs/db_schema_check.py` |
  | Project scripts | eleven loose files and `data_ops/` | about 3,830 | Nearly all |
  | Docs generators | `documentation_ui/`, `database_diagrams/` | about 1,190 | No |

- **The eleven loose files**: `benchmark_sweep.py`, `check_jobs.py`, `dev_run_daily.py`, `fixture_db.py`,
  `ibkr_socket_smoke_test.py`, `ibkr_web_api_smoke_test.py`, `launch_demo.py`, `launch_sandbox.py`,
  `launch_ui.py`, `screenshot_ui.py`, `ui_config.py`. `data_ops/` is the other project folder (seven modules:
  `backup_db`, `build_database_diagram_viewer`, `capture_scenario_fixture`, `check_cash_invariant`,
  `describe_db_schema`, `manage_db_migrations`, `probe_intraday_bars`).
- **They import each other by full path**: `dev_run_daily` imports `scripts.fixture_db` and
  `scripts.launch_sandbox`; `launch_demo` and `launch_sandbox` import `scripts.fixture_db` and
  `scripts.ui_config`; `launch_ui` and `screenshot_ui` import `scripts.ui_config`.
- **Five scripts locate the repository root by position.** `dev_run_daily.py`, `launch_demo.py`,
  `launch_sandbox.py`, and `launch_ui.py` use `Path(__file__).resolve().parent.parent`; `launch_ui.py` and
  `screenshot_ui.py` also insert that path into `sys.path`. Moved one folder deeper, each would silently point
  at `scripts/` instead of the repository. `check_jobs.py` already uses `common.git.get_repo_root(__file__)`.
- **Command paths appear in runtime text inside `src/`**, not only in docs:
  `_STATUS_COMMAND` in `src/infrastructure/database/connection.py`
  (`python -m scripts.data_ops.manage_db_migrations status`), the capture hint in
  `src/backtesting/services/scenario_fixtures.py`, and the upgrade hints inside `manage_db_migrations.py`
  itself.
- **Where the moving paths are named** (files, not occurrences): 9 under `docs/reference/`, 5 under
  `docs/runbooks/`, 2 under `docs/maps/`, 1 under `docs/architecture/`, 4 under `.ai/skills/` (the
  `db-migration` skill), 7 under `tests/scripts/`, 1 under `tests/src/`, the READMEs of `src/trading`,
  `src/trading/repositories`, `src/backtesting`, `src/infrastructure/database`, `apps/paper_trading_web`, and
  the root, one line in `AGENTS.md` (Working references), a comment in
  `apps/paper_trading_web/backend/schemas/strategy_lab.py`, and `plan/ib-gateway-socket-switch.md`.
- **Nothing in `.github/workflows/`, `docker/`, or `.claude/settings.json` names any moving script.** The CI
  path filters use `scripts/**` and `scripts`, which still match after the move.
- **Tests are flat and found by file stem.** `tests/scripts/test_<stem>.py` is what
  `scripts/checks/python/public_api_test_evidence_check.py` looks for when a file under `scripts/` changes, so
  the tests can stay where they are. Seven test modules import the moving scripts (`check_jobs`,
  `dev_run_daily`, `fixture_db`, `ibkr_socket_smoke_test`, `backup_db`, `probe_intraday_bars`,
  `manage_db_migrations`); `test_ibkr_web_api_smoke_test.py` was not read.
- **`docs/maps/scripts-map.md` is checked against the tree** by `maps_check.py` (its `MAP_SPECS` entry for
  `scripts`). It has a "Root Scripts" section and a "Data Ops (`scripts/data_ops/`)" section.
- **All of `scripts/` is a guarded path** (`scripts/forge/guarded_paths.py`), so the unattended pickup cannot
  do this work. It is for the owner or an attended session.
- **Unverified:** whether anything outside the repository calls these scripts by path: the production host's
  scheduler units or crontab, shell aliases, or notes under `local/`. `docs/runbooks/` shows operators running
  `scripts.check_jobs`, `scripts.data_ops.backup_db`, and `scripts.data_ops.manage_db_migrations` by hand.

## Target layout
```
scripts/
  run_checks.py  fix_checks.py     tooling: entry points          (unchanged)
  checks/  fixes/  ci/             tooling: the quality gate      (unchanged)
  forge/                           tooling: the AI pipeline       (unchanged)
  documentation_ui/                docs generators                (unchanged)
  database_diagrams/               docs generators                (unchanged)
  app/                             this repository's own scripts  (new)
    dev/        launch_ui  launch_demo  launch_sandbox  ui_config  fixture_db
                dev_run_daily  screenshot_ui  benchmark_sweep
    broker/     ibkr_socket_smoke_test  ibkr_web_api_smoke_test
    ops/        check_jobs
    data_ops/   the seven modules, unchanged inside
```

## Work items
One pull request per item, in order. Each passes the gate on its own.

### 1. Move the eleven loose scripts
- First, in its own commit before any move: replace the five position-based repository-root lookups with
  `common.git.get_repo_root(__file__)`, and remove the two `sys.path.insert` lines if the editable install
  already makes the imports work (`scripts/__init__.py` says it does). Run each launcher once to confirm it
  still finds `apps/paper_trading_web`. **Unverified:** that `launch_ui` and `screenshot_ui` start without the
  `sys.path` line when run as `python scripts/launch_ui.py` instead of `python -m`; if they do not, keep the
  insert and compute the path with `get_repo_root`.
- Then `git mv` the files into `dev/`, `broker/`, and `ops/` as in the layout, add the `__init__.py` files,
  and update the imports between them.
- Update every reference found in "What exists": docs, runbooks, READMEs, the source comment in
  `strategy_lab.py`, the docstring in `src/trading/services/operations/job_status.py`, the usage lines inside
  the scripts' own docstrings, and the test imports.
- No forwarding modules left at the old paths (architecture conventions, Import and Facade Rules). If the
  owner's answer on the production host says an old path is called there, stop and agree the changeover first.
- Tests stay in `tests/scripts/` under their current names.

### 2. Move `data_ops/`
- `git mv scripts/data_ops scripts/app/data_ops`. Nothing inside it changes except its own usage text
  and the `scripts.database_diagrams` import path if it is relative to the old location (it is absolute today,
  so it should not).
- Update the three places where the command path is runtime text: `_STATUS_COMMAND` in
  `src/infrastructure/database/connection.py`, the hint in `src/backtesting/services/scenario_fixtures.py`,
  and the hints in `manage_db_migrations.py`. These are operator-facing messages; search the tests for the old
  string and update any that pin it. `src/infrastructure/database/` is high-risk scope: the change there is one
  string constant and nothing else.
- Update the `db-migration` skill files under `.ai/skills/`, the `AGENTS.md` Working references line, and the
  READMEs and reference docs that give the commands. `AGENTS.md` and `.ai/skills/` are guarded; the owner makes
  or approves those edits.
- Kept separate from item 1 because it touches `src/`, the skill, and `AGENTS.md`, and because these are the
  commands most likely to be typed from memory or called on the host.

### 3. Say which is which
- `scripts/README.md`: replace "Ownership Boundaries" and the catalog's opening with a short table of the top
  level: what is tooling, what is a docs generator, what is this project's own. Keep the per-script detail in
  the map, not here.
- `docs/maps/scripts-map.md`: replace "Root Scripts" and "Data Ops" with sections for the new folders, and
  mark each top-level section as tooling, docs generator, or project. `maps_check` must pass.
- State the rule for new scripts in one sentence in the README: a script that imports `trading`, `backtesting`,
  `infrastructure`, or the web app goes under `scripts/app/`.

## Constraints
- A file move and a behaviour change are separate steps. The repository-root fix in item 1 is its own commit.
- Do not touch `forge/`, `checks/`, `fixes/`, `ci/`, `run_checks.py`, `fix_checks.py`,
  `scripts/forge/guarded_paths.py`, the workflows, or `docker/`.
- Nothing here is strategy-specific; all of it is intentionally public.
- Run `python -m scripts.fix_checks`, then `python -m scripts.run_checks pr --base origin/develop`. After each
  item, `git grep -nE "scripts[./](<old names>)"` must return nothing outside this plan.
- **Environment (seen 2026-11-11 on the dev PC):** the `.venv` editable install resolved to a different
  checkout, so imports failed until `PYTHONPATH` pointed at this checkout's `src` and `apps`. If imports fail
  the same way, report it; do not reinstall the environment unasked.

## Decisions (owner, 2026-11-11)
- The folder is `scripts/app/`. It is a different thing from the top-level `apps/` folder, which holds the web
  app and the trends app; say so in the README table in item 3.

## Decisions needed (owner)
- **Does the production host, or anything else outside the repository, call a moving script by path?** If yes,
  list the paths so the changeover can be planned with the move.

## Out of scope
- Moving `documentation_ui/`. It builds this project's frontend assets, so it is project-specific, but
  `fix_checks.py` and the docs check call it, which makes it part of the gate's wiring.
- Regrouping `tests/scripts/`.
- Anything under "Not yet" below.

## Not yet (owner, 2026-11-11)
Considered and deliberately left out. Recorded so the reasoning is here if the answer changes.

### A. Separate the rules from the engines
Make the gate and the pipeline read this project's rules from one place instead of holding them inline.

- Where the project knowledge sits today: the layer rules in `checks/repo/layer_check.py`, the scope rules in
  `checks/repo/review_scope_check.py`, the map list (`MAP_SPECS`) in `checks/docs/maps_check.py`, the default
  targets in `checks/python/mypy_check.py` and `ruff_check.py`, and the extra guarded paths in
  `forge/guarded_paths.py`. The other check and forge modules name no project path, or one or two.
- Two checks are about trading and nothing else: `checks/repo/sector_map_check.py` and
  `checks/repo/live_safety_check.py`. They would move to a project-checks folder that the generic runner calls.
- `forge/local.py` imports the trading runtime's email notifier. It would take a notifier from configuration.
- Why not now: it changes the guarded-path list and the gate's own checks, which the standing authorizations
  in `AGENTS.md` say need the owner's yes, and it is worth doing only as the first step toward B.
- What would change the answer: a decision to reuse the tooling in a second repository, or the rule files
  becoming hard to find.

### B. Make the tooling its own project
Move `forge/` and the generic part of `checks/` to a separate package or repository that this one installs.

- What stands in the way today: 40 script modules import `common.git.get_repo_root` and 13 import
  `common.paths`, both from this project's `src/common`. `src/` uses `common.git` too, so the tooling would
  need its own copy of those helpers or the dependency would stay.
- The PR-readiness workflow runs `python -m scripts.forge` from the base branch, and `docker/Dockerfile` builds
  the gate image from this checkout. Both would have to install the tooling from somewhere else, pinned.
- Why not now: with one repository using it, a separate project adds versioning and release work and makes a
  tooling fix a two-repository change. Step A makes this a small move later.
- What would change the answer: a second repository that wants the gate or the pipeline.

### C. Move the tooling out of `scripts/` instead of the project scripts
Give the tooling its own top-level folder and leave `scripts/` to the project.

- Why not now: the tooling paths are the most referenced in the repository (`scripts.run_checks` and
  `scripts.forge` alone appear about 100 times outside `scripts/`), they are written into the standing
  authorizations in `AGENTS.md`, and the workflow and the guarded-path list name them. Moving the project
  scripts reaches the same separation by touching far fewer places.
- What would change the answer: doing B, at which point the tooling leaves the repository anyway.

## Developer verification (fill in when the work ships)
- Item 1: `python -m scripts.app.dev.launch_sandbox --no-ui` prints a database path under `local/`;
  `ls scripts/*.py` shows only `__init__.py`, `run_checks.py`, and `fix_checks.py`.
- Item 2: `python -m scripts.app.data_ops.manage_db_migrations status` runs, and the message a stale
  database raises names that same command.
- Item 3: `python -m scripts.run_checks docs --advisory` passes.
