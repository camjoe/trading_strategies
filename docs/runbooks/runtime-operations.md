# Runtime Operations Runbook

Type: runbook
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-07-13
Purpose: Procedures for monitoring and recovering the runtime trading jobs — the daily paper-trading workflow, daily supporting jobs, and weekly database backup — including completion checks and artifact inspection.
Related: [Runtime Jobs Reference](../reference/runtime-jobs.md), [Governance Review Guide](governance-review.md), [Burn-In Protocol](burn-in-protocol.md), [Broker Integration](../reference/broker-integration.md)

Procedures for monitoring and recovering the runtime trading jobs. This runbook covers the daily
paper-trading workflow, supporting daily jobs, and weekly database backup; the weekly/monthly
**governance** jobs are covered in the [Governance Review Guide](governance-review.md), and the
**burn-in** period in the [Burn-In Protocol](burn-in-protocol.md). For how to *run or schedule* any
job (rather than monitor it), see the [Runtime Jobs Reference](../reference/runtime-jobs.md).

## Scheduled job

The daily paper-trading job runs once per trading day via the OS scheduler — systemd timers on the
dedicated Linux production host (per [ADR 008](../adr/008-production-runtime-hosting-and-deployment.md)
and the [Production Runtime Host runbook](production-runtime-host.md)); Windows Task Scheduler when
running from a Windows dev machine.

**Entrypoint:**
```
./.venv/bin/python -m trading.interfaces.runtime.jobs.daily.paper_trading
```

**Expected run window:** configured in `manage_job_schedules`. There is one scheduled entry; a missed run is backfilled with `replay_daily_runs` rather than re-attempted automatically.

