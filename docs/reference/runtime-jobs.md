# Runtime Jobs Reference

Type: notes
Status: Active
Created: 2026-06-25
Last Reviewed: 2026-08-02
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

| Job | Entrypoint | Task name | Frequency | What it does |
|---|---|---|---|---|
| Daily paper trading | `python -m trading.interfaces.runtime.jobs.daily.paper_trading` | `Trading\DailyPaperTrading` | Daily at `--daily-paper-trading-time` | Main daily workflow: shadow eval, auto trades, snapshots, report, notifications. |
| Challenger shadow evaluation | `python -m trading.interfaces.runtime.jobs.daily.challenger_shadow_eval` | `Trading\DailyChallengerShadowEval` | Daily at `--daily-challenger-shadow-eval-time`, or auto-derived before paper trading with `--auto-shadow-eval-from-daily-paper` | Scores challengers against incumbents per account. No-op without `--enable-run` or `DAILY_CHALLENGER_SHADOW_EVAL_ENABLED=1`. |
| Daily trader health check | `python -m trading.interfaces.runtime.jobs.daily.trader_health` | `Trading\DailyTraderHealthCheck` | Daily at `--health-check-time` | Checks the latest daily log is recent and carries the success sentinel. |
| Weekly DB backup | `python -m trading.interfaces.runtime.jobs.maintenance.weekly_db_backup` | `Trading\WeeklyDbBackup` | Weekly at `--weekly-db-backup-time` on `--weekly-db-backup-day-of-week` | Database backup with a same-week duplicate guard. |

## Manual or indirect jobs

| Job | Entrypoint | Frequency | What it does |
|---|---|---|---|
| Run auto trades | `python -m trading.interfaces.runtime.jobs.daily.paper_trading.run_auto_trades` | Indirect/manual | Per-account signal-driven trades, up to `--max-trades`. The daily job shells out to it. |
| Burn-in status | `python -m trading.interfaces.runtime.jobs.maintenance.burn_in_status` | Manual/ad hoc | Counts consecutive successful daily artifacts to report go-live readiness. |
| Reconcile broker fills | `python -m trading.interfaces.runtime.jobs.daily.paper_trading.reconcile_orders` | Indirect/manual | Applies outstanding broker fills to the books. No-op for `paper` accounts. |
| Replay daily runs | `python -m trading.interfaces.runtime.jobs.maintenance.replay_daily_runs` | Manual recovery | Replays dates in a range that have no successful daily log. |

## Governance jobs

Runnable entrypoints with weekly or monthly duplicate guards; **not** registered by
`manage_job_schedules.py`. Procedures and artifact interpretation live in the
[Governance Review Guide](../runbooks/governance-review.md).

| Job | Entrypoint | Frequency | What it does |
|---|---|---|---|
| W1 weekly leaderboard | `python -m trading.interfaces.runtime.jobs.governance.weekly.w1_leaderboard` | Weekly dedup guard | Ranks account books by recent performance (default 30 days). |
| W2 weekly promotion review | `python -m trading.interfaces.runtime.jobs.governance.weekly.w2_promotion_review` | Weekly dedup guard | Promotion/retirement readiness per runtime-eligible account. |
| W3 weekly allocation review | `python -m trading.interfaces.runtime.jobs.governance.weekly.w3_allocation_review` | Weekly dedup guard | Flags book NAV drift against target/start-equity ratios. |
| M1 monthly risk rebaseline | `python -m trading.interfaces.runtime.jobs.governance.monthly.m1_risk_rebaseline` | Monthly dedup guard | Captures latest risk snapshots per account for budget review. |
| M2 monthly parameter governance | `python -m trading.interfaces.runtime.jobs.governance.monthly.m2_parameter_governance` | Monthly dedup guard | Inventories each book's active strategy and effective parameters. |
| M3 monthly performance audit | `python -m trading.interfaces.runtime.jobs.governance.monthly.m3_performance_audit` | Monthly dedup guard | Longer-horizon book performance audit (default 90 days). |

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

The daily run is self-contained and can be started by hand at any time. It submits orders only during
US regular equity hours and otherwise completes every other step; it snapshots accounts itself rather
than depending on a separate job; and it skips a date that already succeeded. Pass `--force-run` for a
deliberate re-run — that is a second full trading pass, not a retry. The reasoning behind the guard
and the snapshot placement is in the `paper_trading` package docstring and `workflow.py`.

## Registering schedules

By default `manage_job_schedules` follows the host: Windows Task Scheduler entries on Windows, and
on Linux systemd timer units, falling back to cron if systemd is unavailable. **Always preview with
`--dry-run` first.**

`--scheduler systemd` is honoured on any host, so the timer and service units can be reviewed from a
Windows dev machine with `--scheduler systemd --dry-run` — the systemd path writes a script and
installs nothing. Note that paths, `User=`, and the interpreter come from the *invoking* host, so
what you get on Windows is a structural preview — the right units with the right `OnCalendar`
expressions, not a file to copy across. Register on the production host itself.

`--scheduler cron` still needs a host with `crontab`, because it merges into that machine's existing
table rather than emitting a file.

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

On Windows, the same registration commands apply with the PowerShell path form
(`.\.venv\Scripts\python.exe -m ...`) plus an explicit `--python .\.venv\Scripts\python.exe`.

`--unregister` does not know the retired `Trading\DailySnapshot` and `Trading\DailyPaperTradingFallback`
names; a host that still has them registered needs them deleted by hand. Neither was registered
anywhere when this was checked on 2026-08-01.

### Behavior notes

- `manage_job_schedules.py` is a thin schedule entrypoint; `scheduler_installer.py` handles platform-specific installation.
- On Linux with systemd, the installer generates `local/install_trading_timers.sh` (requires `sudo bash` to apply). Each timer includes `WakeSystem=yes` so the machine wakes from sleep before the job fires. Pass `--no-wake-system` to disable this.
- Pass `--env-file /path/to/.env` to inject secrets via `EnvironmentFile=` in each service unit (systemd only). The file is treated as optional — a missing file does not fail the job. For cron setups, the production runbook documents an equivalent `run-job.sh` wrapper you create on the host.
- `--python` defaults to the venv's python when running inside a venv; override explicitly if needed.
- The challenger shadow-evaluation entry can be installed before it is operator-enabled. `--enable-daily-challenger-shadow-eval` appends `--enable-run` to the scheduled command; `--auto-shadow-eval-from-daily-paper` does so automatically.
- Windows Task Scheduler task names default to the `Trading\*` names in the scheduled-jobs table above.

## Configuration

- Account trade caps come from the daily paper-trading job's own flags: `--primary-accounts` with `--primary-max-trades` / `--other-max-trades`, and `--account-trade-caps` for per-account overrides. See [backtest-live-divergence.md](backtest-live-divergence.md) for why these do not currently bind.
- The daily auto-trading run derives its fetch universe from the `trade_universes` of the books it trades; `--tickers-file` overrides that with an explicit ticker file. Named universe files live under `src/infrastructure/config/trade_universes/`. See [src/trading/README.md](../../src/trading/README.md) for auto-trading behavior.
</content>
</invoke>
