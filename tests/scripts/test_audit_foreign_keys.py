from __future__ import annotations

import sqlite3
import sys

from infrastructure.database.init import init_schema
from scripts.data_ops import audit_foreign_keys


def _fresh_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_schema(conn)
    return conn


def _table(payload: dict[str, object], table_name: str) -> dict[str, object]:
    tables = payload["tables"]
    assert isinstance(tables, list)
    for table in tables:
        assert isinstance(table, dict)
        if table["name"] == table_name:
            return table
    raise AssertionError(f"Missing table in audit payload: {table_name}")


def test_account_deletion_scope_reports_known_cascade_and_no_action() -> None:
    conn = _fresh_conn()
    try:
        payload = audit_foreign_keys.audit_payload(
            conn,
            source="fresh",
            scope="account-deletion",
            db_path=None,
        )
    finally:
        conn.close()

    assert payload["foreign_keys_enabled"] is True
    assert payload["foreign_key_violations"] == []

    books = _table(payload, "books")
    trades = _table(payload, "trades")
    assert books["foreign_keys"] == [
        {
            "column": "account_id",
            "references_table": "accounts",
            "references_column": "id",
            "on_update": "NO ACTION",
            "on_delete": "CASCADE",
        }
    ]
    assert trades["foreign_keys"] == [
        {
            "column": "account_id",
            "references_table": "accounts",
            "references_column": "id",
            "on_update": "NO ACTION",
            "on_delete": "CASCADE",
        }
    ]

    # walk_forward_group_runs.run_id stays NO ACTION deliberately: a backtest run
    # that belongs to a walk-forward group must not disappear out from under it.
    group_runs = _table(payload, "walk_forward_group_runs")
    run_fk = next(fk for fk in group_runs["foreign_keys"] if fk["references_table"] == "backtest_runs")
    assert run_fk["on_delete"] == "NO ACTION"


def test_all_scope_includes_tables_outside_account_deletion_scope() -> None:
    conn = _fresh_conn()
    try:
        payload = audit_foreign_keys.audit_payload(conn, source="fresh", scope="all", db_path=None)
    finally:
        conn.close()

    table_names = {str(table["name"]) for table in payload["tables"]}
    assert "accounts" in table_names
    assert "global_settings" in table_names


def test_parse_args_defaults_to_fresh_account_deletion_text(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["scripts.data_ops.audit_foreign_keys"])

    args = audit_foreign_keys.parse_args()

    assert args.source == "fresh"
    assert args.scope == "account-deletion"
    assert args.format == "text"
