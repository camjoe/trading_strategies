# Database Schema Reference

Type: notes
Status: Active
Created: 2026-06-16
Last Reviewed: 2026-07-16
Purpose: Schema orientation for agents and developers — quick-reference table (all tables, purposes, FK relationships) and semantic notes. For full DDL, read the Alembic revisions or run scripts.data_ops.describe_db_schema.
Related: [DB Migration System](db-migration-system.md)

**Sources of truth:**
- `src/infrastructure/database/alembic/versions/` — the numbered Alembic revision chain (revision `0001` holds the base DDL; later revisions amend it)
- `local/paper_trading.db` — live SQLite database

All timestamps are stored as ISO 8601 strings with UTC `Z` suffix (e.g. `2026-01-20T12:00:00Z`).  
Schema changes are authored as new immutable revisions — never edit an applied revision.

For a terminal schema view: `python -m scripts.data_ops.describe_db_schema` (or `--source live` for the live DB).

---

## Quick Reference

25 tables — the clean strategy-book tables plus the remaining account-level history, research, and
configuration tables. The legacy order/accounting tables (`broker_orders`, `sleeve_orders`,
`sleeve_fills`, `sleeve_positions`, `sleeve_ledger`, `rotation_episodes`) and the retired
`strategy_param_sets` store were dropped as the submission/accounting spine and strategy catalog
moved onto the book/strategy tables. One row per table — use this for orientation and context. For
column details, run `python -m scripts.data_ops.describe_db_schema`.

| Table | Purpose | Key relationships |
|---|---|---|
| `accounts` | Account identity, custody, goals, option config, and broker connection (rotation columns dropped in `0003`; execution columns moved to `books` in `0004`) | — |
| `trades` | Individual paper trades (equities and options) | → `accounts` |
| `equity_snapshots` | Point-in-time cash/equity/P&L snapshots | → `books` |
| `global_settings` | Singleton row of system-wide runtime, evaluation, and promotion thresholds | — |
| `order_fills` | Individual fill events for a clean order | → `orders` |
| `backtest_runs` | Metadata for a single backtest execution (dates, fees, slippage, notes) | → `accounts` |
| `backtest_trades` | Simulated trades within a backtest run | → `backtest_runs` |
| `backtest_equity_snapshots` | Point-in-time equity snapshots within a backtest run | → `backtest_runs` |
| `walk_forward_groups` | Walk-forward group summary: date range, window count, aggregate return stats | → `accounts` |
| `walk_forward_group_runs` | Individual backtest runs belonging to a walk-forward group | → `walk_forward_groups`, `backtest_runs` |
| `rotation_decisions` | Records of each hold/rotate decision for a book | → `books`, `strategies` |
| `daily_metrics` | Per-day performance metrics (return, drawdown, hit rate) per book | → `books` |
| `promotion_reviews` | Strategy promotion review records (lifecycle: requested → closed) | → `accounts` |
| `promotion_review_events` | Audit trail of state transitions and notes within a promotion review | → `promotion_reviews` |
| `books` | Strategy-execution primitive incl. execution/risk settings columns (revision `0004`); one default book per account (partial-unique) | → `accounts` |
| `strategies` | Data-defined strategy catalog: code primitive + knobs (`params_json`), draft/frozen/retired | — |
| `feature_providers` | Pluggable external-feature provider catalog (enablement is data; fetch logic is code) | — |
| `book_option_settings` | Per-unit option/leaps config (strike offset, DTE, delta/IV bounds, caps) | → `books` |
| `book_rotation_settings` | Per-unit rotation settings (mode, interval, schedule, regime/overlay config) | → `books`, `strategies` |
| `book_strategy_assignments` | Which strategy a book runs; one open assignment per book (partial-unique) | → `books`, `strategies` |
| `orders` | Clean-schema orders (unifies broker + sleeve orders), book-keyed with broker linkage | → `books`, `accounts`, `strategies` |
| `positions` | Current open positions per book, keyed `(book_id, symbol)` | → `books` |
| `ledger` | Unit-keyed cash/trade/fee ledger entries (unifies sleeve ledger + account trades) | → `books` |
| `risk_snapshots` | Account-level risk metrics snapshots (clean-schema successor to `portfolio_risk_snapshots`) | → `accounts` |
| `risk_decisions` | Allow/rescale/block risk decisions (clean-schema successor to `sleeve_risk_decisions`) | → `accounts`, `books` |

*Update this table manually when tables are added or removed. Drift is detected by `python -m scripts.checks.docs.db_schema_check`.*

---

## Semantic Notes

Domain-specific meaning that the schema alone does not convey.

### `accounts`

| Column | Note |
|--------|------|
| `initial_cash` | Starting cash balance seeded by the operator. Set to `0.0` for **deposit-model accounts**, where capital is injected via `CASH`-ticker buy trades in the `trades` table. Services use `total_deposited` (from `AccountState`) as the P&L-percentage base when `initial_cash = 0`. |

### `trades`

**Note conventions used in `note` field:**

| Prefix | Meaning |
|--------|---------|
| `auto-daily;strategy=<name>` | System-generated daily trade |
| `manual-import;source=<name>` | Manually imported trade |
| `manual-import;...;instrument=option;type=call;action=bought\|sold\|expired` | Options trade |

### Deletion semantics

- Account deletion is a single `DELETE FROM accounts`; `ON DELETE CASCADE` removes every
  account-owned row (books, orders, trades, research, governance, and risk history). The
  pre-deletion database backup is the only retention path — there is no archive model.
- `walk_forward_group_runs.run_id -> backtest_runs` is deliberately `NO ACTION`: a grouped run
  must not silently vanish from its group's composition. Account deletion still succeeds because
  SQLite settles immediate FK checks at statement end, inside the single cascading delete. Do not
  "fix" this FK to `CASCADE` in a future rebuild without an explicit decision.

---

## Migration System

Schema changes are numbered Alembic revisions in `src/infrastructure/database/alembic/versions/`. Rules:

- Revisions are **immutable** — a fix is a new revision, never an edit
- Every revision implements `upgrade()` and `downgrade()`
- `NOT NULL` additions must supply a `DEFAULT` value
- Operators apply revisions with `python -m scripts.data_ops.manage_db_migrations`; runtime only verifies

See `docs/reference/db-migration-system.md` for full details.
