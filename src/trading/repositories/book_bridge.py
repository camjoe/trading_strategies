"""Idempotent bridging resolutions into the book-keyed tables.

Two shared resolutions used across services (execution, rotation, parameters):

- account → its default book (created bare on first write; settings rows are
  intentionally absent — a missing row means code defaults),
- strategy label → a `strategies` row (created as a draft when the catalog
  has no row for the label yet).

These retire only if a future refactor makes callers book-native end to end.
"""

from __future__ import annotations

import sqlite3


def default_book_id(conn: sqlite3.Connection, account_id: int) -> int:
    """Resolve (bootstrapping if needed) the account's default book id."""
    row = conn.execute(
        "SELECT id FROM books WHERE account_id = ? AND is_default = 1",
        (int(account_id),),
    ).fetchone()
    if row is not None:
        return int(row[0])
    cursor = conn.execute(
        """
        INSERT INTO books (
            account_id, name, status, is_default, start_equity, current_cash,
            current_equity, trade_universes, goal_min_return_pct,
            goal_max_return_pct, goal_period, created_at, updated_at
        )
        SELECT id, 'default', 'active', 1, initial_cash, initial_cash, initial_cash,
               trade_universes, goal_min_return_pct, goal_max_return_pct, goal_period,
               created_at, created_at
        FROM accounts WHERE id = ?
        """,
        (int(account_id),),
    )
    if cursor.rowcount == 0:
        raise LookupError(f"Account {account_id} does not exist; cannot resolve its default book.")
    return int(cursor.lastrowid or 0)


def strategy_id_for_label(
    conn: sqlite3.Connection,
    label: str | None,
    *,
    now_iso: str,
    create: bool = True,
) -> int | None:
    """Resolve a legacy strategy label to a strategies row id (draft-created if unknown)."""
    if label is None or not label.strip():
        return None
    key = label.strip().lower()
    row = conn.execute("SELECT id FROM strategies WHERE strategy_key = ?", (key,)).fetchone()
    if row is not None:
        return int(row[0])
    if not create:
        return None
    primitive, style = _draft_primitive_and_style(key)
    cursor = conn.execute(
        """
        INSERT INTO strategies (
            strategy_key, primitive, params_json, style, status, enabled, created_at, updated_at
        )
        VALUES (?, ?, '{}', ?, 'draft', 1, ?, ?)
        """,
        (key, primitive, style, now_iso, now_iso),
    )
    return int(cursor.lastrowid or 0)


def _draft_primitive_and_style(key: str) -> tuple[str, str]:
    """Canonical primitive id + style for a bridged draft label.

    A draft records the canonical code primitive its label resolves to (e.g.
    ``momentum`` -> ``trend``) so the catalog stays internally consistent. An
    unrecognized label keeps the raw key as a neutral placeholder primitive,
    which the catalog resolver reports as unresolvable at read time.
    """
    from trading.domain.strategy_signals import resolve_strategy

    try:
        spec = resolve_strategy(key)
    except ValueError:
        return key, "neutral"
    return spec.strategy_id, spec.strategy_style
