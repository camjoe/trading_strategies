from __future__ import annotations

import json
import sqlite3

from scripts.database_diagrams.html_viewer import render_html
from scripts.database_diagrams.render_html import load_payload
from scripts.database_diagrams.sqlite_introspection import build_payload_from_connection


def test_sqlite_introspection_builds_neutral_payload() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        );
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
        );
        CREATE INDEX idx_orders_account_id ON orders(account_id);
        """
    )
    try:
        payload = build_payload_from_connection(conn, source="test sqlite", title="Test DB")
    finally:
        conn.close()

    assert payload["title"] == "Test DB"
    assert payload["source"] == "test sqlite"
    assert payload["sections"] == []
    assert payload["views"] == [
        {
            "id": "overview",
            "label": "Full overview",
            "description": "All tables and foreign-key relationships from the inspected SQLite database.",
            "tables": ["accounts", "orders"],
        }
    ]

    orders = next(table for table in payload["tables"] if table["name"] == "orders")
    assert orders["section"] is None
    assert any(index["name"] == "idx_orders_account_id" for index in orders["indexes"])
    assert orders["foreignKeys"] == [
        {
            "column": "account_id",
            "referencesTable": "accounts",
            "referencesColumn": "id",
            "onUpdate": "NO ACTION",
            "onDelete": "CASCADE",
        }
    ]


def test_generic_renderer_uses_payload_title_and_source() -> None:
    payload = {
        "title": "External Project Database",
        "source": "neutral schema json",
        "generatedAt": "2026-07-12T00:00:00+00:00",
        "sections": [],
        "tables": [],
        "views": [{"id": "overview", "label": "Full overview", "description": "All tables", "tables": []}],
    }

    html = render_html(payload)

    assert "<title>External Project Database</title>" in html
    assert "<h1>External Project Database</h1>" in html
    assert "Source: neutral schema json." in html
    assert "schema-payload" in html


def test_render_cli_loader_requires_object_payload(tmp_path) -> None:
    payload_path = tmp_path / "schema.json"
    payload_path.write_text(json.dumps({"tables": []}), encoding="utf-8")

    assert load_payload(payload_path) == {"tables": []}
