# Database Schema Reference

**Source of truth:** `trading/database/db.py`  
**Database file:** `local/paper_trading.db` (SQLite)

All timestamps are stored as ISO 8601 strings with UTC `Z` suffix (e.g. `2026-01-20T12:00:00Z`).  
New columns are added via the `ColumnMigration` append-only migration system — never drop or rename columns.

---

## accounts

Stores paper-trading and live-trading account configurations.

```sql
CREATE TABLE IF NOT EXISTS accounts (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    name                     TEXT    NOT NULL UNIQUE,
    strategy                 TEXT    NOT NULL,
    initial_cash             REAL    NOT NULL,
    created_at               TEXT    NOT NULL,

    -- benchmark & goals
    benchmark_ticker         TEXT    NOT NULL DEFAULT 'SPY',
    descriptive_name         TEXT    NOT NULL DEFAULT '',
    goal_min_return_pct      REAL,
    goal_max_return_pct      REAL,
    goal_period              TEXT    NOT NULL DEFAULT 'monthly',

    -- learning & risk
    learning_enabled         INTEGER NOT NULL DEFAULT 0,
    risk_policy              TEXT    NOT NULL DEFAULT 'none',
    stop_loss_pct            REAL,
    take_profit_pct          REAL,

    -- instrument mode (equity | option)
    instrument_mode          TEXT    NOT NULL DEFAULT 'equity',
    option_strike_offset_pct REAL,
    option_min_dte           INTEGER,
    option_max_dte           INTEGER,
    option_type              TEXT,
    target_delta_min         REAL,
    target_delta_max         REAL,
    max_premium_per_trade    REAL,
    max_contracts_per_trade  INTEGER,
    iv_rank_min              REAL,
    iv_rank_max              REAL,
    roll_dte_threshold       INTEGER,
    profit_take_pct          REAL,
    max_loss_pct             REAL,

    -- rotation settings
    rotation_enabled         INTEGER NOT NULL DEFAULT 0,
    rotation_mode            TEXT    NOT NULL DEFAULT 'time',
    rotation_optimality_mode TEXT    NOT NULL DEFAULT 'previous_period_best',
    rotation_interval_days   INTEGER,
    rotation_lookback_days   INTEGER,
    rotation_schedule        TEXT,
    rotation_active_index    INTEGER NOT NULL DEFAULT 0,
    rotation_last_at         TEXT,
    rotation_active_strategy TEXT
);
```

**Column notes**

| Column | Note |
|--------|------|
| `initial_cash` | Starting cash balance seeded by the operator. Set to `0.0` for **deposit-model accounts**, where capital is injected via `CASH`-ticker buy trades in the `trades` table. Services use `total_deposited` (from `AccountState`) as the P&L-percentage base when `initial_cash = 0`. |

---

## trades

Individual paper trades (equities and options) linked to an account.

```sql
CREATE TABLE IF NOT EXISTS trades (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id   INTEGER NOT NULL,
    ticker       TEXT    NOT NULL,
    side         TEXT    NOT NULL CHECK (side IN ('buy', 'sell')),
    qty          REAL    NOT NULL,
    price        REAL    NOT NULL,   -- per-share / per-contract price
    fee          REAL    NOT NULL DEFAULT 0,
    trade_time   TEXT    NOT NULL,
    note         TEXT,
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
```

**Note conventions used in `note` field:**

| Prefix | Meaning |
|--------|---------|
| `auto-daily;strategy=<name>` | System-generated daily trade |
| `manual-import;source=<name>` | Manually imported trade |
| `manual-import;...;instrument=option;type=call;action=bought\|sold\|expired` | Options trade |

---

## equity_snapshots

Point-in-time equity/cash snapshots for an account.

```sql
CREATE TABLE IF NOT EXISTS equity_snapshots (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id     INTEGER NOT NULL,
    snapshot_time  TEXT    NOT NULL,
    cash           REAL    NOT NULL,
    market_value   REAL    NOT NULL,
    equity         REAL    NOT NULL,
    realized_pnl   REAL    NOT NULL,
    unrealized_pnl REAL    NOT NULL,
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
```

---

## backtest_runs

