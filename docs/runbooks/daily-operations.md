# Daily Operations Runbook

Type: runbook
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-06-16
Purpose: Procedures for monitoring and recovering the daily IBKR Paper Autonomy workflow including completion checklist and artifact inspection.
Related: [Burn-In Protocol](burn_in_protocol.md), [Broker Integration](../reference/notes-broker-integration.md)

Procedures for monitoring and recovering the daily IBKR Paper Autonomy workflow.

## Scheduled job

The daily paper-trading job runs once per trading day via Windows Task Scheduler (or cron on Linux).

**Entrypoint:**
```
python -m trading.interfaces.runtime.jobs.daily.paper_trading
```

**Expected run window:** configured in `manage_job_schedules`; fallback task fires if the primary misses its window.

---

## Normal daily checklist

1. **Confirm run completed** — check for today's complete sentinel:
   ```bash
   grep "COMPLETE" local/logs/daily_paper_trading_$(date +%Y%m%d)_*.log
   ```
   Expected: `COMPLETE: Daily paper trading run succeeded.`

2. **Inspect today's artifact** — review the JSON run report:
   ```bash
   cat local/exports/daily_paper_trading/daily_paper_trading_$(date +%Y%m%d)_*.json | python -m json.tool
   ```
   Check: `status == "ok"`, all `step_results` entries show `status: ok` or `status: skipped`.

3. **Review daily operator report** — step 10 artifact section contains per-account sleeve performance, risk violations, and rotation decisions.

---

## DAG step reference

| Step ID | Purpose |
|---|---|
| `00_ingest_market_and_account` | Load market data and account state |
| `01_mark_sleeve_nav` | Mark sleeve NAV (handled by snapshot/reconciliation) |
| `02_run_signals_all_strategies` | Challenger shadow evaluation (if enabled) |
| `03_score_incumbent_vs_challengers` | Score strategies |
| `04_rotation_decision` | Evaluate and apply sleeve rotation |
| `05_build_position_targets_by_sleeve` | Build position targets |
| `06_pretrade_risk_gate` | Pre-trade risk gate evaluation |
| `07_submit_ibkr_orders` | Submit orders to IBKR auto-trader |
| `08_reconcile_fills_update_ledgers` | Reconcile fills and update ledgers |
| `09_postclose_metrics_and_attribution` | Compute daily metrics and attribution |
| `10_emit_report_and_alerts` | Build operator report and send alerts |

---

## Failure recovery

### Run failed (non-zero exit)

1. Check `status` and `failed_step` in the artifact JSON.
2. Read the log file for the error detail:
   ```bash
   cat local/logs/daily_paper_trading_$(date +%Y%m%d)_*.log | grep -A 5 "ERROR\|FAIL"
   ```
3. Fix the underlying issue (connectivity, data freshness, configuration).
4. Re-run with `--force-run`:
   ```bash
   .venv/bin/python -m trading.interfaces.runtime.jobs.daily.paper_trading --force-run
   ```

### Run did not execute (scheduler missed)

1. Verify no log file exists for the expected date:
   ```bash
   ls local/logs/daily_paper_trading_$(date +%Y%m%d)_*.log
   ```
2. Replay via the backfill tool:
   ```bash
   .venv/bin/python -m trading.interfaces.runtime.jobs.maintenance.replay_daily_runs \
       --from-date YYYY-MM-DD --to-date YYYY-MM-DD
   ```
3. Use `--dry-run` first to confirm which dates are missing across a range:
   ```bash
   .venv/bin/python -m trading.interfaces.runtime.jobs.maintenance.replay_daily_runs \
       --from-date 2026-05-01 --to-date 2026-05-07 --dry-run
   ```

### Kill switch triggered

If `kill_switch_triggered: true` appears in the daily operator report or the M1 risk rebaseline:

1. Identify the triggering account from the report's `account_reports` section.
2. Review `portfolio_risk_snapshots` for that account:
   ```bash
   .venv/bin/python -m trading.interfaces.cli.main risk-snapshot --account <name>
   ```
3. Investigate the cause (data staleness, reconciliation mismatch, exposure breach).
4. Resolve and reset the kill switch via the admin interface before the next scheduled run.

---

## Log and artifact locations

| Type | Path |
|---|---|
| Run logs | `local/logs/daily_paper_trading_{YYYYMMDD}_{HHMMSS}.log` |
| Run artifacts | `local/exports/daily_paper_trading/daily_paper_trading_{YYYYMMDD}_{HHMMSS}.json` |
| Startup log | `local/logs/daily_paper_trading_startup_{YYYYMMDD}.log` |
| Governance artifacts | `local/artifacts/{job}_{tag}_{YYYYMMDD}_{HHMMSS}.json` |
| Burn-in status artifacts | `local/artifacts/check_burn_in_status_{YYYYMMDD}_{HHMMSS}.json` |

All `local/` paths are gitignored. Back up `local/exports/` and `local/logs/` as part of the weekly DB backup schedule.

---

## Webhook notifications

Set `TRADING_RUNTIME_ALERT_WEBHOOK_URL` to receive webhook notifications on failure.
Pass `--notify-on-success` to also receive success notifications.

---

## Health check

The `check_daily_trader_health` job validates that a recent successful run artifact exists within the configured `--max-age-hours` window:
```bash
.venv/bin/python -m trading.interfaces.runtime.jobs.daily.trader_health
```
