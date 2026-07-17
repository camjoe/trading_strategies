# Governance Review Guide

Type: runbook
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-07-13
Purpose: Procedures for running and interpreting the read-only weekly and monthly governance jobs that produce review artifacts.
Related: [Runtime Jobs Reference](../reference/runtime-jobs.md), [Runtime Operations](runtime-operations.md), [Burn-In Protocol](burn-in-protocol.md), [Strategy Catalog](../reference/strategies.md)

Procedures for interpreting the weekly and monthly governance jobs. For the complete job catalog,
scheduling notes, and entrypoint inventory, see the [Runtime Jobs Reference](../reference/runtime-jobs.md).

## Overview

Governance jobs produce read-only operator review artifacts. They do not modify trading state. Each job has a dedup guard — running it twice in the same week or month is a no-op unless `--force-run` is passed.

Artifacts land in `local/artifacts/` with naming `{job}_{tag}_{YYYYMMDD}_{HHMMSS}.json`.

---

## Weekly jobs

Run each of the three weekly jobs after Friday's close or over the weekend.

### W1 — Strategy parameter leaderboard

Ranks books by 30-day risk-adjusted performance score.

```bash
.venv/bin/python -m trading.interfaces.runtime.jobs.governance.weekly.w1_leaderboard
```

**Key fields in artifact:**
- `books[].rank` — performance rank within the account (1 = best)
- `books[].avg_risk_adjusted_score` — primary ranking signal
- `books[].avg_return_pct` — average daily return over window
- `books[].max_drawdown_pct` — worst drawdown in window

**When to act:**
- If a book holds rank 1 consistently, use W2 and the promotion review lifecycle to decide whether it is a promotion candidate
- If a book stays at the bottom for multiple weeks, flag it for W2 retirement review

---

### W2 — Promotion / retirement review

Reports promotion readiness and any blocking violations for each account.

```bash
.venv/bin/python -m trading.interfaces.runtime.jobs.governance.weekly.w2_promotion_review
```

**Key fields in artifact:**
- `ready_for_live` — whether the account's incumbent strategy meets promotion criteria
- `blockers` — list of reasons blocking promotion
- `books[].book_status` — `active`, `inactive`, or other status

**When to act:**
- `ready_for_live: true` with no blockers → persist a review with `promotion-request-review`, inspect history with `promotion-review-history`, then approve/reject/comment with `promotion-review-action`
- Any book with `book_status` other than `active` for an extended period → investigate

---

### W3 — Allocation reweight review

Compares actual book NAV allocation against original `start_equity` ratios.

```bash
.venv/bin/python -m trading.interfaces.runtime.jobs.governance.weekly.w3_allocation_review
```

**Key fields in artifact:**
- `books[].current_pct` — actual current NAV percentage
- `books[].target_pct` — target percentage based on original start equity
- `books[].drift_pct` — current minus target
- `books[].reweight_suggested` — true when `|drift_pct| >= threshold` (default 5%)

**When to act:**
- Any book with `reweight_suggested: true` → review whether drift is driven by performance (acceptable) or by an accounting error (investigate); this job does not rebalance automatically

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
- `books[].strategy_name` — active strategy (catalog key)
- `books[].primitive` — the code primitive backing it
- `books[].params` — effective knobs (primitive defaults with catalog `params_json` layered on top)

**When to act:**
- Compare params against the ranges defined in the strategy documentation
- Any assigned book whose strategy does not resolve to a code primitive (`params` null) →
  investigate whether the assignment is correct

---

### M3 — Long-horizon performance audit

90-day compound return, max drawdown, and average hit rate per book.

```bash
.venv/bin/python -m trading.interfaces.runtime.jobs.governance.monthly.m3_performance_audit
```

**Key fields in artifact:**
- `books[].cumulative_return_pct` — compound return over audit window
- `books[].max_drawdown_pct` — worst drawdown over audit window
- `books[].avg_hit_rate` — average win rate
- `books[].total_trades` — total trade count

**Changing the audit window:**
```bash
.venv/bin/python -m trading.interfaces.runtime.jobs.governance.monthly.m3_performance_audit \
    --audit-window-days 60
```

**When to act:**
- Negative `cumulative_return_pct` for multiple months → open a retirement review
- Low `avg_hit_rate` (< 0.4) with high `total_trades` → review strategy signal quality; this job is an audit signal, not an automatic retirement action

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