**Schedule setup:** to register, enable, or remove scheduled jobs (the challenger shadow-eval, health-check, and weekly-backup entries), see the [Runtime Jobs Reference](../reference/runtime-jobs.md#registering-schedules).

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
   Check: top-level `status == "success"`; all `step_results` entries show `status: ok` or `status: skipped`.

3. **Review daily operator report** — step 10 artifact section contains per-account book performance, risk violations, and rotation decisions.

---

## DAG step reference

| Step ID | Purpose |
|---|---|
| `00_ingest_market_and_account` | Ingest market and account context |
| `01_mark_book_nav` | Mark book NAV |
| `02_run_signals_all_strategies` | Run incumbent/challenger strategy signals |
| `03_score_incumbent_vs_challengers` | Score incumbent versus challengers |
| `04_rotation_decision` | Apply rotation decision gates |
| `05_build_position_targets_by_book` | Build position targets by book |
| `06_pretrade_risk_gate` | Apply pretrade risk gate |
| `07_submit_ibkr_orders` | Submit broker orders |
| `08_reconcile_fills_update_ledgers` | Reconcile fills and update ledgers |
| `09_postclose_metrics_and_attribution` | Compute post-close metrics and attribution |
| `10_emit_report_and_alerts` | Emit report and alerts |

---

## Failure recovery

### Run failed (non-zero exit)

1. Check `status` and `failed_step` in the artifact JSON.
2. Read the log file for the error detail:
   ```bash
   cat local/logs/daily_paper_trading_$(date +%Y%m%d)_*.log | grep -A 5 "ERROR\|FAIL"
   ```
3. Fix the underlying issue (connectivity, data freshness, configuration).
4. Re-run — the job has no duplicate guard, so an earlier run today does not block a retry:
   ```bash
   python -m trading.interfaces.runtime.jobs.daily.paper_trading
   ```

### Run did not execute (scheduler missed)

1. Verify no log file exists for the expected date:
   ```bash
   ls local/logs/daily_paper_trading_$(date +%Y%m%d)_*.log
   ```
2. Replay via the backfill tool:
   ```bash
   python -m trading.interfaces.runtime.jobs.maintenance.replay_daily_runs \
       --from-date YYYY-MM-DD --to-date YYYY-MM-DD
   ```
3. Use `--dry-run` first to confirm which dates are missing across a range:
   ```bash
   python -m trading.interfaces.runtime.jobs.maintenance.replay_daily_runs \
       --from-date 2026-05-01 --to-date 2026-05-07 --dry-run
   ```

### Kill switch triggered

If `kill_switch_triggered: true` appears in the daily operator report or the M1 risk rebaseline:

1. Identify the triggering account from the report's `account_reports` section.
2. Review the latest account report/risk state:
   ```bash
   python -m trading.interfaces.cli.main report --account <name>
   python -m trading.interfaces.cli.main portfolio-exposure
   python -m trading.interfaces.cli.main portfolio-concentration
   ```
3. Inspect the daily run artifact, M1 risk rebaseline artifact, or `risk_snapshots` table for the
   kill-switch reason payload.
4. Investigate the cause (data staleness, reconciliation mismatch, exposure breach).
5. Resolve and reset the kill switch via the admin interface before the next scheduled run.

---

## Weekly database backup

The weekly database backup runs via the scheduler entry `Trading\WeeklyDbBackup`.

1. **Confirm this week's backup completed** — check the latest weekly log:
   ```bash
   grep "COMPLETE" local/logs/weekly_db_backup_*.log | tail -1
   ```
2. **Run on demand** if a scheduled run was missed:
   ```bash
   python -m trading.interfaces.runtime.jobs.maintenance.weekly_db_backup
   ```
3. The combined daily paper-trading and weekly backup status is summarized by:
   ```bash
   python -m scripts.check_jobs
   ```

---

## Log and artifact locations

| Type | Path |
|---|---|
| Run logs | `local/logs/daily_paper_trading_{YYYYMMDD}_{HHMMSS}.log` |
| Run artifacts | `local/exports/daily_paper_trading/daily_paper_trading_{YYYYMMDD}_{HHMMSS}.json` |
| Startup log | `local/logs/daily_paper_trading_startup_{YYYYMMDD}.log` |
| Scheduler logs | `local/logs/*_scheduler.log` |
| Governance artifacts | `local/artifacts/{job}_{tag}_{YYYYMMDD}_{HHMMSS}.json` |
| Burn-in status artifacts | `local/artifacts/check_burn_in_status_{YYYYMMDD}_{HHMMSS}.json` |

All `local/` paths are gitignored. Back up `local/exports/` and `local/logs/` as part of the weekly DB backup schedule.

---

## Runtime notifications

Runtime jobs emit events (failure by default; success with `--notify-on-success`/`--notify-on-ok`)
to any configured transport. Both are opt-in and best-effort — an unset transport is skipped, and a
delivery failure is logged to stderr without failing the job. The two transports are independent, so
one failing does not suppress the other.

**Webhook.** Set `TRADING_RUNTIME_ALERT_WEBHOOK_URL` (or pass `--notify-webhook-url`).

**Email (SMTP).** Configured entirely via environment variables; email is sent only when host,
sender, and at least one recipient are all set:

| Variable | Required | Purpose |
|---|---|---|
| `TRADING_RUNTIME_ALERT_SMTP_HOST` | yes | Outgoing SMTP server hostname |
| `TRADING_RUNTIME_ALERT_SMTP_FROM` | yes | From address |
| `TRADING_RUNTIME_ALERT_SMTP_TO` | yes | Recipient(s), comma-separated |
| `TRADING_RUNTIME_ALERT_SMTP_PORT` | no | Submission port (default `587`) |
| `TRADING_RUNTIME_ALERT_SMTP_USERNAME` | no | SMTP login user (omit for an unauthenticated relay) |
| `TRADING_RUNTIME_ALERT_SMTP_PASSWORD` | no | SMTP login password / app password (keep out of source) |
| `TRADING_RUNTIME_ALERT_SMTP_USE_TLS` | no | STARTTLS on unless set to `0`/`false`/`no`/`off` |

Username/password are optional so an unauthenticated local relay works; for a hosted mailbox (e.g.
Gmail or a transactional provider) use the provider's SMTP credentials — an app password, never a
committed secret. Email currently mirrors the webhook's event set; per-transport event filtering is
not yet implemented.

---

## Health check

The `check_daily_trader_health` job validates that a recent successful run artifact exists within the configured `--max-age-hours` window:
```bash
python -m trading.interfaces.runtime.jobs.daily.trader_health
```
