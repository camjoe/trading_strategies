from __future__ import annotations

import sqlite3

from infrastructure.database.init import init_schema
from scripts.data_ops import build_database_diagram_viewer


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
    raise AssertionError(f"Missing table in diagram payload: {table_name}")


def test_payload_includes_columns_indexes_and_fk_actions() -> None:
    conn = _fresh_conn()
    try:
        payload = build_database_diagram_viewer.build_diagram_payload(conn)
    finally:
        conn.close()

    books = _table(payload, "books")
    column_names = {str(column["name"]) for column in books["columns"]}
    assert {"id", "account_id", "name"} <= column_names
    assert any(index["name"] == "idx_books_default_per_account" for index in books["indexes"])
    assert books["foreignKeys"] == [
        {
            "column": "account_id",
            "referencesTable": "accounts",
            "referencesColumn": "id",
            "onUpdate": "NO ACTION",
            "onDelete": "CASCADE",
        }
    ]
    assert books["section"] == {"id": "books", "label": "Books", "color": "#0f8b5f"}

    accounts = _table(payload, "accounts")
    rotation_column = next(column for column in accounts["columns"] if column["name"] == "rotation_enabled")
    assert rotation_column["section"] == {"id": "rotations", "label": "Rotations", "color": "#d97706"}


def test_payload_defines_expected_focused_views() -> None:
    conn = _fresh_conn()
    try:
        payload = build_database_diagram_viewer.build_diagram_payload(conn)
    finally:
        conn.close()

    views = {str(view["id"]): view for view in payload["views"]}
    assert {"overview", "account_deletion", "book_execution", "research", "governance", "catalogs"} <= set(views)
    assert "accounts" in views["account_deletion"]["tables"]
    assert "book_strategy_assignments" in views["book_execution"]["tables"]


def test_build_html_contains_viewer_controls_and_schema_payload() -> None:
    html = build_database_diagram_viewer.build_html()

    assert "Trading Strategies Database Diagram Viewer" in html
    assert "Full overview" in html
    assert "Account deletion" in html
    assert "Book execution spine" in html
    assert "schema-payload" in html
    assert "section-label" in html
    assert "groupedTables" in html
    assert "info-panel" in html
    assert "colorKey" in html
    assert "attachSectionDragHandlers" in html
    assert "zoomIn" in html
    assert "toggleConstraints" in html
    assert "toggleDeleteActions" in html
    assert "fk-arrow" in html
    assert 'markerWidth="11"' in html
    assert 'markerHeight="8"' in html
    assert "edgePoint" in html
    assert "cardBounds" in html
    assert "columnBounds" in html
    assert "combineRelationships" in html
    assert "relationshipSourceBounds" in html
    assert "targetAnchorBounds" in html
    assert "targetSlotAssignments" in html
    assert "arrowStorageKey" in html
    assert "attachArrowDragHandle" in html
    assert "handleArrowPointerMove" in html
    assert "handleArrowPointerUp" in html
    assert 'window.addEventListener("pointermove", handleArrowPointerMove)' in html
    assert "saveArrowTarget" in html
    assert "ns-resize" in html
    assert "sideOffsetPoint" in html
    assert "routeRespectsEndpointDirection" in html
    assert "sourceTurnsBack" in html
    assert "targetTurnsBack" in html
    assert 'data-column="' in html
    assert "routeRelationship" in html
    assert "routeCandidates" in html
    assert "routeBendCount" in html
    assert "routeOverlapScore" in html
    assert "segmentOverlapLength" in html
    assert "obstacleAvoidanceCandidates" in html
    assert "simplifyRoute(points, 2)" in html
    assert "routedPathData" in html
    assert "segmentCrossing" in html
    assert "appendSegmentWithBridges" in html
    assert "relationshipLaneOffset" in html
    assert "bridgedCrossings" in html
    assert "reserveBridge" in html
    assert "oppositeSide" not in html
    assert 'side === "top"' not in html
    assert 'side === "bottom"' not in html
    assert "resetLayout" in html
    assert "Drag table cards" in html
    assert "child/FK table points to referenced parent table" in html
