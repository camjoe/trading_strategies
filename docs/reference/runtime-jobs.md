# Runtime Jobs Reference

Type: notes
Status: Active
Created: 2026-06-25
Last Reviewed: 2026-07-13
Purpose: Single catalog of runtime job entrypoints — what each job is, how to run it, and how to register it on a scheduler.
Related: [Runtime Operations Runbook](../runbooks/runtime-operations.md), [Governance Review Guide](../runbooks/governance-review.md), [Trading Package Map](../maps/trading-package-map.md)

How to run and schedule the runtime job entrypoints. For the full structural module inventory see
[trading-package-map.md](../maps/trading-package-map.md) (Runtime jobs section); for monitoring and
recovery procedures see the [Runtime Operations Runbook](../runbooks/runtime-operations.md).

All interactive commands run as Python modules from the repository root and assume the virtual
environment described in the root README is active. Generated scheduler definitions use an explicit
interpreter path because they do not run inside an activated shell.

## Scheduled jobs

Jobs the scheduler installer (`manage_job_schedules.py`) can register. Optional
entries are installed only when their time flag is provided.

| Job | Entrypoint | Task name | Frequency | Why it exists / how it is used |
|---|---|---|---|---|
| Daily paper trading | `python -m trading.interfaces.runtime.jobs.daily.paper_trading` | `Trading\DailyPaperTrading` | Daily at `--daily-paper-trading-time` | Main daily runtime workflow. Loads runtime-eligible accounts, optionally runs challenger shadow evaluation, executes auto trades, snapshots accounts, compares strategies, and emits logs, artifacts, and notifications. |
| Challenger shadow evaluation | `python -m trading.interfaces.runtime.jobs.daily.challenger_shadow_eval` | `Trading\DailyChallengerShadowEval` | Daily at `--daily-challenger-shadow-eval-time`, or auto-derived before paper trading with `--auto-shadow-eval-from-daily-paper` | Scores challenger strategies against incumbents for runtime-eligible accounts and writes account-level shadow-evaluation artifacts. Disabled unless `--enable-run` or the matching environment enable is set. |
| Daily trader health check | `python -m trading.interfaces.runtime.jobs.daily.trader_health` | `Trading\DailyTraderHealthCheck` | Daily at `--health-check-time` | Checks that the latest daily paper-trading log is recent and contains the success sentinel; can notify on failure. |
| Weekly DB backup | `python -m trading.interfaces.runtime.jobs.maintenance.weekly_db_backup` | `Trading\WeeklyDbBackup` | Weekly at `--weekly-db-backup-time` on `--weekly-db-backup-day-of-week` | Runs the database backup command with a same-week duplicate guard. |

## Manual or indirect jobs

| Job | Entrypoint | Frequency | Why it exists / how it is used |
|---|---|---|---|
| Run auto trades | `python -m trading.interfaces.runtime.jobs.daily.paper_trading.run_auto_trades` | Indirect/manual | Executes per-account signal-driven trades (only when the active strategy signals, up to `--max-trades`). The daily paper-trading job shells out to this module; operators can also run it manually. |
| Burn-in status | `python -m trading.interfaces.runtime.jobs.maintenance.burn_in_status` | Manual/ad hoc daily-style guard | Scans daily paper-trading artifacts to report burn-in stability and go-live readiness (counts consecutive artifacts with top-level `status == "success"`). |
| Reconcile broker fills | `python -m trading.interfaces.runtime.jobs.daily.paper_trading.reconcile_orders` | Indirect/manual | Applies outstanding broker fills to the books for the given accounts. The daily job runs it before each snapshot pass; operators can run it on demand when an async broker fills after a run has finished. No-op for `paper` accounts. |
| Replay daily runs | `python -m trading.interfaces.runtime.jobs.maintenance.replay_daily_runs` | Manual recovery | Finds dates in a range without successful daily paper-trading logs and replays them with `--as-of-date`. |

## Governance jobs

Runnable entrypoints with weekly or monthly duplicate guards; **not** registered by
`manage_job_schedules.py`. Procedures and artifact interpretation live in the
[Governance Review Guide](../runbooks/governance-review.md).

| Job | Entrypoint | Frequency | Why it exists / how it is used |
|---|---|---|---|
| W1 weekly leaderboard | `python -m trading.interfaces.runtime.jobs.governance.weekly.w1_leaderboard` | Weekly dedup guard | Ranks account books by recent performance, default 30-day window, for governance review. |
| W2 weekly promotion review | `python -m trading.interfaces.runtime.jobs.governance.weekly.w2_promotion_review` | Weekly dedup guard | Produces promotion/retirement readiness review for runtime-eligible accounts. |
| W3 weekly allocation review | `python -m trading.interfaces.runtime.jobs.governance.weekly.w3_allocation_review` | Weekly dedup guard | Compares actual book NAV allocation against target/start-equity ratios and flags drift. |
| M1 monthly risk rebaseline | `python -m trading.interfaces.runtime.jobs.governance.monthly.m1_risk_rebaseline` | Monthly dedup guard | Captures latest risk snapshots per account for operator risk budget review. |
| M2 monthly parameter governance | `python -m trading.interfaces.runtime.jobs.governance.monthly.m2_parameter_governance` | Monthly dedup guard | Inventories each book's active strategy assignment and effective parameters. |
| M3 monthly performance audit | `python -m trading.interfaces.runtime.jobs.governance.monthly.m3_performance_audit` | Monthly dedup guard | Runs a longer-horizon book performance audit, default 90 days. |

