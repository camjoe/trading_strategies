# Governance Review Guide

Type: runbook
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-06-16
Purpose: Procedures for running and interpreting the read-only weekly and monthly governance jobs that produce review artifacts.
Related: [Runtime Operations](runtime-operations.md), [Burn-In Protocol](burn-in-protocol.md), [Strategy Catalog](../reference/strategies.md)

Procedures for running and interpreting the weekly and monthly governance jobs.

## Overview

Governance jobs produce read-only operator review artifacts. They do not modify trading state. Each job has a dedup guard — running it twice in the same week or month is a no-op unless `--force-run` is passed.

Artifacts land in `local/artifacts/` with naming `{job}_{tag}_{YYYYMMDD}_{HHMMSS}.json`.

---

## Weekly jobs

Run each of the three weekly jobs after Friday's close or over the weekend.

### W1 — Strategy parameter leaderboard

Ranks sleeves by 30-day risk-adjusted performance score.

```bash
.venv/bin/python -m trading.interfaces.runtime.jobs.governance.weekly.w1_leaderboard
```

**Key fields in artifact:**
- `sleeves[].rank` — performance rank within the account (1 = best)
- `sleeves[].avg_risk_adjusted_score` — primary ranking signal
- `sleeves[].avg_return_pct` — average daily return over window
- `sleeves[].max_drawdown_pct` — worst drawdown in window

**When to act:**
- If a sleeve holds rank 1 consistently → consider it for promotion review
- If a sleeve stays at the bottom for multiple weeks → flag for W2 retirement review

---

### W2 — Promotion / retirement review

Reports promotion readiness and any blocking violations for each account.

```bash
.venv/bin/python -m trading.interfaces.runtime.jobs.governance.weekly.w2_promotion_review
```

**Key fields in artifact:**
- `ready_for_live` — whether the account's incumbent strategy meets promotion criteria
- `blockers` — list of reasons blocking promotion
- `sleeves[].sleeve_status` — `active`, `inactive`, or other status

**When to act:**
- `ready_for_live: true` with no blockers → open a promotion review via the CLI
- Any sleeve with `sleeve_status` other than `active` for an extended period → investigate

---

### W3 — Allocation reweight review

Compares actual sleeve NAV allocation against original `start_equity` ratios.

```bash
.venv/bin/python -m trading.interfaces.runtime.jobs.governance.weekly.w3_allocation_review
```

**Key fields in artifact:**
- `sleeves[].current_pct` — actual current NAV percentage
- `sleeves[].target_pct` — target percentage based on original start equity
- `sleeves[].drift_pct` — current minus target
- `sleeves[].reweight_suggested` — true when `|drift_pct| >= threshold` (default 5%)

**When to act:**
- Any sleeve with `reweight_suggested: true` → review whether drift is driven by performance (acceptable) or by an accounting error (investigate)

**Changing the drift threshold:**
```bash
.venv/bin/python -m trading.interfaces.runtime.jobs.governance.weekly.w3_allocation_review \
    --drift-threshold-pct 10.0
```

---

## Monthly jobs

Run monthly jobs at the end of each calendar month.

### M1 — Risk budget rebaseline

Snapshots the current portfolio risk state per account for operator review.

```bash
.venv/bin/python -m trading.interfaces.runtime.jobs.governance.monthly.m1_risk_rebaseline
```

**Key fields in artifact:**
- `kill_switch_triggered` — current kill switch state
- `gross_exposure`, `net_exposure` — portfolio exposure levels
- `drawdown_pct` — current drawdown from peak
- `daily_loss_pct` — daily loss percentage

**When to act:**
- Any account with `kill_switch_triggered: true` → resolve before next trading day
- Drawdown approaching limits → review risk gate thresholds

---

### M2 — Parameter range governance

Inventories all active strategy parameter sets for operator review.

```bash
.venv/bin/python -m trading.interfaces.runtime.jobs.governance.monthly.m2_parameter_governance
```

**Key fields in artifact:**
- `sleeves[].strategy_name` — active strategy
- `sleeves[].param_set_id` — active parameter set ID
- `sleeves[].params` — full parameter dict

**When to act:**
- Compare params against the ranges defined in the strategy documentation
- Any strategy without an active param set → investigate whether the assignment is correct

---

### M3 — Long-horizon performance audit

90-day compound return, max drawdown, and average hit rate per sleeve.

```bash
.venv/bin/python -m trading.interfaces.runtime.jobs.governance.monthly.m3_performance_audit
```

**Key fields in artifact:**
- `sleeves[].cumulative_return_pct` — compound return over audit window
- `sleeves[].max_drawdown_pct` — worst drawdown over audit window
- `sleeves[].avg_hit_rate` — average win rate
- `sleeves[].total_trades` — total trade count

**Changing the audit window:**
```bash
.venv/bin/python -m trading.interfaces.runtime.jobs.governance.monthly.m3_performance_audit \
    --audit-window-days 60
```

**When to act:**
- Negative `cumulative_return_pct` for multiple months → open a retirement review
- Low `avg_hit_rate` (< 0.4) with high `total_trades` → review strategy signal quality

---

## Force-running a governance job

All governance jobs support `--force-run` to bypass the weekly/monthly dedup guard:
```bash
.venv/bin/python -m trading.interfaces.runtime.jobs.governance.weekly.w1_leaderboard --force-run
```

## Scoping to specific accounts

Pass `--accounts` to limit to specific accounts:
```bash
.venv/bin/python -m trading.interfaces.runtime.jobs.governance.weekly.w1_leaderboard \
    --accounts momentum_5k,meanrev_5k
```

## Reading artifacts

All artifacts are pretty-printed JSON in `local/artifacts/`:
```bash
cat local/artifacts/weekly_governance_w1_leaderboard_*.json | python -m json.tool | head -60
```
