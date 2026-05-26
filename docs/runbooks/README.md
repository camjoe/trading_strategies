# Operator Runbooks

## Overview

Operational procedures for the IBKR Paper Autonomy trading system. Use these runbooks to monitor
daily runs, manage the burn-in period, and conduct weekly/monthly governance reviews.

## Contents

| Runbook | When to use |
|---|---|
| [daily_operations.md](daily_operations.md) | Daily monitoring, failure recovery, log inspection |
| [burn_in_protocol.md](burn_in_protocol.md) | Burn-in period definition, stability thresholds, go-live checklist |
| [governance_review_guide.md](governance_review_guide.md) | Weekly and monthly governance job procedures |

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