## Running jobs directly

The direct job scripts are the source of truth — run the job you want directly, and use
`manage_job_schedules` only when you need to install or remove scheduler entries.

```sh
# Daily paper trading
python -m trading.interfaces.runtime.jobs.daily.paper_trading --run-source manual


# Weekly DB backup
python -m trading.interfaces.runtime.jobs.maintenance.weekly_db_backup

# Health check
python -m trading.interfaces.runtime.jobs.daily.trader_health --max-age-hours 24
```

## When the daily run trades

The daily paper-trading job is self-contained and can be run by hand at any time:

- **Market-hours gate.** The runtime submits orders only during US regular equity hours
  (09:30–16:00 ET, weekdays, NYSE holidays and early closes honoured — see
  `trading/domain/market_hours.py`). Outside that window the run still completes every other
  step and logs `Market closed: no orders will be submitted`.
- **Pre-trade reconcile + snapshot.** Step `01_mark_book_nav` applies any outstanding broker fills
  and then snapshots every account before the auto-trader runs. The pre-submit gate reconciles book
  equity against the latest equity snapshot and kills the run when that snapshot is missing or older
  than six hours, so the run has to establish it itself rather than depend on a separately scheduled
  snapshot job. Step `08` repeats both afterwards to record end-state equity.
- **No duplicate guard.** Every invocation runs. Repeat runs through the trading day are the
  intended usage — each one reconciles fills, re-snapshots, and trades if the market is open.

## Registering schedules

`manage_job_schedules` writes Windows Task Scheduler entries on Windows. On Linux it auto-detects
systemd and creates systemd timer units; falls back to cron if systemd is unavailable. Pass
`--scheduler cron` or `--scheduler systemd` to override. **Always preview with `--dry-run` first.**

```sh
# Register the core runtime jobs (Linux — generates local/install_trading_timers.sh)
python -m trading.interfaces.runtime.scheduling.manage_job_schedules \
  --daily-paper-trading-time <PRIMARY_HH:MM> \
  --health-check-time <HEALTH_HH:MM> \
  --weekly-db-backup-day-of-week <DAY> \
  --weekly-db-backup-time <BACKUP_HH:MM>

# Then install with sudo (systemd timers require root to write to /etc/systemd/system/)
sudo bash local/install_trading_timers.sh

# Set AC inactivity timeout to 60 min so the machine stays up through the job window
gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-timeout 3600

# Alternatively, auto-derive the shadow-eval time as a lead before daily paper trading
python -m trading.interfaces.runtime.scheduling.manage_job_schedules \
  --daily-paper-trading-time <PRIMARY_HH:MM> \
  --auto-shadow-eval-from-daily-paper --shadow-eval-lead-minutes 20

# Remove previously registered entries (preview with --dry-run first)
python -m trading.interfaces.runtime.scheduling.manage_job_schedules --unregister --dry-run
python -m trading.interfaces.runtime.scheduling.manage_job_schedules --unregister
sudo bash local/uninstall_trading_timers.sh
```

Replace schedule placeholders with private operator values. Store actual installation schedules under
the gitignored `local/operations/` directory, not in tracked documentation.

**Retired entries:** `Trading\DailySnapshot` and `Trading\DailyPaperTradingFallback` were removed,
and `--unregister` does not know either name — a host that had registered them would need them
deleted by hand. Neither was registered on any host when this was checked on 2026-08-01.

The fallback is the one not to reinstate. It re-attempted a missed primary run and relied on the
daily job's duplicate-run guard to no-op when the primary had already succeeded. That guard is gone,
so the entry would now be a *second full run* — reconciling, snapshotting, and trading again if the
market is open at that hour. A missed day is backfilled with `replay_daily_runs` instead. Snapshots
moved into the daily run itself, at steps `01` and `08`.

On Windows, the same registration commands apply with the PowerShell path form
(`.\.venv\Scripts\python.exe -m ...`) plus an explicit `--python .\.venv\Scripts\python.exe`.

### Behavior notes

- `manage_job_schedules.py` is a thin schedule entrypoint; `scheduler_installer.py` handles platform-specific installation.
- On Linux with systemd, the installer generates `local/install_trading_timers.sh` (requires `sudo bash` to apply). Each timer includes `WakeSystem=yes` so the machine wakes from sleep before the job fires. Pass `--no-wake-system` to disable this.
- Pass `--env-file /path/to/.env` to inject secrets via `EnvironmentFile=` in each service unit (systemd only). The file is treated as optional — a missing file does not fail the job. For cron setups, the production runbook documents an equivalent `run-job.sh` wrapper you create on the host.
- `--python` defaults to the venv's python when running inside a venv; override explicitly if needed.
- The challenger shadow-evaluation entry can be installed before it is operator-enabled. It only executes real work when the scheduled command includes `--enable-run` (via `--enable-daily-challenger-shadow-eval`) or the matching environment variable is set. The `--auto-shadow-eval-from-daily-paper` form enables the shadow-eval run automatically.
- Windows Task Scheduler task names default to the `Trading\*` names in the scheduled-jobs table above.

## Configuration

- `src/infrastructure/config/account_trade_caps.json` — per-account trade caps used by the runtime scheduler; supports per-account `min`/`max` trade counts with a `default` fallback.
- Trade universe files live under `src/infrastructure/config/` (default `trade_universe.txt`); pass `--tickers-file` to select a preset. See [src/trading/README.md](../../src/trading/README.md) for universe presets and auto-trading behavior.
