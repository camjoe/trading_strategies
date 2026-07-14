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

The schema has taken over child-row cleanup for the implemented cascades below: the service no longer
deletes `order_fills`, `backtest_trades`, `backtest_equity_snapshots`, `promotion_review_events`, or
`walk_forward_group_runs` explicitly. Deletion order still matters — `walk_forward_groups` must be
deleted before `backtest_runs` because `walk_forward_group_runs.run_id` remains `NO ACTION` (an open
decision below).

## Implemented Child-Owned Cascades

These relationships are child-owned implementation detail. The child row has no useful standalone meaning after the parent row is deleted.

| Relationship | Action | Validation |
|---|---|---|
| `order_fills.order_id` -> `orders.id` | `ON DELETE CASCADE` | Fresh DDL plus legacy table-rebuild migration. |
| `backtest_trades.run_id` -> `backtest_runs.id` | `ON DELETE CASCADE` | Fresh DDL plus legacy table-rebuild migration. |
| `backtest_equity_snapshots.run_id` -> `backtest_runs.id` | `ON DELETE CASCADE` | Fresh DDL plus legacy table-rebuild migration. |
| `promotion_review_events.review_id` -> `promotion_reviews.id` | `ON DELETE CASCADE` | Fresh DDL plus legacy table-rebuild migration. |
| `walk_forward_group_runs.group_id` -> `walk_forward_groups.id` | `ON DELETE CASCADE` | Fresh DDL plus legacy table-rebuild migration. |

## Implemented Account-Owned Cascades

Decision (2026-07-13): account deletion removes the account's operational, research, governance, and
risk history. There is no separate archive path; the pre-deletion backup
(`data_ops.admin backup`) is the retention mechanism.

| Relationship | Action | Notes |
|---|---|---|
| `trades.account_id` -> `accounts.id` | `ON DELETE CASCADE` | Codifies what `delete_accounts()` already did explicitly. |
| `orders.account_id` -> `accounts.id`, `orders.book_id` -> `books.id` | `ON DELETE CASCADE` | Fresh DDL already cascaded; the rebuild upgrades pre-book-era legacy DBs. |
| `backtest_runs.account_id` -> `accounts.id` | `ON DELETE CASCADE` | Research runs are account-owned; cascades reach `backtest_trades`/`backtest_equity_snapshots`. |
| `walk_forward_groups.account_id` -> `accounts.id` | `ON DELETE CASCADE` | Cascades reach `walk_forward_group_runs` via `group_id`. |
| `promotion_reviews.account_id` -> `accounts.id` | `ON DELETE CASCADE` | Codifies existing service behavior; events cascade via `review_id`. |
| `risk_snapshots.account_id` -> `accounts.id` | `ON DELETE CASCADE` | Fixes a latent bug: the service never deleted risk rows, so account deletion failed for accounts with risk telemetry. |
| `risk_decisions.account_id` -> `accounts.id` | `ON DELETE CASCADE` | Same latent-bug fix as `risk_snapshots`. |
| `risk_decisions.book_id` -> `books.id` | `ON DELETE SET NULL` | Standalone book deletion preserves account-level decision history (`book_id` was already nullable); account deletion still removes rows via `account_id`. |

## Remaining Open Decision

| Relationship | Candidate action | Decision dependency | Risk if chosen blindly |
|---|---|---|---|
| `walk_forward_group_runs.run_id` -> `backtest_runs.id` | `ON DELETE CASCADE` | Should deleting a backtest run remove its walk-forward membership, or should parent group deletion be the only cascade path? Kept `NO ACTION` so a grouped run cannot disappear silently; fold any change into a future `walk_forward_group_runs` rebuild. | A run deletion can silently alter walk-forward group composition. |

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

- [x] Decide whether direct account-owned operational rows should cascade. (Yes — cascade.)
- [x] Decide whether research/evaluation rows should survive account deletion. (No — account-owned; backup is the retention path.)
- [x] Decide whether promotion and risk history are audit records. (No — account-owned; risk `book_id` uses `SET NULL` so book deletion alone keeps history.)
- [x] Add table-rebuild migration support under `src/infrastructure/database/`.
- [x] Update fresh DDL in `src/infrastructure/database/schema.py`.
- [x] Add migration tests for a legacy table shape upgraded to the target FK action.
- [x] Add service tests proving account deletion still reports counts and leaves no FK violations.
- [x] Simplify `delete_accounts()` to rely on the implemented child-owned cascades.

## Related Docs

- [Database Diagram Viewer](database-diagram-viewer.html)
- [DB Migration System](db-migration-system.md)
