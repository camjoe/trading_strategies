# Runtime Jobs Reference

Type: notes
Status: Active
Created: 2026-06-25
Last Reviewed: 2026-07-02
Purpose: Single catalog of runtime job entrypoints — what each job is, how to run it, and how to register it on a scheduler. (Merged with the former runtime-jobs-inventory.md.)
Related: [Runtime Operations Runbook](../runbooks/runtime-operations.md), [Governance Review Guide](../runbooks/governance-review.md), [Trading Package Map](../maps/trading-package-map.md)

How to run and schedule the runtime job entrypoints. For the full structural module inventory see
[trading-package-map.md](../maps/trading-package-map.md) (Runtime jobs section); for monitoring and
recovery procedures see the [Runtime Operations Runbook](../runbooks/runtime-operations.md).

All commands run as Python modules from the repository root with the active venv interpreter
(`.venv\Scripts\python.exe` on Windows, `./.venv/bin/python` on POSIX).

## Scheduled jobs

Jobs registered by the installer (`manage_job_schedules.py`).

| Job | Entrypoint | Task name | Frequency | Why it exists / how it is used |
|---|---|---|---|---|
| Daily paper trading | `python -m trading.interfaces.runtime.jobs.daily.paper_trading` | `Trading\DailyPaperTrading` | Daily at `--daily-paper-trading-time` | Main daily runtime workflow. Loads runtime-eligible accounts, optionally runs challenger shadow evaluation, executes auto trades, snapshots accounts, compares strategies, and emits logs, artifacts, and notifications. |
| Daily paper trading fallback | `python -m trading.interfaces.runtime.jobs.daily.paper_trading --run-source scheduled-daily-fallback` | `Trading\DailyPaperTradingFallback` | Daily at `--daily-paper-trading-fallback-time` | Second duplicate-guarded attempt in case the primary daily run missed or failed before completion. |
| Challenger shadow evaluation | `python -m trading.interfaces.runtime.jobs.daily.challenger_shadow_eval` | `Trading\DailyChallengerShadowEval` | Daily at `--daily-challenger-shadow-eval-time`, or auto-derived before paper trading with `--auto-shadow-eval-from-daily-paper` | Scores challenger strategies against incumbents for runtime-eligible accounts and writes account-level shadow-evaluation artifacts. Disabled unless `--enable-run` or the matching environment enable is set. |
| Daily snapshot | `python -m trading.interfaces.runtime.jobs.daily.snapshot` | `Trading\DailySnapshot` | Daily at `--daily-snapshot-time` | Runs account snapshots with duplicate-run guard and retry handling. Disabled unless `--enable-run` or the matching environment enable is set. |
| Daily backtest refresh | `python -m trading.interfaces.runtime.jobs.daily.backtest_refresh` | `Trading\DailyBacktestRefresh` | Daily at `--daily-backtest-refresh-time` | Refreshes backtest runs for runtime accounts, captures run IDs, retries transient failures, and writes JSON artifacts under `local/exports/daily_backtest_refresh/`. Disabled unless `--enable-run` or the matching environment enable is set. |
| Daily trader health check | `python -m trading.interfaces.runtime.jobs.daily.trader_health` | `Trading\DailyTraderHealthCheck` | Daily at `--health-check-time` | Checks that the latest daily paper-trading log is recent and contains the success sentinel; can notify on failure. |
| Weekly DB backup | `python -m trading.interfaces.runtime.jobs.maintenance.weekly_db_backup` | `Trading\WeeklyDbBackup` | Weekly at `--weekly-db-backup-time` on `--weekly-db-backup-day-of-week` | Runs the database backup command with a same-week duplicate guard. |

## Manual or indirect jobs

| Job | Entrypoint | Frequency | Why it exists / how it is used |
|---|---|---|---|
| Run auto trades | `python -m trading.interfaces.runtime.jobs.daily.paper_trading.run_auto_trades` | Indirect/manual | Executes per-account signal-driven trades (only when the active strategy signals, up to `--max-trades`). The daily paper-trading job shells out to this module; operators can also run it manually. |
| Burn-in status | `python -m trading.interfaces.runtime.jobs.maintenance.burn_in_status` | Manual/ad hoc daily-style guard | Scans daily paper-trading artifacts to report burn-in stability and go-live readiness (counts consecutive artifacts with top-level `status == "success"`). |
| Replay daily runs | `python -m trading.interfaces.runtime.jobs.maintenance.replay_daily_runs` | Manual recovery | Finds dates in a range without successful daily paper-trading logs and replays them with `--as-of-date --force-run`. |

## Governance jobs

Runnable entrypoints with weekly or monthly duplicate guards; **not** registered by
`manage_job_schedules.py`. Procedures and artifact interpretation live in the
[Governance Review Guide](../runbooks/governance-review.md).

