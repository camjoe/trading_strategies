# Runtime Jobs Inventory

Type: notes
Status: Active
Created: 2026-06-29
Purpose: Operator-facing inventory of runtime job names, entrypoints, schedule status, install command, and usage.
Related: [Runtime Jobs Reference](runtime-jobs.md), [Runtime Operations Runbook](../runbooks/runtime-operations.md)

This inventory covers the runnable jobs under `src/trading/interfaces/runtime/jobs`.

All commands should be run from the repository root with the repo-local virtual environment:

```powershell
.\.venv\Scripts\python.exe
```

## Install Scheduled Jobs

`manage_job_schedules.py` installs OS-level schedules. On Windows it creates Task Scheduler entries. On Linux it writes cron lines.

Use `--dry-run` first to preview the generated scheduler entries:

```powershell
.\.venv\Scripts\python.exe -m trading.interfaces.runtime.jobs.manage_job_schedules `
  --python .\.venv\Scripts\python.exe `
  --daily-paper-trading-time 13:10 `
  --daily-paper-trading-fallback-time 15:45 `
  --daily-challenger-shadow-eval-time 12:50 --enable-daily-challenger-shadow-eval `
  --health-check-time 16:15 `
  --daily-snapshot-time 16:30 --enable-daily-snapshot `
  --daily-backtest-refresh-time 17:00 --enable-daily-backtest-refresh `
  --weekly-db-backup-day-of-week Sunday `
  --weekly-db-backup-time 02:00 `
  --dry-run
```

Re-run without `--dry-run` to install:

```powershell
.\.venv\Scripts\python.exe -m trading.interfaces.runtime.jobs.manage_job_schedules `
  --python .\.venv\Scripts\python.exe `
  --daily-paper-trading-time 13:10 `
  --daily-paper-trading-fallback-time 15:45 `
  --daily-challenger-shadow-eval-time 12:50 --enable-daily-challenger-shadow-eval `
  --health-check-time 16:15 `
  --daily-snapshot-time 16:30 --enable-daily-snapshot `
  --daily-backtest-refresh-time 17:00 --enable-daily-backtest-refresh `
  --weekly-db-backup-day-of-week Sunday `
  --weekly-db-backup-time 02:00
