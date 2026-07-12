---
name: db-migration
description: Manages SQLite schema migrations for the trading database — creating, validating, estimating risk, generating rollback strategies, and planning FK cascade/table-rebuild changes. Use when asked to add a column, validate a migration, assess schema change risk, change foreign-key actions, plan account-deletion cascades, or plan a rollback.
invoker: any
---

# DB Migration

Handles the full lifecycle of a schema change: design → validate → risk check → rollback plan.
For a complete schema change, run all four tasks in order unless asked for a specific one.

## Choose a task

| Task | Use when | Reference |
|---|---|---|
| Create migration | Adding a new column or table to the schema | [create-migration.md](create-migration.md) |
| SQLite table rebuild | Changing FK actions, constraints, or other SQLite schema details that cannot use additive column migrations | [sqlite-table-rebuild.md](sqlite-table-rebuild.md) |
| Validate migration | Checking a proposed migration for safety and correctness | [validate-migration.md](validate-migration.md) |
| Estimate risk | Assessing blast radius, index needs, and backtest impact | [estimate-risk.md](estimate-risk.md) |
| Generate rollback | Planning how to undo a migration safely | [generate-rollback.md](generate-rollback.md) |

## Hard rules (apply to all tasks)

- Migrations are **additive and idempotent** — no DROP, no rename, no type changes without an explicit plan.
- Every `NOT NULL` column **must** have a `DEFAULT`.
- New migrations are **appended** to the tuple — never reorder deployed migrations.
- FK action changes require a SQLite table rebuild; use the table-rebuild reference before editing DDL.
- `post_sql` that updates or deletes existing rows requires explicit human review.
- Backup required before any destructive data-op.

## Repo references

- `src/infrastructure/database/schema.py`
- `src/infrastructure/database/migrations.py`
- `src/infrastructure/database/init.py`
- `scripts/data_ops/audit_foreign_keys.py`
- `scripts/data_ops/build_database_diagram_viewer.py`
- `docs/reference/account-deletion-cascade-proposal.md`
- `docs/reference/database-diagram-viewer.html`
- `docs/architecture/architecture-conventions.md`