| Job | Entrypoint | Frequency | Why it exists / how it is used |
|---|---|---|---|
| W1 weekly leaderboard | `python -m trading.interfaces.runtime.jobs.governance.weekly.w1_leaderboard` | Weekly dedup guard | Ranks account sleeves by recent performance, default 30-day window, for governance review. |
| W2 weekly promotion review | `python -m trading.interfaces.runtime.jobs.governance.weekly.w2_promotion_review` | Weekly dedup guard | Produces promotion/retirement readiness review for runtime-eligible accounts. |
| W3 weekly allocation review | `python -m trading.interfaces.runtime.jobs.governance.weekly.w3_allocation_review` | Weekly dedup guard | Compares actual sleeve NAV allocation against target/start-equity ratios and flags drift. |
| M1 monthly risk rebaseline | `python -m trading.interfaces.runtime.jobs.governance.monthly.m1_risk_rebaseline` | Monthly dedup guard | Captures latest risk snapshots per account for operator risk budget review. |
| M2 monthly parameter governance | `python -m trading.interfaces.runtime.jobs.governance.monthly.m2_parameter_governance` | Monthly dedup guard | Inventories active strategy assignments and parameter sets per sleeve. |
| M3 monthly performance audit | `python -m trading.interfaces.runtime.jobs.governance.monthly.m3_performance_audit` | Monthly dedup guard | Runs a longer-horizon sleeve performance audit, default 90 days. |

## Helper modules

These support the jobs above but are not standalone jobs: `job_helpers.py`, the `job_runner/`
package (`governance_job`, `daily_account_job`, `maintenance_job` decorators),
`scheduling/scheduler_installer.py`, and `daily/paper_trading/{caps,dag,reporting}.py`.

## Running jobs directly

The direct job scripts are the source of truth — run the job you want directly, and use
`manage_job_schedules` only when you need to install or remove scheduler entries.

```sh
# Daily paper trading
./.venv/bin/python -m trading.interfaces.runtime.jobs.daily.paper_trading --run-source manual

# Daily snapshot
./.venv/bin/python -m trading.interfaces.runtime.jobs.daily.snapshot --run-source manual --enable-run

# Daily backtest refresh
./.venv/bin/python -m trading.interfaces.runtime.jobs.daily.backtest_refresh --accounts all --enable-run

# Weekly DB backup
./.venv/bin/python -m trading.interfaces.runtime.jobs.maintenance.weekly_db_backup

# Health check
./.venv/bin/python -m trading.interfaces.runtime.jobs.daily.trader_health --max-age-hours 24
```

## Registering schedules

`manage_job_schedules` writes Windows Task Scheduler entries on Windows. On Linux it auto-detects
systemd and creates systemd timer units; falls back to cron if systemd is unavailable. Pass
`--scheduler cron` or `--scheduler systemd` to override. **Always preview with `--dry-run` first.**

```sh
# Register the core runtime jobs (Linux — generates local/install_trading_timers.sh)
./.venv/bin/python -m trading.interfaces.runtime.scheduling.manage_job_schedules \
  --daily-paper-trading-time 13:00 \
  --daily-paper-trading-fallback-time 13:20 \
  --health-check-time 13:35 \
  --weekly-db-backup-day-of-week Sunday \
  --weekly-db-backup-time 12:58

# Then install with sudo (systemd timers require root to write to /etc/systemd/system/)
sudo bash local/install_trading_timers.sh

# Set AC inactivity timeout to 60 min so the machine stays up through the job window
gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-timeout 3600

# Alternatively, auto-derive the shadow-eval time as a lead before daily paper trading
./.venv/bin/python -m trading.interfaces.runtime.scheduling.manage_job_schedules \
  --daily-paper-trading-time 13:00 \
  --auto-shadow-eval-from-daily-paper --shadow-eval-lead-minutes 20

# Remove previously registered entries (preview with --dry-run first)
./.venv/bin/python -m trading.interfaces.runtime.scheduling.manage_job_schedules --unregister --dry-run
./.venv/bin/python -m trading.interfaces.runtime.scheduling.manage_job_schedules --unregister
sudo bash local/uninstall_trading_timers.sh
```

On Windows, the same registration commands apply with the PowerShell path form
(`.\.venv\Scripts\python.exe -m ...`) plus an explicit `--python .\.venv\Scripts\python.exe`.

### Behavior notes

- `manage_job_schedules.py` is a thin schedule entrypoint; `scheduler_installer.py` handles platform-specific installation.
- On Linux with systemd, the installer generates `local/install_trading_timers.sh` (requires `sudo bash` to apply). Each timer includes `WakeSystem=yes` so the machine wakes from sleep before the job fires. Pass `--no-wake-system` to disable this.
- Pass `--env-file /path/to/.env` to inject secrets via `EnvironmentFile=` in each service unit (systemd only). The file is treated as optional — a missing file does not fail the job. For cron setups, the production runbook documents an equivalent `run-job.sh` wrapper you create on the host.
- `--python` defaults to the venv's python when running inside a venv; override explicitly if needed.
- Snapshot, daily backtest refresh, and challenger shadow-evaluation entries can be installed before they are operator-enabled. They only execute real work when the scheduled command includes `--enable-run` (via `--enable-daily-snapshot` / `--enable-daily-backtest-refresh` / `--enable-daily-challenger-shadow-eval`) or the matching environment variable is set. The `--auto-shadow-eval-from-daily-paper` form enables the shadow-eval run automatically.
- Windows Task Scheduler task names default to the `Trading\*` names in the scheduled-jobs table above.

## Configuration

- `src/infrastructure/config/account_trade_caps.json` — per-account trade caps used by the runtime scheduler; supports per-account `min`/`max` trade counts with a `default` fallback.
- Trade universe files live under `src/infrastructure/config/` (default `trade_universe.txt`); pass `--tickers-file` to select a preset. See [src/trading/README.md](../../src/trading/README.md) for universe presets and auto-trading behavior.