Metadata for a single backtest execution.

```sql
CREATE TABLE IF NOT EXISTS backtest_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id    INTEGER NOT NULL,
    strategy_name TEXT,
    run_name      TEXT,
    start_date    TEXT    NOT NULL,
    end_date      TEXT    NOT NULL,
    created_at    TEXT    NOT NULL,
    slippage_bps  REAL    NOT NULL DEFAULT 0,
    fee_per_trade REAL    NOT NULL DEFAULT 0,
    tickers_file  TEXT,
    notes         TEXT,
    warnings      TEXT,
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
```

---

## backtest_trades

Simulated trades within a backtest run.

```sql
CREATE TABLE IF NOT EXISTS backtest_trades (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER NOT NULL,
    trade_time   TEXT    NOT NULL,
    ticker       TEXT    NOT NULL,
    side         TEXT    NOT NULL CHECK (side IN ('buy', 'sell')),
    qty          REAL    NOT NULL,
    price        REAL    NOT NULL,
    fee          REAL    NOT NULL DEFAULT 0,
    slippage_bps REAL    NOT NULL DEFAULT 0,
    note         TEXT,
    FOREIGN KEY (run_id) REFERENCES backtest_runs(id)
);
```

---

## backtest_equity_snapshots

Point-in-time equity snapshots within a backtest run.

```sql
CREATE TABLE IF NOT EXISTS backtest_equity_snapshots (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         INTEGER NOT NULL,
    snapshot_time  TEXT    NOT NULL,
    cash           REAL    NOT NULL,
    market_value   REAL    NOT NULL,
    equity         REAL    NOT NULL,
    realized_pnl   REAL    NOT NULL,
    unrealized_pnl REAL    NOT NULL,
    FOREIGN KEY (run_id) REFERENCES backtest_runs(id)
);
```

---

## broker_orders

Live broker orders submitted to an external broker integration.

```sql
CREATE TABLE IF NOT EXISTS broker_orders (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id       INTEGER NOT NULL,
    broker_order_id  TEXT    NOT NULL UNIQUE,
    ticker           TEXT    NOT NULL,
    side             TEXT    NOT NULL CHECK (side IN ('buy', 'sell')),
    qty              REAL    NOT NULL,
    order_type       TEXT    NOT NULL DEFAULT 'market',
    time_in_force    TEXT    NOT NULL DEFAULT 'day',
    requested_price  REAL    NOT NULL,
    status           TEXT    NOT NULL,
    filled_qty       REAL    NOT NULL DEFAULT 0,
    avg_fill_price   REAL,
    commission       REAL    NOT NULL DEFAULT 0,
    submitted_at     TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL,
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
```

---

## order_fills

Individual fill events for a broker order.

```sql
CREATE TABLE IF NOT EXISTS order_fills (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    broker_order_id TEXT NOT NULL,
    filled_qty      REAL NOT NULL,
    fill_price      REAL NOT NULL,
    fill_time       TEXT NOT NULL,
    commission      REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (broker_order_id) REFERENCES broker_orders(broker_order_id)
);
```

---

## Indexes

```sql
-- Backtest
CREATE INDEX IF NOT EXISTS idx_backtest_runs_account_id   ON backtest_runs(account_id);
CREATE INDEX IF NOT EXISTS idx_backtest_trades_run_id     ON backtest_trades(run_id);
CREATE INDEX IF NOT EXISTS idx_backtest_equity_run_id     ON backtest_equity_snapshots(run_id);

-- Broker
CREATE INDEX IF NOT EXISTS idx_broker_orders_account_id       ON broker_orders(account_id);
CREATE INDEX IF NOT EXISTS idx_order_fills_broker_order_id    ON order_fills(broker_order_id);
```

---

## Migration system

New columns are added via `ColumnMigration` dataclasses defined in `db.py`. Rules:

- **Append-only** — never drop or rename a column
- `NOT NULL` additions must supply a `DEFAULT` value
- `post_sql` can carry `UPDATE` statements to backfill existing rows
- `init_schema()` checks `PRAGMA table_info` before applying each migration (idempotent)

See `docs/reference/db-migration-system.md` for full details.
