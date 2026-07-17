from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    return [str(row["name"]) for row in rows]


def columns(conn: sqlite3.Connection, table_name: str) -> list[dict[str, Any]]:
    rows = conn.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()
    return [
        {
            "name": str(row["name"]),
            "type": str(row["type"]),
            "notNull": bool(row["notnull"]),
            "default": row["dflt_value"],
            "primaryKeyPosition": int(row["pk"]),
            "section": None,
        }
        for row in rows
    ]


def indexes(conn: sqlite3.Connection, table_name: str) -> list[dict[str, Any]]:
    rows = conn.execute(f"PRAGMA index_list({_quote_identifier(table_name)})").fetchall()
    index_payloads: list[dict[str, Any]] = []
    for row in rows:
        index_name = str(row["name"])
        index_columns = conn.execute(f"PRAGMA index_info({_quote_identifier(index_name)})").fetchall()
        index_payloads.append(
            {
                "name": index_name,
                "unique": bool(row["unique"]),
                "origin": str(row["origin"]),
                "columns": [str(index_row["name"]) for index_row in index_columns],
            }
        )
    return index_payloads


def foreign_keys(conn: sqlite3.Connection, table_name: str) -> list[dict[str, str]]:
    rows = conn.execute(f"PRAGMA foreign_key_list({_quote_identifier(table_name)})").fetchall()
    return [
        {
            "column": str(row["from"]),
            "referencesTable": str(row["table"]),
            "referencesColumn": str(row["to"]),
            "onUpdate": str(row["on_update"]),
            "onDelete": str(row["on_delete"]),
        }
        for row in rows
    ]


def build_payload_from_connection(
    conn: sqlite3.Connection,
    *,
    source: str,
    title: str = "Database Diagram Viewer",
) -> dict[str, Any]:
    names = table_names(conn)
    tables: list[dict[str, Any]] = []
    for table_name in names:
        tables.append(
            {
                "name": table_name,
                "section": None,
                "columns": columns(conn, table_name),
                "indexes": indexes(conn, table_name),
                "foreignKeys": foreign_keys(conn, table_name),
            }
        )
    return {
        "title": title,
        "source": source,
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "sections": [],
        "tables": tables,
        "views": [
            {
                "id": "overview",
                "label": "Full overview",
                "description": "All tables and foreign-key relationships from the inspected SQLite database.",
                "tables": names,
            }
        ],
    }


def build_payload_from_database_path(
    database_path: Path,
    *,
    title: str = "Database Diagram Viewer",
) -> dict[str, Any]:
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    try:
        return build_payload_from_connection(conn, source=str(database_path), title=title)
    finally:
        conn.close()
