"""Group repository writes into one atomic transaction.

Repositories in this codebase self-commit (`conn.commit()` after each write),
which is correct for a single-statement mutation but wrong for a multi-write
sequence: a crash between two writes leaves the projections inconsistent (a
recorded fill whose cash effect never landed, for example).

`unit_of_work(conn)` opens a scope in which participating repositories call
:func:`maybe_commit` instead of committing directly, so every write accumulates
in one transaction that commits once at the end of the outermost scope — or
rolls back entirely if the block raises. The scope is re-entrant, so a service
can wrap a sequence that itself calls helpers which open their own
`unit_of_work` blocks.

State is keyed by ``id(conn)`` and exists only while a scope is open on that
connection (``sqlite3.Connection`` supports neither attribute assignment nor
weak references), so connection-id reuse across closed connections is harmless.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

# Open unit-of-work nesting depth per live connection, keyed by id(conn).
_ACTIVE_DEPTH: dict[int, int] = {}


@contextmanager
def unit_of_work(conn: Any) -> Iterator[Any]:
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


def maybe_commit(conn: Any) -> None:
    """Commit *conn*, unless an enclosing :func:`unit_of_work` owns the transaction.

    The drop-in replacement for ``conn.commit()`` in repository writes that must
    be able to participate in a larger atomic sequence. Standalone (no enclosing
    scope) it commits immediately, preserving each repository's prior behavior.
    """
    if _ACTIVE_DEPTH.get(id(conn), 0) == 0:
        conn.commit()
