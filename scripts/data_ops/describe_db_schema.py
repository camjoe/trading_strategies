from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from infrastructure.database import migration_runner
from infrastructure.database.config import get_db_path


def _connect_fresh_schema() -> sqlite3.Connection:
    conn = migration_runner.build_reference_connection()
    # Code-defined application schema only — Alembic bookkeeping is not part of it.
    conn.execute("DROP TABLE alembic_version")
    return conn


def _connect_live_schema() -> sqlite3.Connection:
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _table_names(conn: sqlite3.Connection) -> list[str]:
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


def _columns(conn: sqlite3.Connection, table_name: str) -> list[dict[str, Any]]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    columns: list[dict[str, Any]] = []
    for row in rows:
        columns.append(
            {
                "name": row["name"],
                "type": row["type"],
                "not_null": bool(row["notnull"]),
                "default": row["dflt_value"],
                "primary_key_position": row["pk"],
            }
        )
    return columns


def _indexes(conn: sqlite3.Connection, table_name: str) -> list[dict[str, Any]]:
    rows = conn.execute(f"PRAGMA index_list({table_name})").fetchall()
    indexes: list[dict[str, Any]] = []
    for row in rows:
        index_name = str(row["name"])
        index_columns = conn.execute(f"PRAGMA index_info({index_name})").fetchall()
        indexes.append(
            {
                "name": index_name,
                "unique": bool(row["unique"]),
                "origin": row["origin"],
                "columns": [str(index_row["name"]) for index_row in index_columns],
            }
        )
    return indexes


def _schema_payload(conn: sqlite3.Connection, source: str, db_path: Path | None) -> dict[str, Any]:
    tables: list[dict[str, Any]] = []
    for table_name in _table_names(conn):
        tables.append(
            {
                "name": table_name,
                "columns": _columns(conn, table_name),
                "indexes": _indexes(conn, table_name),
            }
        )
    return {
        "source": source,
        "db_path": str(db_path) if db_path is not None else None,
        "tables": tables,
    }


def _print_text(payload: dict[str, Any]) -> None:
    source = str(payload["source"])
    db_path = payload["db_path"]
    print(f"Schema source: {source}")
    if db_path:
        print(f"Database path: {db_path}")
    print(f"Tables: {len(payload['tables'])}")

    for table in payload["tables"]:
        print(f"\n[{table['name']}]")
        for column in table["columns"]:
            parts = [f"{column['name']} {column['type']}".strip()]
            if column["primary_key_position"]:
                parts.append("PRIMARY KEY")
            if column["not_null"]:
                parts.append("NOT NULL")
            if column["default"] is not None:
                parts.append(f"DEFAULT {column['default']}")
            print(f"- {' '.join(parts)}")

        if table["indexes"]:
            print("Indexes:")
            for index in table["indexes"]:
                qualifier = "UNIQUE " if index["unique"] else ""
                columns = ", ".join(index["columns"])
                print(f"- {qualifier}{index['name']} ({columns})")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Describe the trading database schema from the canonical code-defined "
            "schema or from the configured live SQLite database."
        ),
    )
    parser.add_argument(
        "--source",
        choices=("fresh", "live"),
        default="fresh",
        help="Read schema from an in-memory database initialized from code, or from the live configured DB.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    conn = _connect_fresh_schema() if args.source == "fresh" else _connect_live_schema()
    db_path = get_db_path() if args.source == "live" else None
    try:
        payload = _schema_payload(conn, source=args.source, db_path=db_path)
    finally:
        conn.close()

    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_text(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
