# Trading Runtime Scripts

Operational scripts in this folder are part of trading runtime behavior (scheduler jobs, runtime health checks, and runtime backup scheduling).

## Scope

Use this folder for scripts that:

- Execute or supervise trading runtime flows.
- Are expected to run on schedule (Task Scheduler/cron).
- Read/write runtime artifacts in `local/` as part of trading operations.

Do not place repository workflow scripts here. Those belong in `scripts/`.
Do not place interactive DB admin tools here. Those belong in `dev_tools/`.

## Catalog

- `daily_paper_trading.py`: orchestrates scheduled daily paper-trading run.
- `check_daily_trader_health.py`: verifies recency/health of daily trading runs.
- `daily_snapshot.py`: scheduled snapshot runner with duplicate-run guards and retry.
- `weekly_db_backup.py`: scheduled weekly backup execution.
- `register_weekly_backup.py`: schedule registration helper for weekly backups.
- `account_trade_caps.json`: configuration for per-account trade caps used by runtime scheduler.

## Placement Rules

- Runtime orchestration and runtime checks: `trading/scripts/`
- Repo maintenance and CI workflow helpers: `scripts/`
- DB admin and account maintenance operations: `dev_tools/`
