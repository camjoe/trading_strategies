from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from infrastructure.database.config import get_db_path
from infrastructure.database.init import init_schema

ACCOUNT_DELETE_RELATED_TABLES = (
    "trades",
    "books",
    "equity_snapshots",
    "backtest_runs",
    "backtest_trades",
    "backtest_equity_snapshots",
    "walk_forward_groups",
    "walk_forward_group_runs",
    "promotion_reviews",
    "promotion_review_events",
    "orders",
    "order_fills",
    "positions",
    "ledger",
    "risk_snapshots",
    "risk_decisions",
)


def _connect_fresh_schema() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_schema(conn)
    return conn


def _connect_live_schema() -> sqlite3.Connection:
    db_path = get_db_path()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
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


def _foreign_keys(conn: sqlite3.Connection, table_name: str) -> list[dict[str, str]]:
    rows = conn.execute(f"PRAGMA foreign_key_list({table_name})").fetchall()
    return [
        {
            "column": str(row["from"]),
            "references_table": str(row["table"]),
            "references_column": str(row["to"]),
            "on_update": str(row["on_update"]),
            "on_delete": str(row["on_delete"]),
        }
        for row in rows
    ]


def _foreign_key_violations(conn: sqlite3.Connection) -> list[dict[str, object]]:
    rows = conn.execute("PRAGMA foreign_key_check").fetchall()
    return [
        {
            "table": row["table"],
            "rowid": row["rowid"],
            "parent": row["parent"],
            "fkid": row["fkid"],
        }
        for row in rows
    ]


def _selected_tables(conn: sqlite3.Connection, scope: str) -> list[str]:
    all_tables = set(_table_names(conn))
    if scope == "all":
        return sorted(all_tables)
    return [table for table in ACCOUNT_DELETE_RELATED_TABLES if table in all_tables]


def audit_payload(conn: sqlite3.Connection, *, source: str, scope: str, db_path: Path | None) -> dict[str, Any]:
    tables = [
        {
            "name": table_name,
            "foreign_keys": _foreign_keys(conn, table_name),
        }
        for table_name in _selected_tables(conn, scope)
    ]
    row = conn.execute("PRAGMA foreign_keys").fetchone()
    return {
        "source": source,
        "scope": scope,
        "db_path": str(db_path) if db_path is not None else None,
        "foreign_keys_enabled": bool(row[0]) if row is not None else False,
        "foreign_key_violations": _foreign_key_violations(conn),
        "tables": tables,
    }


def _print_text(payload: dict[str, Any]) -> None:
    print(f"Foreign key audit source: {payload['source']}")
    print(f"Scope: {payload['scope']}")
    if payload["db_path"]:
        print(f"Database path: {payload['db_path']}")
    print(f"Foreign keys enabled: {payload['foreign_keys_enabled']}")
    print(f"Foreign key violations: {len(payload['foreign_key_violations'])}")

    for table in payload["tables"]:
        print(f"\n[{table['name']}]")
        foreign_keys = table["foreign_keys"]
        if not foreign_keys:
            print("- no foreign keys")
            continue
        for fk in foreign_keys:
            print(
                f"- {fk['column']} -> {fk['references_table']}.{fk['references_column']} ON DELETE {fk['on_delete']}"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit SQLite foreign-key actions without modifying the trading database.",
    )
    parser.add_argument(
        "--source",
        choices=("fresh", "live"),
        default="fresh",
        help="Audit an in-memory database initialized from code, or the configured live SQLite database.",
    )
    parser.add_argument(
        "--scope",
        choices=("account-deletion", "all"),
        default="account-deletion",
        help="Limit output to account-deletion-related tables, or include every table.",
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
        payload = audit_payload(conn, source=args.source, scope=args.scope, db_path=db_path)
    finally:
        conn.close()

    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_text(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
