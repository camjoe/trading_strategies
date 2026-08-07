"""Group several database writes into one all-or-nothing transaction.

Repositories in this codebase self-commit (``conn.commit()`` after each write),
which is correct for a single-statement mutation but wrong for a multi-write
sequence: a crash between two writes leaves the persisted state inconsistent —
for example a recorded order fill whose cash effect never landed.

Wrap the sequence in ``unit_of_work(conn)``. Inside that scope, participating
repositories call :func:`commit_unit_of_work` instead of ``conn.commit()``, so
every write accumulates in one transaction that commits once when the outermost
scope exits cleanly — or rolls back entirely if the block raises. The scope is
re-entrant, so a service can wrap a sequence that itself calls helpers which
open their own ``unit_of_work`` blocks.

Any repository write that should be able to participate must call
:func:`commit_unit_of_work` rather than committing directly; a write that
hard-commits inside a scope would end the transaction early and defeat the
rollback guarantee.

State is keyed by ``id(conn)`` and exists only while a scope is open on that
connection (``sqlite3.Connection`` supports neither attribute assignment nor
weak references), so connection-id reuse across closed connections is harmless.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

# Open unit-of-work nesting depth per live connection, keyed by id(conn).
_ACTIVE_DEPTH: dict[int, int] = {}


@contextmanager
def unit_of_work(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run the block's repository writes as one all-or-nothing transaction.

    Commits once when the outermost scope exits cleanly; rolls the whole
    transaction back if it raises. Nested scopes join the outermost one.
    """
    key = id(conn)
    outer_depth = _ACTIVE_DEPTH.get(key, 0)
    _ACTIVE_DEPTH[key] = outer_depth + 1
    try:
        yield conn
    except BaseException:
        if outer_depth == 0:
            conn.rollback()
        raise
    else:
        if outer_depth == 0:
            conn.commit()
    finally:
        if outer_depth == 0:
            _ACTIVE_DEPTH.pop(key, None)
        else:
            _ACTIVE_DEPTH[key] = outer_depth


def commit_unit_of_work(conn: sqlite3.Connection) -> None:
    """Commit the connection's current unit of work.

    The drop-in replacement for ``conn.commit()`` in repository writes that must
    be able to participate in a larger atomic sequence. Standalone (no enclosing
    scope) it commits the write immediately, preserving each repository's prior
    behavior. Inside an open :func:`unit_of_work` scope the commit is owned by
    that scope, so this is a no-op and the write lands when the scope closes.
    """
    if _ACTIVE_DEPTH.get(id(conn), 0) == 0:
        conn.commit()
