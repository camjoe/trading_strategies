# Account Deletion Cascade Proposal

Type: notes
Status: Active
Created: 2026-07-10
Last Reviewed: 2026-07-13
Purpose: Proposed cascade changes and decision dependencies for simplifying account deletion without losing intentional history.
Related: [Database Diagram Viewer](database-diagram-viewer.html), [DB Migration System](db-migration-system.md), [Service/Repository Boundary](../architecture/service-repository-boundary.md)

## Purpose

Use this note to decide which foreign-key relationships should become database-enforced cascades before simplifying account deletion code. It separates safe child-owned cleanup from data-retention decisions that need an explicit product or operator call.

## Current Direction

Keep `trading.services.admin.delete_accounts()` as the account-deletion orchestration boundary while schema cascades are added. The service still owns:

- target account resolution and missing-account behavior
- dry-run count reporting
- transaction boundaries
- backup-before-delete integration through the runtime data-ops CLI
- stable count keys consumed by the UI and CLI

The schema can take over row cleanup only after tests prove that deleting a parent removes the same child rows the service currently deletes explicitly.

## Implemented Child-Owned Cascades

These relationships are child-owned implementation detail. The child row has no useful standalone meaning after the parent row is deleted.

| Relationship | Action | Validation |
|---|---|---|
| `order_fills.order_id` -> `orders.id` | `ON DELETE CASCADE` | Fresh DDL plus legacy table-rebuild migration. |
| `backtest_trades.run_id` -> `backtest_runs.id` | `ON DELETE CASCADE` | Fresh DDL plus legacy table-rebuild migration. |
| `backtest_equity_snapshots.run_id` -> `backtest_runs.id` | `ON DELETE CASCADE` | Fresh DDL plus legacy table-rebuild migration. |
| `promotion_review_events.review_id` -> `promotion_reviews.id` | `ON DELETE CASCADE` | Fresh DDL plus legacy table-rebuild migration. |
| `walk_forward_group_runs.group_id` -> `walk_forward_groups.id` | `ON DELETE CASCADE` | Fresh DDL plus legacy table-rebuild migration. |

## Potential Cascades

These may be correct, but the dependency or retention semantics need a decision first.

| Relationship | Candidate action | Decision dependency | Risk if chosen blindly |
|---|---|---|---|
| `trades.account_id` -> `accounts.id` | `ON DELETE CASCADE` | Are paper trade records account-owned scratch data, or should they remain as account-name-independent execution history? | Account deletion removes trade history with no separate archive path. |
| `backtest_runs.account_id` -> `accounts.id` | `ON DELETE CASCADE` | Should deleting an account remove all research runs created for it? | Research evidence can disappear during account cleanup. |
| `walk_forward_groups.account_id` -> `accounts.id` | `ON DELETE CASCADE` | Should walk-forward summaries be account-owned, or retained as strategy evaluation evidence? | Evaluation history disappears with the account. |
| `walk_forward_group_runs.run_id` -> `backtest_runs.id` | `ON DELETE CASCADE` | Should deleting a backtest run remove its walk-forward membership, or should parent group deletion be the only cascade path? | A run deletion can silently alter walk-forward group composition. |
| `promotion_reviews.account_id` -> `accounts.id` | `ON DELETE CASCADE` | Are promotion reviews operational account state, or audit records that must survive? | Operator approval history disappears. |
| `risk_snapshots.account_id` -> `accounts.id` | `ON DELETE CASCADE` | Are risk snapshots disposable account telemetry, or retained safety evidence? | Safety history disappears. |
| `risk_decisions.account_id` -> `accounts.id` | `ON DELETE CASCADE` | Are risk decisions disposable account telemetry, or retained safety evidence? | Allow/block decision history disappears. |
| `risk_decisions.book_id` -> `books.id` | `ON DELETE SET NULL` or `ON DELETE CASCADE` | If account-level history is retained, should book deletion preserve decisions with `book_id = NULL`? | Cascade can remove safety decisions; `SET NULL` requires nullable semantics to be intentional. |

## Keep As Non-Cascade

These relationships currently look intentionally restrictive or reference shared catalog data.

| Relationship | Current action | Reason to keep |
|---|---|---|
| `rotation_decisions.book_id` -> `books.id` | `ON DELETE RESTRICT` | Rotation decisions are audit history; restriction prevents silent book deletion while decisions exist. |
| `*_strategy_id` -> `strategies.id` | `NO ACTION` | Strategies are shared catalog records. Deleting a strategy should be blocked while historical rows reference it, unless a retirement/archive model replaces deletion. |
| `book_strategy_assignments.param_set_id` -> `strategy_param_sets.id` | `NO ACTION` | Param sets are shared/versioned configuration evidence. |

## Migration Shape

SQLite cannot alter `ON DELETE` actions in place. Each changed FK requires a table rebuild migration:

1. create a replacement table with the target FK action
2. copy existing rows
3. drop or rename the old table only after backup and validation plan approval
4. recreate indexes and unique constraints
5. run `PRAGMA foreign_key_check`

The example pattern lives in `.ai/skills/db-migration/sqlite-table-rebuild.md`.

## Decision Checklist

- [ ] Decide whether direct account-owned operational rows should cascade.
- [ ] Decide whether research/evaluation rows should survive account deletion.
- [ ] Decide whether promotion and risk history are audit records.
- [x] Add table-rebuild migration support under `src/infrastructure/database/`.
- [x] Update fresh DDL in `src/infrastructure/database/schema.py`.
- [x] Add migration tests for a legacy table shape upgraded to the target FK action.
- [ ] Add service tests proving account deletion still reports counts and leaves no FK violations.

## Related Docs

- [Database Diagram Viewer](database-diagram-viewer.html)
- [DB Migration System](db-migration-system.md)
