---
name: estimate-risk
description: Estimates the blast radius and risk of a proposed schema migration — rows affected, index needs, backfill requirements, and backtest impact.
---

# Estimate Migration Risk

## Workflow

1. **Row count impact** — how many rows does this table currently hold? A `DEFAULT` backfill on a large table is fast in SQLite but worth confirming.

2. **Backfill requirement** — does the new column need historical rows populated? If `post_sql` is a `UPDATE ... SET column = <value> WHERE column IS NULL`, flag it as a backfill and estimate scope.

3. **Index need** — will this column be used in `WHERE`, `JOIN`, or `ORDER BY` queries? If yes, an index should be created alongside the migration. Check existing query patterns.

4. **Backward compatibility** — does any existing query, service, or repository SELECT * or rely on column order? SQLite adds columns at the end; named column access is safe, positional access is not.

5. **Backtest impact** — does this column appear in any backtesting query, report payload, or leaderboard metric? If so, historical backtest results may need re-evaluation.
   - Check `src/trading/backtesting/` for references to the affected table.
   - Check `apps/paper_trading_web/backend/` for report payloads that query this table.

6. **Rollback complexity** — every revision has a `downgrade()`, but lossy downgrades recover shape only; data comes back from the automatic pre-upgrade backup. Note which applies before the revision runs.

## Output

```
Table:               <table_name>
Estimated rows:      <count or "unknown — check manually">
Backfill required:   Yes / No
Index recommended:   Yes (<column> on <table>) / No
Backward compatible: Yes / No (explain if No)
Backtest impact:     None / Possible — check src/trading/backtesting/<area>
Rollback complexity: Low (no data change) / Medium (backfill) / High (table recreation needed)

Risk level: LOW / MEDIUM / HIGH
Proceed recommendation: <one sentence>
```

## Repo references

- `src/infrastructure/database/alembic/versions/`
- `src/trading/backtesting/`
- `apps/paper_trading_web/backend/`
