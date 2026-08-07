"""Read-only access to any table by name, for the operator export/preview feature.

Deliberately not scoped to one business context: the operator chooses the table at
runtime, so this module takes a table *name* where every other module in the package
has its table fixed in the SQL it owns.

A table name cannot be a bound parameter, so it is interpolated into the query. That
is why both entry points resolve their table through :func:`require_table` first:
:func:`normalize_table_name` strips the input to ``[a-z0-9_]`` and existence is
checked against ``sqlite_master`` before any name reaches a statement. A new read
added here must go through the same gate.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

DEFAULT_EXPORT_TABLES: tuple[str, ...] = (
    "accounts",
    "equity_snapshots",
    "orders",
    "order_fills",
    "backtest_runs",
    "backtest_executions",
)


@dataclass(frozen=True)
class TableRows:
    table: str
    header: list[str]
    rows: list[list[str]]
    truncated: bool


def normalize_table_name(name: str) -> str:
    cleaned = "".join(ch for ch in name.strip().lower() if ch.isalnum() or ch == "_")
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


def fetch_table_rows(conn: sqlite3.Connection, table: str, *, limit: int) -> TableRows:
    normalized = require_table(conn, table)

    query = f"{_ordered_select_sql(conn, normalized)} LIMIT ?"
    cur = conn.execute(query, (limit + 1,))

    header = [str(item[0]) for item in cur.description or []]
    rows = [[str(cell) if cell is not None else "" for cell in row] for row in cur]

    truncated = len(rows) > limit
    if truncated:
        rows = rows[:limit]

    return TableRows(table=normalized, header=header, rows=rows, truncated=truncated)


def fetch_table_cursor(conn: sqlite3.Connection, table: str) -> tuple[str, list[str], sqlite3.Cursor]:
    """Open a cursor over the full table, ordered by id when available."""
    normalized = require_table(conn, table)
    cur = conn.execute(_ordered_select_sql(conn, normalized))
    header = [str(item[0]) for item in cur.description or []]
    return normalized, header, cur
