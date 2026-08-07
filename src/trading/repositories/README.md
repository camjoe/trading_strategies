# Repositories

## Purpose

SQL persistence adapters — the only layer that talks to the database. Each module owns one logical
data area, builds its SQL internally, and takes plain data from callers (never SQL fragments).
Services depend on repositories; repositories never import services.

The directory is intentionally flat. The groupings below are the *ownership* map — read them as
"which modules change together", not as a directory structure. Modules listed under
[Cross-cutting](#cross-cutting) resist grouping on purpose: their responsibilities genuinely span
several contexts, so filing them under one owner would misstate who owns them.

## Golden rules

- **Every write commits through `commit_unit_of_work`, never `conn.commit()`.** Standalone it
  commits immediately; inside an open `unit_of_work(conn)` scope it defers, so any write can be
  composed into a larger all-or-nothing sequence. `unit_of_work.py` is the only module that calls
  `conn.commit()` directly. A hard commit inside a scope would end the transaction early and
  silently defeat the rollback guarantee — see
  [Database Transactions](../../../docs/reference/database-transactions.md).
- **`book_bridge.py` and `promotion.py` deliberately do not commit at all** — they leave the commit
  to their caller's `unit_of_work` scope. That is a deliberate caller-owned boundary, not an
  oversight; don't "fix" them by adding a commit without checking callers. (`book_assignments.py`
  opens its own scope internally, so it commits when called standalone and joins an outer scope
  otherwise.)
- **Reads need no ceremony.** Only write methods commit, so query methods participate in any
  enclosing scope for free.
- **`books.py`, `book_bridge.py`, `snapshots.py`, and `positions.py` carry the widest import
  fan-out** in the package. Changes to their signatures ripple broadly — prefer additive changes.

## Modules

### Books — the execution primitive

| Module | Responsibility |
|---|---|
| `books.py` | Strategy books: bounded capital pools that own cash, positions, and settings |
| `book_assignments.py` | Book↔strategy assignment and lifecycle records |
| `book_settings.py` | Per-concern typed book settings (execution, rotation, options) |
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
| `strategies.py` | Strategy catalog rows: primitive + knobs, draft/frozen lifecycle |
| `feature_providers.py` | Feature-provider enablement and config records |

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
| `unit_of_work.py` | Re-entrant transaction scope + `commit_unit_of_work` helper |
| `change_events.py` | JSON column encoding and the old/new field diff behind the settings change-event trail |
| `global_settings.py` | Single-row global settings (throttles, evaluation, promotion thresholds) |
| `fixture_seed.py` | Fixture-only writes with no production writer to route through (backtest/promotion records, non-default book bootstrap) |
| `book_bridge.py` | **Transitional.** Bridges legacy account/label access into the book-keyed tables (account → default book, strategy label → catalog row). Retires only once callers are book-native end to end — treat it as a seam, not a permanent home. |
| `table_export.py` | Generic read-only table row/CSV-cursor access for the operator export/preview feature — not scoped to one business context by design |

## Usage

Group several writes into one all-or-nothing transaction:

```python
from trading.repositories.unit_of_work import unit_of_work

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
