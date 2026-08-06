---
name: create-runtime-job
description: Scaffolds a new runtime job under src/trading/interfaces/runtime/jobs using the shared job_runner — picks the right decorator (daily_account_job, governance_job, or maintenance_job), then generates the module, its harness test, the completion sentinel, optional schedule wiring, and the inventory row. Use when adding a new scheduled runtime job, daily account job, governance review job, or maintenance job.
---

# Create Runtime Job

Runtime jobs share one lifecycle runner (`trading.interfaces.runtime.jobs.job_runner`).
Each job is a decorator config plus a small body — the runner owns arg parsing, the
dedup guard, the DB session, artifact/sentinel writing, and exit codes. This skill
scaffolds a new job against the right decorator. Code templates live in
[templates.md](templates.md).

## 1. Pick the job shape

| Shape | Decorator | Body signature | Cadence | Accounts | Artifact |
|---|---|---|---|---|---|
| Per-account daily | `daily_account_job` | `body(ctx, account) -> dict` | daily | runtime-eligible | combined results under `local/exports/<subdir>` |
| Governance review | `governance_job` | `body(ctx) -> dict` | weekly / monthly | runtime-eligible | tagged under `local/artifacts` |
| Maintenance | `maintenance_job` | `body(ctx) -> int` | weekly / monthly | none | none (sentinel only) |

Decision hints:
- Runs a command or evaluation once per account, gated behind an enable flag → `daily_account_job`.
- Produces a review artifact across accounts on a weekly/monthly dedup → `governance_job`.
- Housekeeping with no accounts and no artifact (backup, prune) → `maintenance_job`.
- A worker invoked by another job (not scheduled, no dedup/sentinel) → this is **not** a runner
  job; write a plain module (see `run_auto_trades.py`).

## 2. Add the completion sentinel

Add `<JOB>_COMPLETE_SENTINEL = "<Job> run succeeded."` to `src/common/runtime_job_status.py`
and its `__all__`. Job modules import it from there directly — the sentinels live in
`common/` because the web backend reads them too and cannot import the interface layer.

## 3. Create the module

Fill the matching template from [templates.md](templates.md), placed at:
- daily → `src/trading/interfaces/runtime/jobs/daily/<name>.py`
- governance → `.../governance/weekly/<name>.py` or `.../governance/monthly/<name>.py`
- maintenance → `.../maintenance/<name>.py`

## 4. Create the harness test

Use the shared harness (`run_runtime_job_main` / `run_runtime_job_with_args` from
`tests/src/trading/interfaces/runtime/jobs/loaders.py`) — see [templates.md](templates.md). Patch lifecycle
seams (`resolve_accounts`, `load_runtime_eligible_account_names`, `db_session`) on the
`job_runner._core` submodule, where those lookups live; patch the job's own body helper on
the job module.

## 5. Wire the schedule (daily + maintenance only)

In `manage_job_schedules.py`: add `<NAME>_MODULE`, a `DEFAULT_..._TASK_NAME`, a
`--...-time` argument, and a `build_scheduled_tasks` entry; add the task name to
`default_task_names`. Governance jobs are not installer-registered.

## 6. Add the inventory row

Add a row to `docs/reference/runtime-jobs.md` in the Scheduled / Manual /
Governance table that matches the job.

## 7. Validate

```
python -m scripts.run_checks repo
python -m scripts.run_checks python --suite src/trading/interfaces/runtime/jobs/<area> --no-cov
```

## Constraints

- Do not hand-roll the lifecycle (parse / dedup / sentinel / artifact). It belongs to the runner.
- A per-account body returns a dict carrying a `status` key (`"success"` marks the account done).
- Set `open_db=True` only when the body runs against the DB in-process; leave it `False` for
  bodies that shell out to subprocesses.
- Keep the module to constants + helpers + body. There is no `main()` logic to write.
- If a job grows into a multi-file package (like `daily/paper_trading/`), put the entrypoint in
  `__main__.py` and have the entrypoint smoke test run `run_module_as_main(pkg + ".__main__")` —
  targeting the package itself pops/re-executes `__init__` and corrupts the shared module object
  for sibling tests under xdist.

## Repo references

- `src/trading/interfaces/runtime/jobs/job_runner/__init__.py` — the three decorators + `__all__`
- `src/trading/interfaces/runtime/jobs/daily/challenger_shadow_eval.py` — daily example
- `src/trading/interfaces/runtime/jobs/governance/weekly/w1_leaderboard.py` — governance example
- `src/trading/interfaces/runtime/jobs/maintenance/weekly_db_backup.py` — maintenance example
- `docs/reference/runtime-jobs.md` — operator-facing inventory
