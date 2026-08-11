# Repositories

## Purpose

SQL persistence adapters — the only layer that talks to the database. Each module owns one logical
data area, builds its SQL internally, and takes plain data from callers (never SQL fragments).
Services depend on repositories; repositories never import services.

The directory is intentionally flat. The groupings below are the *ownership* map — read them as
"which modules change together", not as a directory structure. Modules listed under
[Cross-cutting](#cross-cutting) resist grouping on purpose: their responsibilities genuinely span
several contexts, so filing them under one owner would misstate who owns them.

## What belongs here

Every module in this package **owns one area's SQL**. Nothing else does.

Owning "one area" is not the same as owning one table: `promotion.py` and `risk.py` each own two,
`books.py` also owns `book_universe_history`, and `table_export.py` is table-agnostic by design.
Those are a different granularity, not a different kind of thing, and each says so in its module
docstring.

Anything without SQL of its own belongs elsewhere. Mechanics every repository shares — transaction
scope, column encoding — live in [`trading/persistence/`](../persistence/), which sits *below* this
layer so `backtesting/repositories/` and the services above can use them too. A module that
needs a connection but expresses domain policy is a service; a pure calculation over already-fetched
rows is `domain/`; connection, schema, backend, and path concerns are `infrastructure/database/`.

## Golden rules

- **Every write commits through `commit_unit_of_work`, never `conn.commit()`.** Standalone it
  commits immediately; inside an open `unit_of_work(conn)` scope it defers, so any write can be
  composed into a larger all-or-nothing sequence. Both live in
  [`trading/persistence/unit_of_work.py`](../persistence/unit_of_work.py), the only module that
  calls `conn.commit()` directly. A hard commit inside a scope would end the transaction early and
  silently defeat the rollback guarantee — see
  [Database Transactions](../../../docs/reference/database-transactions.md).
- **`promotion.py` deliberately does not commit at all** — it leaves the commit
  to its caller's `unit_of_work` scope. That is a deliberate caller-owned boundary, not an
  oversight; don't "fix" it by adding a commit without checking callers.
  (`book_strategy_history.py` opens its own scope internally, so it commits when called standalone
  and joins an outer scope otherwise.)
- **Reads need no ceremony.** Only write methods commit, so query methods participate in any
  enclosing scope for free.
- **A row becomes a record at the query**, written out as `Record.from_mapping(dict(row))` — the
  same spelling `backtesting/repositories/` uses. Coercion belongs in the model's `from_mapping`,
  never in a private per-class mapper. Every record and event model has one, enum and JSON columns
  included; `common.coercion` carries the readers a model is allowed to reach for, because
  `trading/models/` sits below `trading/persistence/` and cannot import it.
- **Writes take their timestamp from the caller.** `updated_at`/`created_at` are parameters, never
  `utc_now_iso()` called inside a repository: several callers pass an event time (a fill, a ledger
  entry) that is deliberately not the wall clock.
- **`books.py`, `snapshots.py`, and `positions.py` carry the widest import
  fan-out** in the package. Changes to their signatures ripple broadly — prefer additive changes.

## Modules

### Books — the execution primitive

| Module | Responsibility |
|---|---|
| `books.py` | Strategy books: bounded capital pools that own cash, positions, and settings |
| `book_strategy_history.py` | The `book_strategy_history` table: a book's strategy assignments, the open row being its incumbent |
| `book_rotation_settings.py` | The `book_rotation_settings` row: per-book rotation gate, schedule, lookback, and policy weights |
| `rotation_decisions.py` | Champion/challenger rotation decision records |

### Execution — orders through to accounting

| Module | Responsibility |
|---|---|
| `orders.py` | Orders table (unifies broker and book orders) plus fills |
| `positions.py` | Position records keyed by `(book_id, symbol)` |
| `ledger.py` | Book-keyed ledger entries (the cash-effect trail) |
| `risk.py` | Risk snapshots and normalized risk-decision records |

### Accounts and balances

| Module | Responsibility |
|---|---|
| `accounts.py` | Account records, deletion-count queries, cascade-backed deletion |
| `snapshots.py` | Book-keyed equity snapshots with account-level roll-up reads |
| `daily_metrics.py` | Daily performance metric snapshots |

`snapshots.py` is **accounting**, not evaluation — it stores balances (cash, market value, equity,
realized/unrealized P&L) and is read by the accounts, analysis, evaluation, execution-reconciliation,
and reporting services alike.

### Strategy catalog

| Module | Responsibility |
|---|---|
| `strategies.py` | Strategy catalog rows: primitive + knobs, draft/frozen lifecycle, label → row id resolution |

### Promotion

| Module | Responsibility |
|---|---|
| `promotion.py` | Promotion reviews and their event history |

Self-contained: two dedicated tables (`promotion_reviews`, `promotion_review_events`) read only by
`services/promotion/`. The most cohesive context in the package.

### Cross-cutting

These belong to no single context and stay at the root deliberately.

| Module | Responsibility |
|---|---|
| `global_settings.py` | Single-row global settings (throttles, evaluation, promotion thresholds) |
| `table_export.py` | Generic read-only table-cursor access by table name for the operator CSV export — not scoped to one business context by design |

## Usage

Group several writes into one all-or-nothing transaction:

```python
from trading.persistence.unit_of_work import unit_of_work

with unit_of_work(conn):
    order_id = OrderRepository(conn).insert(...)   # no commit yet
    PositionRepository(conn).upsert(...)           # no commit yet
# one COMMIT here on clean exit; a raise anywhere above rolls all of it back
```

Keep broker/network calls **outside** the scope — never hold a write transaction open across I/O.

Inspect the current schema rather than relying on a hand-maintained mirror:

```bash
python -m scripts.data_ops.describe_db_schema
```

## Related

- [Database Transactions](../../../docs/reference/database-transactions.md) — the unit-of-work pattern in full
- [Trading Package Map](../../../docs/maps/trading-package-map.md) — whole-package navigation
- [Architecture Conventions](../../../docs/architecture/architecture-conventions.md) — layer boundaries
