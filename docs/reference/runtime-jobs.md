# Runtime Jobs Reference

Type: notes
Status: Active
Created: 2026-06-25
Last Reviewed: 2026-06-25
Purpose: Catalog of runtime job entrypoints — what each one is, how to invoke it, and how to register it on a scheduler.
Related: [Runtime Operations Runbook](../runbooks/runtime-operations.md), [Governance Review Guide](../runbooks/governance-review.md), [Trading Package Map](../maps/trading-package-map.md)

How to run and schedule the runtime job entrypoints. For the full structural module inventory see
[trading-package-map.md](../maps/trading-package-map.md) (Runtime jobs section); for monitoring and
recovery procedures see the [Runtime Operations Runbook](../runbooks/runtime-operations.md).

All commands run as Python modules from the repository root with the active venv interpreter
(`.venv\Scripts\python` on Windows, `.venv/bin/python` on POSIX).

## Entrypoint catalog

| Entrypoint | What it is |
|---|---|
| `daily/paper_trading.py` | Orchestrates the scheduled daily paper-trading run. |
| `run_auto_trades.py` | Executes per-account simulated trade batches directly; the daily job shells out to this, but operators can also run it standalone. |
| `daily/snapshot.py` | Daily equity snapshot runner with duplicate-run guards and retry. |
| `daily/backtest_refresh.py` | Daily backtest refresh runner with duplicate-run guards, transient-retry handling, and JSON artifacts under `local/exports/daily_backtest_refresh/`. |
| `daily/challenger_shadow_eval.py` | Daily challenger shadow-evaluation runner (off by default; install the entry before enabling it). |
| `daily/trader_health.py` | Verifies recency/health of recent daily runs. |
| `maintenance/weekly_db_backup.py` | Weekly database backup execution. |
| `manage_job_schedules.py` | Single entrypoint that registers/removes scheduler entries for all of the above. |

Weekly and monthly **governance** jobs have their own catalog and procedures in the
[Governance Review Guide](../runbooks/governance-review.md).

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

`manage_job_schedules` writes Windows Task Scheduler entries on Windows. On Linux it auto-detects systemd and creates systemd timer units; falls back to cron if systemd is unavailable. Pass `--scheduler cron` or `--scheduler systemd` to override.

```sh
# Register the core 4 runtime jobs (Linux — generates local/install_trading_timers.sh)
./.venv/bin/python -m trading.interfaces.runtime.jobs.manage_job_schedules \
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
./.venv/bin/python -m trading.interfaces.runtime.jobs.manage_job_schedules \
  --daily-paper-trading-time 13:00 \
  --auto-shadow-eval-from-daily-paper --shadow-eval-lead-minutes 20

# Remove previously registered entries (preview with --dry-run first)
./.venv/bin/python -m trading.interfaces.runtime.jobs.manage_job_schedules --unregister --dry-run
./.venv/bin/python -m trading.interfaces.runtime.jobs.manage_job_schedules --unregister
sudo bash local/uninstall_trading_timers.sh
```

### Behavior notes

- `manage_job_schedules.py` is a thin schedule entrypoint; `scheduler_installer.py` handles platform-specific installation.
- On Linux with systemd, the installer generates `local/install_trading_timers.sh` (requires `sudo bash` to apply). Each timer includes `WakeSystem=yes` so the machine wakes from sleep before the job fires. Pass `--no-wake-system` to disable this.
- `--python` defaults to the venv's python when running inside a venv; override explicitly if needed.
- Snapshot, daily backtest refresh, and challenger shadow-evaluation entries can be installed before they are operator-enabled. They only execute real work when the scheduled command includes `--enable-run` (via `--enable-daily-snapshot` / `--enable-daily-backtest-refresh` / `--enable-daily-challenger-shadow-eval`) or the matching environment variable is set. The `--auto-shadow-eval-from-daily-paper` form enables the shadow-eval run automatically.
- Windows Task Scheduler task names default to `Trading\DailyPaperTrading`, `Trading\DailyPaperTradingFallback`, `Trading\DailyChallengerShadowEval`, `Trading\DailySnapshot`, `Trading\DailyBacktestRefresh`, `Trading\DailyTraderHealthCheck`, and `Trading\WeeklyDbBackup`.

## Configuration

- `src/infrastructure/config/account_trade_caps.json` — per-account trade caps used by the runtime scheduler; supports per-account `min`/`max` trade counts with a `default` fallback.
- Trade universe files live under `src/infrastructure/config/` (default `trade_universe.txt`); pass `--tickers-file` to select a preset. See [src/trading/README.md](../../src/trading/README.md) for universe presets and auto-trading behavior.