```

Remove registered entries:

```powershell
.\.venv\Scripts\python.exe -m trading.interfaces.runtime.jobs.manage_job_schedules --unregister --dry-run
.\.venv\Scripts\python.exe -m trading.interfaces.runtime.jobs.manage_job_schedules --unregister
```

## Scheduled Jobs

| Job | Entrypoint | Scheduled by installer? | Frequency | Why it exists / how it is used |
|---|---|---:|---|---|
| Daily paper trading | `python -m trading.interfaces.runtime.jobs.daily.paper_trading` | Yes: `Trading\DailyPaperTrading` | Daily at `--daily-paper-trading-time` | Main daily runtime workflow. Loads runtime-eligible accounts, optionally runs challenger shadow evaluation, executes auto trades, snapshots accounts, compares strategies, and emits logs, artifacts, and notifications. |
| Daily paper trading fallback | `python -m trading.interfaces.runtime.jobs.daily.paper_trading --run-source scheduled-daily-fallback` | Yes: `Trading\DailyPaperTradingFallback` | Daily at `--daily-paper-trading-fallback-time` | Second duplicate-guarded attempt in case the primary daily run missed or failed before completion. |
| Challenger shadow evaluation | `python -m trading.interfaces.runtime.jobs.daily.challenger_shadow_eval` | Yes: `Trading\DailyChallengerShadowEval` | Daily at `--daily-challenger-shadow-eval-time`, or auto-derived before paper trading with `--auto-shadow-eval-from-daily-paper` | Scores challenger strategies against incumbents for runtime-eligible accounts and writes account-level shadow-evaluation artifacts. Disabled unless `--enable-run` or the matching environment enable is set. |
| Daily snapshot | `python -m trading.interfaces.runtime.jobs.daily.snapshot` | Yes: `Trading\DailySnapshot` | Daily at `--daily-snapshot-time` | Runs account snapshots with duplicate-run guard and retry handling. Disabled unless `--enable-run` or the matching environment enable is set. |
| Daily backtest refresh | `python -m trading.interfaces.runtime.jobs.daily.backtest_refresh` | Yes: `Trading\DailyBacktestRefresh` | Daily at `--daily-backtest-refresh-time` | Refreshes backtest runs for runtime accounts, captures run IDs, retries transient failures, and writes JSON artifacts. Disabled unless `--enable-run` or the matching environment enable is set. |
| Daily trader health check | `python -m trading.interfaces.runtime.jobs.daily.trader_health` | Yes: `Trading\DailyTraderHealthCheck` | Daily at `--health-check-time` | Checks that the latest daily paper-trading log is recent and contains the success sentinel; can notify on failure. |
| Weekly DB backup | `python -m trading.interfaces.runtime.jobs.maintenance.weekly_db_backup` | Yes: `Trading\WeeklyDbBackup` | Weekly at `--weekly-db-backup-time` on `--weekly-db-backup-day-of-week` | Runs the database backup command with a same-week duplicate guard. |

## Manual Or Indirect Jobs

| Job | Entrypoint | Scheduled by installer? | Frequency | Why it exists / how it is used |
|---|---|---:|---|---|
| Run auto trades | `python -m trading.interfaces.runtime.jobs.run_auto_trades` | No | Indirect/manual | Executes per-account simulated trade batches. The daily paper-trading job shells out to this module; operators can also run it manually. |
| Burn-in status | `python -m trading.interfaces.runtime.jobs.maintenance.burn_in_status` | No | Manual/ad hoc daily-style guard | Scans daily paper-trading artifacts to report burn-in stability and go-live readiness. Current code appears to count artifact status `"ok"`, while daily paper trading writes `"success"`. |
| Replay daily runs | `python -m trading.interfaces.runtime.jobs.maintenance.replay_daily_runs` | No | Manual recovery | Finds dates in a range without successful daily paper-trading logs and replays them with `--as-of-date --force-run`. |

## Governance Jobs

Governance jobs are runnable entrypoints with weekly or monthly duplicate guards, but they are not registered by `manage_job_schedules.py`.

| Job | Entrypoint | Scheduled by installer? | Frequency | Why it exists / how it is used |
|---|---|---:|---|---|
| W1 weekly leaderboard | `python -m trading.interfaces.runtime.jobs.governance.weekly.w1_leaderboard` | No | Weekly dedup guard | Ranks account sleeves by recent performance, default 30-day window, for governance review. |
| W2 weekly promotion review | `python -m trading.interfaces.runtime.jobs.governance.weekly.w2_promotion_review` | No | Weekly dedup guard | Produces promotion/retirement readiness review for runtime-eligible accounts. |
| W3 weekly allocation review | `python -m trading.interfaces.runtime.jobs.governance.weekly.w3_allocation_review` | No | Weekly dedup guard | Compares actual sleeve NAV allocation against target/start-equity ratios and flags drift. |
| M1 monthly risk rebaseline | `python -m trading.interfaces.runtime.jobs.governance.monthly.m1_risk_rebaseline` | No | Monthly dedup guard | Captures latest risk snapshots per account for operator risk budget review. |
| M2 monthly parameter governance | `python -m trading.interfaces.runtime.jobs.governance.monthly.m2_parameter_governance` | No | Monthly dedup guard | Inventories active strategy assignments and parameter sets per sleeve. |
| M3 monthly performance audit | `python -m trading.interfaces.runtime.jobs.governance.monthly.m3_performance_audit` | No | Monthly dedup guard | Runs a longer-horizon sleeve performance audit, default 90 days. |

## Helper Modules

These files support the jobs above but are not standalone jobs:

- `job_helpers.py`
- `job_runner.py`
- `scheduler_installer.py`
- `paper_trading_caps.py`
- `paper_trading_dag.py`
- `paper_trading_reporting.py`
