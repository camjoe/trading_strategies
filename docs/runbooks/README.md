# Operator Runbooks

Type: index
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-06-16
Purpose: Index of operational runbooks for the IBKR Paper Autonomy trading system with quick-start commands.
Related: [Runtime Operations](runtime-operations.md), [Production Runtime Host](production-runtime-host.md), [Burn-In Protocol](burn-in-protocol.md), [Governance Review Guide](governance-review.md)

## Overview

Operational procedures for the IBKR Paper Autonomy trading system. Use these runbooks to monitor
daily and weekly runtime jobs, manage the burn-in period, and conduct weekly/monthly governance reviews.

## Contents

| Runbook | When to use |
|---|---|
| [production-runtime-host.md](production-runtime-host.md) | One-time Linux host setup + the test-and-deploy workflow that promotes code to it |
| [runtime-operations.md](runtime-operations.md) | Daily + weekly-backup monitoring, failure recovery, log inspection |
| [burn-in-protocol.md](burn-in-protocol.md) | Burn-in period definition, stability thresholds, go-live checklist |
| [governance-review.md](governance-review.md) | Weekly and monthly governance job procedures |
| [sleeve-retirement-db-migration.md](sleeve-retirement-db-migration.md) | **One-time**: migrate an existing DB off the legacy sleeve tables after the sleeve-retirement branch deploys |
| [book-rotation-cutover.md](book-rotation-cutover.md) | **One-time**: sync book rotation scheduling + default-book assignments after the execution-mode-collapse branch deploys |

## Quick Start

### Check today's run status
```bash
# Check whether today's daily run succeeded
ls local/logs/daily_paper_trading_$(date +%Y%m%d)_*.log
grep "COMPLETE" local/logs/daily_paper_trading_$(date +%Y%m%d)_*.log
```

### Replay a missed date
```bash
.venv/bin/python -m trading.interfaces.runtime.jobs.maintenance.replay_daily_runs \
    --from-date YYYY-MM-DD --to-date YYYY-MM-DD
```

### Check burn-in status
```bash
.venv/bin/python -m trading.interfaces.runtime.jobs.maintenance.burn_in_status --force-run
```
