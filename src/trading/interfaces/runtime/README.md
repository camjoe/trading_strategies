# runtime/

## Purpose

Operator-facing runtime surface for the trading system: the scheduled/runnable
**jobs**, the **scheduling** tooling that installs them on an OS scheduler, one-off
**data ops**, and the shared libraries they lean on. This README is the index for
*which modules you run* versus *which are imported by something else*.

## Layout

| Path | What lives here |
|---|---|
| `jobs/` | The runtime jobs (`daily/`, `governance/`, `maintenance/`) plus the jobs framework (`job_helpers.py`, `job_runner/`) |
| `scheduling/` | Install/remove OS schedules that invoke the jobs (`manage_job_schedules.py` + `scheduler_installer.py`) |
| `data_ops/` | One-off database admin/export operations (`admin.py` + `csv_export.py`) |
| `job_status.py`, `notifications.py` | Runtime-wide shared libraries (sentinels, webhook alerts) |

## Runnable vs. imported

Every runnable module is invoked as `python -m <module>` and has an
`if __name__ == "__main__"` entrypoint (for the `paper_trading/` package, that
entrypoint is its `__main__.py`). Everything else is a library that is only
imported. There are four categories:

**Scheduled entrypoints** — installed by `scheduling/manage_job_schedules.py`,
run unattended on the host:

- `jobs/daily/paper_trading` (package), `jobs/daily/snapshot`,
  `jobs/daily/backtest_refresh`, `jobs/daily/challenger_shadow_eval`,
  `jobs/daily/trader_health`, `jobs/maintenance/weekly_db_backup`

**Operator entrypoints** — run by hand or on a manual cadence:

- `scheduling/manage_job_schedules` (install/remove schedules),
  `jobs/maintenance/burn_in_status`, `jobs/maintenance/replay_daily_runs`,
  `data_ops/admin`, and the governance jobs `jobs/governance/weekly/w1–w3` and
  `jobs/governance/monthly/m1–m3`

**Internal workers** — invoked by another job, not scheduled directly:

- `jobs/daily/paper_trading/run_auto_trades` (the daily DAG shells out to it; also
  runnable standalone)

**Libraries** — never run directly:

- `jobs/job_helpers.py`, `jobs/job_runner/`, `scheduling/scheduler_installer.py`,
  `jobs/daily/paper_trading/{caps,dag,reporting}.py`,
  `jobs/governance/payload_models.py`, `data_ops/csv_export.py`, `job_status.py`,
  `notifications.py`

## Usage

- Full operator inventory (commands, schedule status, frequency):
  [docs/reference/runtime-jobs-inventory.md](../../../../docs/reference/runtime-jobs-inventory.md).
- Running and scheduling reference:
  [docs/reference/runtime-jobs.md](../../../../docs/reference/runtime-jobs.md).
- To add a new job, use the `create-runtime-job` skill — it scaffolds the module,
  test, sentinel, schedule wiring, and inventory row against the right
  `job_runner` decorator.
