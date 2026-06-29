# Burn-In Protocol

Type: runbook
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-06-16
Purpose: Define the shadow period, stability thresholds, and go-live checklist for signing off new strategies for autonomous trading.
Related: [Runtime Operations](runtime-operations.md), [Governance Review Guide](governance-review.md), [Broker Integration](../reference/broker-integration.md)

Defines the shadow period, stability thresholds, and go-live checklist for the IBKR Paper Autonomy system.

## Purpose

Before enabling fully autonomous live trading, the system must demonstrate stability across a defined burn-in window. This protocol defines the criteria and the process for signing off on go-live.

---

## Phases

### Phase 1 — Shadow period

The system runs daily in paper mode with real IBKR Paper broker credentials. No real capital is at risk. All decisions and trades are executed in the paper account.

**Duration:** minimum 10 consecutive trading days with no critical failures.

**What to monitor daily:**
- DAG completion (all steps ok or skipped, no `status: failed`)
- Kill switch state (`kill_switch_triggered: false` in operator report)
- Reconciliation health (no ledger mismatch errors in log)
- Order submission success (step `07_submit_ibkr_orders` completes without retry exhaustion)

### Phase 2 — Stability evaluation

Run the burn-in status checker after the shadow period:
```bash
.venv/bin/python -m trading.interfaces.runtime.jobs.maintenance.burn_in_status --force-run
```

Evaluate the output artifact at `local/artifacts/check_burn_in_status_*.json`.

**Default stability thresholds:**

| Metric | Threshold | Flag |
|---|---|---|
| Consecutive successful days | ≥ 10 | `--min-consecutive-days` |
| Failed-run rate over window | ≤ 0% | `--max-failure-rate-pct` |
| Window scanned | last 30 days | `--window-days` |

`ready_for_live: true` in the artifact means both thresholds are met.

**To apply tighter thresholds:**
```bash
.venv/bin/python -m trading.interfaces.runtime.jobs.maintenance.burn_in_status \
    --min-consecutive-days 20 \
    --max-failure-rate-pct 5.0 \
    --window-days 60 \
    --force-run
```

### Phase 3 — Go-live checklist sign-off

Before enabling autonomous mode, an operator must verify all items below.

---

## Go-live checklist

### Infrastructure

- [ ] Scheduler tasks are registered and verified (`manage_job_schedules --dry-run`)
- [ ] Fallback task fires within the backup window if primary is missed
- [ ] Webhook notification URL is configured (`TRADING_RUNTIME_ALERT_WEBHOOK_URL`)
- [ ] DB backup is scheduled weekly (`weekly_db_backup`)
- [ ] `local/logs/` and `local/exports/` are included in backup scope

### System health

- [ ] `check_burn_in_status` returns `ready_for_live: true`
- [ ] No kill switch events in the burn-in window
- [ ] All sleeve NAV balances reconcile with broker account state
- [ ] No open promotion review requests that need resolution

### Risk controls

- [ ] Risk gate thresholds reviewed and set for each account
- [ ] Max gross/net exposure limits are appropriate for account sizes
- [ ] Daily loss stop levels confirmed
- [ ] Kill switch reset procedure documented and tested

### Governance

- [ ] W1 leaderboard artifact reviewed — no unexpected strategy rank reversals
- [ ] W2 promotion review artifact reviewed — no stale retirement-risk strategies
- [ ] W3 allocation review artifact reviewed — sleeve drift within acceptable range
- [ ] M1 risk rebaseline reviewed for baseline establishment

### Sign-off

- [ ] Operator name: ___________________________
- [ ] Date: ___________________________
- [ ] Burn-in artifact path: `local/artifacts/check_burn_in_status_*.json`
- [ ] Consecutive successes at sign-off: _____ / _____ required

---

## Handling failures during burn-in

Any critical failure during the shadow period **resets the consecutive success counter**. The failure must be:

1. Investigated and root-caused (see [runtime-operations.md](runtime-operations.md))
2. Resolved and validated
3. Documented in the burn-in log (append a note to `local/artifacts/burn_in_notes.txt`)

The consecutive count restarts from the next successful run.

---

## Promotion gate to autonomous mode

The system transitions to autonomous mode when:

1. `check_burn_in_status` returns `ready_for_live: true`
2. All go-live checklist items are checked off by an operator
3. Any live-trading configuration flags are enabled per the broker integration guide

Until all three conditions are met, the system remains in paper mode.
