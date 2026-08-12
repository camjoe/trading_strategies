"""Read-only access to any table by name, for the operator CSV export.

Deliberately not scoped to one business context: the operator chooses the table at
runtime, so this module takes a table *name* where every other module in the package
has its table fixed in the SQL it owns.

A table name cannot be a bound parameter, so it is interpolated into the query. That
is why the entry point resolves its table through :func:`require_table` first. The
gate is existence: the normalized name must match a row in ``sqlite_master``, matched
by bound parameter, so only a name the database already carries reaches a statement.
:func:`normalize_table_name` narrows the input to ``[a-z0-9_]`` ahead of that, which
rejects early rather than carrying the check. A new read added here must go through
the same gate.
"""

from __future__ import annotations

import sqlite3

DEFAULT_EXPORT_TABLES: tuple[str, ...] = (
    "accounts",
    "equity_snapshots",
    "orders",
    "order_fills",
    "backtest_runs",
    "backtest_executions",
)


def normalize_table_name(name: str) -> str:
    # ASCII-only: str.isalnum() accepts any Unicode alphanumeric, and str.lower()
    # folds some non-ASCII characters into ASCII ones, so neither narrows to the
    # identifier shape on its own.
    cleaned = "".join(ch for ch in name.strip().lower() if ch.isascii() and (ch.isalnum() or ch == "_"))
    if not cleaned:
        raise ValueError("Table name cannot be empty.")
    return cleaned


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [str(row[1]) for row in rows]


def _ordered_select_sql(conn: sqlite3.Connection, table: str) -> str:
    cols = _table_columns(conn, table)
    if "id" in cols:
        return f"SELECT * FROM {table} ORDER BY id ASC"
    return f"SELECT * FROM {table}"


def require_table(conn: sqlite3.Connection, table: str) -> str:
    normalized = normalize_table_name(table)
    if not _table_exists(conn, normalized):
        raise ValueError(f"Table not found: {normalized}")
    return normalized


def fetch_table_cursor(conn: sqlite3.Connection, table: str) -> tuple[str, list[str], sqlite3.Cursor]:
    """Open a cursor over the full table, ordered by id when available."""
    normalized = require_table(conn, table)
    cur = conn.execute(_ordered_select_sql(conn, normalized))
    header = [str(item[0]) for item in cur.description or []]
    return normalized, header, cur
