---
name: db-migration
description: Manages SQLite schema migrations for the trading database — creating, validating, estimating risk, and generating rollback strategies. Typically invoked by the DB Migration Steward agent. Use when asked to add a column, validate a migration, assess schema change risk, or plan a rollback.
---

# DB Migration

Handles the full lifecycle of a schema change: design → validate → risk check → rollback plan.

Typically invoked by the **DB Migration Steward** agent (`migrate:` shortcut). Can also be used directly for specific sub-tasks.

## Choose a task

| Task | Use when | Reference |
|---|---|---|
| Create migration | Adding a new column or table to the schema | [create-migration.md](create-migration.md) |
| Validate migration | Checking a proposed migration for safety and correctness | [validate-migration.md](validate-migration.md) |
| Estimate risk | Assessing blast radius, index needs, and backtest impact | [estimate-risk.md](estimate-risk.md) |
| Generate rollback | Planning how to undo a migration safely | [generate-rollback.md](generate-rollback.md) |

## Hard rules (apply to all tasks)

- Migrations are **additive and idempotent** — no DROP, no rename, no type changes without an explicit plan.
- Every `NOT NULL` column **must** have a `DEFAULT`.
- New migrations are **appended** to the tuple — never reorder deployed migrations.
- `post_sql` that updates or deletes existing rows requires explicit human review.
- Backup required before any destructive data-op.

## Repo references

- `trading/database/db_schema.py`
- `trading/database/db_migrations.py`
- `trading/database/db_init.py`
- `.github/BOT_ARCHITECTURE_CONVENTIONS.md`
