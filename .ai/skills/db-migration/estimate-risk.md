# Estimate Migration Risk

## Workflow

1. **Row count impact** — how many rows does this table currently hold? Adding a column with a
   constant schema default is different from rewriting existing rows; estimate the cost of any
   explicit data update separately.

2. **Backfill requirement** — does the revision run `op.execute("UPDATE ...")` or equivalent SQL
   to populate historical rows? If so, identify the predicate, estimate the affected row count, and
   flag the statement for human review.

3. **Index need** — will this column be used in `WHERE`, `JOIN`, or `ORDER BY` queries? If yes, an index should be created alongside the migration. Check existing query patterns.

4. **Backward compatibility** — does any existing query, service, or repository SELECT * or rely on column order? SQLite adds columns at the end; named column access is safe, positional access is not.

5. **Consumer impact** — search repositories, runtime services, exports, reports, API payloads, and
   backtesting for the affected table or columns. Historical backtest results need re-evaluation
   only when the migration changes their inputs or interpretation.

6. **Rollback complexity** — every revision has a `downgrade()`, but lossy downgrades recover shape
   only. An existing database is backed up before an actual migration; note whether downgrade alone
   is sufficient or backup recovery is required.

## Output

```
Table:               <table_name>
Estimated rows:      <count or "unknown — check manually">
Backfill required:   Yes / No
Index recommended:   Yes (<column> on <table>) / No
Backward compatible: Yes / No (explain if No)
Consumer impact:     None / Possible — list affected runtime, API, export, or backtest surfaces
Rollback complexity: Low (no data change) / Medium (backfill) / High (table recreation needed)

Risk level: LOW / MEDIUM / HIGH
Proceed recommendation: <one sentence>
```

## Repo references

- `src/infrastructure/database/alembic/versions/`
- `src/trading/backtesting/`
- `apps/paper_trading_web/backend/`
