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

Times, days, and args come from the schedule config (the `Config id` column maps a row to its entry
in `job_schedule.json`).

| Job | Config id | Entrypoint | Task name | Frequency | What it does |
|---|---|---|---|---|---|
| Daily paper trading | `daily_paper_trading` | `python -m trading.interfaces.runtime.jobs.daily.paper_trading` | `Trading\DailyPaperTrading` | Weekdays | Main daily workflow: shadow eval, auto trades, snapshots, report, notifications. Runs Monday–Friday; the market-closed path still completes and writes the success sentinel. |
| Challenger shadow evaluation | `daily_challenger_shadow_eval` | `python -m trading.interfaces.runtime.jobs.daily.challenger_shadow_eval` | `Trading\DailyChallengerShadowEval` | Daily | Scores challengers against incumbents per account. No-op without `--enable-run` (set it in the entry's `args`) or `DAILY_CHALLENGER_SHADOW_EVAL_ENABLED=1`. |
| Daily trader health check | `daily_trader_health` | `python -m trading.interfaces.runtime.jobs.daily.trader_health` | `Trading\DailyTraderHealthCheck` | Weekdays | Checks the latest daily log is recent and carries the success sentinel. Runs Monday–Friday to match the trading job, so a weekend does not read as a stale run. |
| Weekly DB backup | `weekly_db_backup` | `python -m trading.interfaces.runtime.jobs.maintenance.weekly_db_backup` | `Trading\WeeklyDbBackup` | Weekly | Database backup with a same-week duplicate guard. |

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

## When a reinstall is needed

The scheduler runs `python -m <module>`. It loads the current code on every run. So a change to a
job's Python code takes effect on the next scheduled run with **no reinstall**.

Re-register only when the *registration* itself changes:

- a schedule time or day
- a job's command arguments
- the set of jobs (add or remove one)
- the task name or the Python interpreter path

Two related changes are not a schedule reinstall: a new dependency needs `pip install`, and a new
migration needs to be applied. See the [Production Runtime Host runbook](../runbooks/production-runtime-host.md#24-pull-onto-the-production-host).

## Registering schedules

### The schedule config

The schedule is defined in one JSON file, so a change is one file edit plus one apply command. You
do not uninstall first. The tracked template is
[`src/infrastructure/config/job_schedule.example.json`](../../src/infrastructure/config/job_schedule.example.json).
Copy it to `job_schedule.json` in the same folder (gitignored, so real times stay private — the
`.env` / `.env.example` pattern) and set real times.

Each entry names a job by its `id` (from the catalog in
`src/trading/interfaces/runtime/scheduling/job_catalog.py`) and supplies the `time`, an optional
`day_of_week` for a weekly job, optional `args`, and `enabled`. The module path and log file come
from the catalog, so they cannot be mistyped in the config. The config file is the **only** way to
register jobs; there are no per-job command flags.

The file is the source of truth. An apply registers every enabled job and removes every job that is
disabled or absent, so the host matches the file. `--config` defaults to that `job_schedule.json`
under `src/infrastructure/config/`, so it can be omitted when you use that path:

```sh
# Preview first (prints the actions, changes nothing).
python -m trading.interfaces.runtime.scheduling.manage_job_schedules --dry-run

# Apply.
python -m trading.interfaces.runtime.scheduling.manage_job_schedules
```

Check the host against the file at any time. The status report exits `0` in sync, `1` on drift, and
`2` when installed state cannot be read (a systemd target queried off the host):

```sh
python -m trading.interfaces.runtime.scheduling.manage_job_schedules --status
```

### Backend selection

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
# Register from the config (Linux — generates local/install_trading_timers.sh)
python -m trading.interfaces.runtime.scheduling.manage_job_schedules

# Then install with sudo (systemd timers require root to write to /etc/systemd/system/)
sudo bash local/install_trading_timers.sh

# Set AC inactivity timeout to 60 min so the machine stays up through the job window
gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-timeout 3600

# Remove every catalog entry (preview with --dry-run first)
python -m trading.interfaces.runtime.scheduling.manage_job_schedules --unregister --dry-run
python -m trading.interfaces.runtime.scheduling.manage_job_schedules --unregister
sudo bash local/uninstall_trading_timers.sh
```

Set the run times in the gitignored `job_schedule.json` under `src/infrastructure/config/`, not in
tracked documentation. To change a job's time, day, or args, edit that file and re-apply.

On Windows, the same commands apply with the PowerShell path form
(`.\.venv\Scripts\python.exe -m ...`) plus an explicit `--python .\.venv\Scripts\python.exe`.

`--unregister` removes every task in the catalog. It does not know the retired
`Trading\DailySnapshot` and `Trading\DailyPaperTradingFallback` names; a host that still has them
registered needs them deleted by hand. Neither was registered anywhere when this was checked on
2026-08-01.

### Behavior notes

- `manage_job_schedules.py` is a thin schedule entrypoint; `scheduler_installer.py` handles platform-specific installation.
- On Linux with systemd, the installer generates `local/install_trading_timers.sh` (requires `sudo bash` to apply). Each timer includes `WakeSystem=yes` so the machine wakes from sleep before the job fires. Pass `--no-wake-system` to disable this.
- Pass `--env-file /path/to/.env` to inject secrets via `EnvironmentFile=` in each service unit (systemd only). The file is treated as optional — a missing file does not fail the job. For cron setups, the production runbook documents an equivalent `run-job.sh` wrapper you create on the host.
- `--python` defaults to the venv's python when running inside a venv; override explicitly if needed.
- The challenger shadow-evaluation entry stays a no-op until it is operator-enabled. Enable it by
  adding `"--enable-run"` to that entry's `args` in the config, or by setting
  `DAILY_CHALLENGER_SHADOW_EVAL_ENABLED=1` in the job environment.
- Windows Task Scheduler task names are the `Trading\*` names in the scheduled-jobs table above.
- Windows tasks are registered with `-StartWhenAvailable`, `-AllowStartIfOnBatteries`,
  `-DontStopIfGoingOnBatteries`, and (unless `--no-wake-system`) `-WakeToRun`. These match the
  systemd `Persistent=true` and `WakeSystem=yes` behavior: a missed start runs once the machine is
  back, the task runs off AC, and the machine wakes from sleep before the run. Software cannot start
  a machine that is fully powered off.

## Configuration

- Account trade caps come from the daily paper-trading job's own flags: `--primary-accounts` with `--primary-max-trades` / `--other-max-trades`, and `--account-trade-caps` for per-account overrides. See [backtest-live-divergence.md](backtest-live-divergence.md) for why these do not currently bind.
- The daily auto-trading run derives its fetch universe from `books.trade_symbols` across the books it trades; `--tickers-file` overrides that with an explicit ticker file. Universe names under `src/infrastructure/config/trade_universes/` are a write-time shorthand only. See [src/trading/README.md](../../src/trading/README.md) for auto-trading behavior.
</content>
</invoke>
