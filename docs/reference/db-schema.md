# Database Schema Reference

Type: notes
Status: Active
Created: 2026-06-16
Last Reviewed: 2026-07-17
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

24 tables — the clean strategy-book tables plus the remaining account-level history, research, and
configuration tables. The legacy order/accounting tables (`broker_orders`, `sleeve_orders`,
`sleeve_fills`, `sleeve_positions`, `sleeve_ledger`, `rotation_episodes`) and the retired
`strategy_param_sets` store were dropped as the submission/accounting spine and strategy catalog
moved onto the book/strategy tables. One row per table — use this for orientation and context. For
column details, run `python -m scripts.data_ops.describe_db_schema`.

| Table | Purpose | Key relationships |
|---|---|---|
| `accounts` | Account identity, custody, and broker connection — final shape since `0008` (legacy strategy/goal/universe columns are book-owned) | — |
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
| `books` | Strategy-execution primitive: execution/risk/option settings columns and required `trade_universes` (revisions `0004`–`0008`); one default book per account (partial-unique) | → `accounts` |
| `strategies` | Data-defined strategy catalog: code primitive + knobs (`params_json`), draft/frozen/retired | — |
| `feature_providers` | Pluggable external-feature provider catalog (enablement is data; fetch logic is code) | — |
| `book_rotation_settings` | Per-unit rotation settings (mode, interval, schedule, regime/overlay config) | → `books`, `strategies` |
| `book_strategy_assignments` | Which strategy a book runs; one open assignment per book (partial-unique) | → `books`, `strategies` |
| `orders` | Clean-schema orders (unifies broker + sleeve orders), book-keyed with broker linkage | → `books`, `accounts`, `strategies` |
| `positions` | Current open positions per book, keyed `(book_id, symbol)` | → `books` |
| `ledger` | Unit-keyed cash/trade/fee ledger entries (unifies sleeve ledger + account trades) | → `books` |
| `risk_snapshots` | Account-level risk metrics snapshots (clean-schema successor to `portfolio_risk_snapshots`) | → `accounts` |
| `risk_decisions` | Allow/rescale/block risk decisions (clean-schema successor to `sleeve_risk_decisions`) | → `accounts`, `books` |
| `book_universe_history` | Append-only record of which universes a book traded, when (`effective_from`/`effective_to`; revision `0008`) | → `books` |

*Update this table manually when tables are added or removed. Drift is detected by `python -m scripts.checks.docs.db_schema_check`.*

---

## Semantic Notes

Domain-specific meaning that the schema alone does not convey.

### `accounts`

| Column | Note |
|--------|------|
| `initial_cash` | Starting cash balance seeded by the operator. Set to `0.0` for **deposit-model accounts**, where capital is injected as `ledger` deposit entries (a manual `CASH`-ticker buy via `record_trade` becomes one). Services use `total_deposited` (from `AccountState`) as the P&L-percentage base when `initial_cash = 0`. |
| `broker_*`, `live_trading_enabled` | Broker connection stays on `accounts` by explicit decision (2026-07-16): it is core custody metadata, not a settings group — no 1:1 split table. The live-trading safety guard reads these columns. |

### `positions`

`market_value` and `unrealized_pnl` are **price-dependent caches** next to the authoritative
`qty`/`avg_cost` — they are only as fresh as the last mark-to-market. Do not treat them as truth;
recompute from current prices when accuracy matters.

### `global_settings`

The singleton row (`id = 1` CHECK) intentionally mixes three domains: runtime throttles,
evaluation weights, and promotion gates. This is a deliberate simplicity trade-off — revisit a
split only if a fourth domain lands here.

### Money as REAL

Cash, quantities, and prices are stored as SQLite `REAL` (floats) throughout. This is a **known,
accepted limitation** for paper trading — do not churn the schema toward integer cents or TEXT
decimals. Float drift is expected to surface via reconciliation checks (e.g. `books.current_cash`
vs the `ledger` sum) rather than be prevented by the storage type.

### Account trade history

The account-level `trades` table was dropped in revision `0006`. Execution history is
`orders`/`order_fills` (book-keyed); deposits/withdrawals are `ledger` entries. Account state
(`AccountState`: cash, positions, realized P&L, `total_deposited`) is **derived** by replaying an
account's fills plus its ledger cash events (`trading.services.accounting`). Free-text trade notes
were not carried over — pre-`0006` notes live only in database backups.

### Deletion semantics

- Account deletion is a single `DELETE FROM accounts`; `ON DELETE CASCADE` removes every
  account-owned row (books, orders and fills, research, governance, and risk history). The
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
