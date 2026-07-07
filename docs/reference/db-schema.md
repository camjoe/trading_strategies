# Database Schema Reference

Type: notes
Status: Active
Created: 2026-06-16
Last Reviewed: 2026-06-19
Purpose: Schema orientation for agents and developers — quick-reference table (all tables, purposes, FK relationships) and semantic notes. For full DDL, read src/infrastructure/database/db_schema.py directly.
Related: [DB Migration System](db-migration-system.md), [Accounts Schema Usage](accounts-schema-usage.md)

**Sources of truth:**
- `src/infrastructure/database/schema.py` — CREATE TABLE statements (organized by table as named constants)
- `src/infrastructure/database/migrations.py` — ColumnMigration additions (append-only column history)
- `local/paper_trading.db` — live SQLite database

All timestamps are stored as ISO 8601 strings with UTC `Z` suffix (e.g. `2026-01-20T12:00:00Z`).  
New columns are added via the `ColumnMigration` append-only migration system — never drop or rename columns.

For a terminal schema view: `python -m scripts.data_ops.describe_db_schema` (or `--source live` for the live DB).

---

## Quick Reference

32 tables — the clean strategy-book tables (P3 rewrite) plus the legacy tables not yet retired. The
legacy order/accounting tables (`broker_orders`, `sleeve_orders`, `sleeve_fills`, `sleeve_positions`,
`sleeve_ledger`) were dropped in P4 as the submission/accounting spine moved onto the book tables. One
row per table — use this for orientation and context. For column details, read `db_schema.py` directly.

| Table | Purpose | Key relationships |
|---|---|---|
| `accounts` | Paper/live trading account config — strategy, risk policy, instrument mode, broker, rotation settings | — |
| `trades` | Individual paper trades (equities and options) | → `accounts` |
| `equity_snapshots` | Point-in-time cash/equity/P&L snapshots | → `accounts` |
| `global_settings` | Singleton row of system-wide runtime, evaluation, and promotion thresholds | — |
| `order_fills` | Individual fill events for a clean order | → `orders` |
| `backtest_runs` | Metadata for a single backtest execution (dates, fees, slippage, notes) | → `accounts` |
| `backtest_trades` | Simulated trades within a backtest run | → `backtest_runs` |
| `backtest_equity_snapshots` | Point-in-time equity snapshots within a backtest run | → `backtest_runs` |
| `walk_forward_groups` | Walk-forward group summary: date range, window count, aggregate return stats | → `accounts` |
| `walk_forward_group_runs` | Individual backtest runs belonging to a walk-forward group | → `walk_forward_groups`, `backtest_runs` |
| `strategy_sleeves` | Virtual sub-accounts within an account; each runs one strategy at a time | → `accounts` |
| `strategy_param_sets` | Versioned strategy parameter sets; one `is_active` per `strategy_name` | — |
| `sleeve_strategy_assignments` | History of which param set is/was incumbent for a sleeve | → `strategy_sleeves`, `strategy_param_sets` |
| `rotation_decisions` | Records of each hold/rotate decision for a sleeve | → `strategy_sleeves`, `strategy_param_sets` |
| `rotation_episodes` | Continuous runs of a single strategy on an account (started_at → ended_at) | → `accounts` |
| `sleeve_risk_decisions` | Allow/rescale/block decisions from the risk layer for a proposed trade | → `accounts`, `strategy_sleeves` |
| `portfolio_risk_snapshots` | Portfolio-level risk metrics snapshot (exposure, concentration, drawdown) | → `accounts` |
| `daily_metrics` | Per-day performance metrics (return, drawdown, hit rate) per account or sleeve | → `accounts`, `strategy_sleeves` |
| `promotion_reviews` | Strategy promotion review records (lifecycle: requested → closed) | → `accounts` |
| `promotion_review_events` | Audit trail of state transitions and notes within a promotion review | → `promotion_reviews` |
| `books` | Clean-schema strategy-execution primitive; one default book per account (partial-unique) | → `accounts` |
| `strategies` | Data-defined strategy catalog: code primitive + knobs (`params_json`), draft/frozen/retired | — |
| `feature_providers` | Pluggable external-feature provider catalog (enablement is data; fetch logic is code) | — |
| `book_execution_settings` | Per-unit execution/risk settings (risk policy, stops, sizing, per-run cap) | → `books` |
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

---

## Migration System

New columns are added via `ColumnMigration` dataclasses defined in `migrations.py`. Rules:

- **Append-only** — never drop or rename a column
- `NOT NULL` additions must supply a `DEFAULT` value
- `post_sql` can carry `UPDATE` statements to backfill existing rows
- `init_schema()` checks `PRAGMA table_info` before applying each migration (idempotent)

See `docs/reference/db-migration-system.md` for full details.
