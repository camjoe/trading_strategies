# Operator Runbooks

Type: index
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-06-16
Purpose: Index of operational runbooks for the IBKR Paper Autonomy trading system with quick-start commands.
Related: [Runtime Operations](runtime-operations.md), [Burn-In Protocol](burn-in-protocol.md), [Governance Review Guide](governance-review.md)

## Overview

Operational procedures for the IBKR Paper Autonomy trading system. Use these runbooks to monitor
daily and weekly runtime jobs, manage the burn-in period, and conduct weekly/monthly governance reviews.

## Contents

| Runbook | When to use |
|---|---|
| [runtime-operations.md](runtime-operations.md) | Daily + weekly-backup monitoring, failure recovery, log inspection |
| [burn-in-protocol.md](burn-in-protocol.md) | Burn-in period definition, stability thresholds, go-live checklist |
| [governance-review.md](governance-review.md) | Weekly and monthly governance job procedures |

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
