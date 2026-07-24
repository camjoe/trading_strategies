# Database Transactions — the unit-of-work pattern

Type: notes
Status: Active
Created: 2026-07-21
Last Reviewed: 2026-07-21
Purpose: How to group several database writes into one all-or-nothing transaction with `unit_of_work`, and how repositories participate via `commit_unit_of_work`.
Related: [Architecture Conventions](../architecture/architecture-conventions.md), [DB Migration System](db-migration-system.md)

## Purpose

Read this when a single logical operation performs **more than one database
write** and a partial result would be wrong — an order fill that updates a
position, writes ledger entries, and adjusts book balances, for example. It
explains the reusable transaction primitive in
`src/trading/repositories/unit_of_work.py` and the one rule repositories must
follow to participate.

## How It Works

Repository writes are durable on their own: each write method ends with a commit
so a single mutation lands without ceremony. That is correct for one statement
but wrong for a sequence — a crash between two writes leaves the persisted state
inconsistent, and no amount of retry logic fixes an already-committed partial.

Every repository write in `trading/repositories/` therefore commits through
`commit_unit_of_work` rather than `conn.commit()`. Standalone that behaves
identically to a direct commit; inside a scope it defers, so any write can be
composed into a larger atomic sequence without the caller auditing which
repository it came from. `unit_of_work` itself is the only place that calls
`conn.commit()` directly.

Two functions solve this:

- **`unit_of_work(conn)`** — a context manager. Every participating write inside
  the block accumulates in one transaction that commits **once** when the
  outermost block exits cleanly, or **rolls back entirely** if the block raises.
  It is re-entrant: a service can wrap a sequence that itself calls helpers which
  open their own `unit_of_work` blocks, and only the outermost boundary commits.
- **`commit_unit_of_work(conn)`** — the drop-in replacement for `conn.commit()`
  inside a repository write. Standalone (no enclosing scope) it commits
  immediately, preserving the repository's normal behavior. Inside an open
  `unit_of_work` scope it is a no-op — the commit is owned by the scope.

Scope state is keyed by `id(conn)` and exists only while a scope is open on that
connection, because `sqlite3.Connection` supports neither attribute assignment
nor weak references. Connection-id reuse across closed connections is therefore
harmless.

The fill-accounting path is the worked example: `apply_book_fill` and its three
callers (submission, reconciliation, manual accounting) wrap their per-order
sequences, so the order row, its fills, and the book accounting land together or
not at all. See `src/trading/services/execution/submission.py`.

## Usage

A repository write participates by calling `commit_unit_of_work` instead of
committing directly:

```python
from trading.repositories.unit_of_work import commit_unit_of_work

class PositionRepository:
    def upsert(self, *, book_id: int, ...) -> None:
        self._conn.execute("INSERT INTO positions ... ON CONFLICT ...", (...))
        commit_unit_of_work(self._conn)  # commits standalone; defers inside a scope
```

A service groups several such writes into one transaction:

```python
from trading.repositories.unit_of_work import unit_of_work

with unit_of_work(conn):
    order_id = order_repo.insert(...)      # no commit yet
    order_repo.insert_fill(order_id=...)   # no commit yet
    apply_book_fill(conn, ...)             # its own nested unit_of_work joins this one
# one COMMIT here on clean exit; a raise anywhere above rolls all of it back
```

The broker/network call that produces the data must stay **outside** the
`unit_of_work` block — a write transaction must not be held open across I/O.

## Boundaries

- **Every repository write must use `commit_unit_of_work`.** A write that
  hard-commits (`conn.commit()`) inside a scope ends the transaction early and
  silently defeats the rollback guarantee. This is now uniform across
  `trading/repositories/`, so a new write should follow suit rather than
  hard-committing and waiting to be converted when some caller later needs
  atomicity. `tests/src/trading/repositories/test_repository_transaction_participation.py`
  guards the rule.
- **A few repositories intentionally do not commit at all** — `book_bridge`,
  `promotion`, and `book_assignments` leave the commit to their caller. That is a
  deliberate caller-owned boundary, not an oversight; do not "fix" them by adding
  a commit without checking the callers.
- **The primitive lives in the repository layer** (`trading/repositories/`), not
  `infrastructure/database/`, so services can import it without crossing the
  `trading/services → no direct database imports` boundary enforced by
  `scripts.checks.repo.layer_check`. It imports only the standard library.
- **Reads are unaffected** — only write methods commit, so query methods need no
  change to participate.
- Rollback restores database state only. Any in-memory state a service mutated
  before the exception (counters, accumulator lists) is the caller's
  responsibility, exactly as before.

## Related Docs

- [Architecture Conventions](../architecture/architecture-conventions.md) — layer boundaries, including the services→database import rule
- [DB Migration System](db-migration-system.md) — schema change lifecycle
