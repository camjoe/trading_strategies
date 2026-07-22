from __future__ import annotations

import re
import sqlite3

from scripts.data_ops import build_database_diagram_viewer
from tests.support.db_schema import memory_db_at_head


def _fresh_conn() -> sqlite3.Connection:
    return memory_db_at_head()


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
    account_column_names = {str(column["name"]) for column in accounts["columns"]}
    # Revision 0003 removed the account rotation columns; rotation config is book-owned.
    assert not {name for name in account_column_names if name.startswith("rotation_")}

    rotation_settings = _table(payload, "book_rotation_settings")
    assert rotation_settings["section"] == {"id": "rotations", "label": "Rotations", "color": "#d97706"}
    rotation_column_names = {str(column["name"]) for column in rotation_settings["columns"]}
    assert "rotation_schedule" in rotation_column_names
    assert "rotation_mode" not in rotation_column_names
    assert "regime_strategy_risk_on_id" not in rotation_column_names
    assert "overlay_mode" not in rotation_column_names
    assert rotation_settings["foreignKeys"] == [
        {
            "column": "book_id",
            "referencesTable": "books",
            "referencesColumn": "id",
            "onUpdate": "NO ACTION",
            "onDelete": "CASCADE",
        }
    ]

    backtest_snapshots = _table(payload, "backtest_equity_snapshots")
    assert backtest_snapshots["section"] == {"id": "research", "label": "Research", "color": "#7c3aed"}


def test_payload_defines_expected_focused_views() -> None:
    conn = _fresh_conn()
    try:
        payload = build_database_diagram_viewer.build_diagram_payload(conn)
    finally:
        conn.close()

    views = {str(view["id"]): view for view in payload["views"]}
    assert {
        "overview",
        "account_deletion",
        "book_execution",
        "research",
        "promotion_governance",
        "risk_controls",
        "catalogs",
    } <= set(views)
    assert "accounts" in views["account_deletion"]["tables"]
    assert "book_strategy_history" in views["book_execution"]["tables"]


def test_payload_defines_category_views_with_account_and_book_anchors() -> None:
    conn = _fresh_conn()
    try:
        payload = build_database_diagram_viewer.build_diagram_payload(conn)
    finally:
        conn.close()

    category_views = {str(view["id"]): view for view in payload["categoryViews"]}
    expected_ids = {
        *(
            f"category_{section['id']}"
            for section in build_database_diagram_viewer.SECTION_DEFINITIONS
            if section["id"] != "accounts"
        ),
    }
    assert set(category_views) == expected_ids
    assert all({"accounts", "books"} <= set(view["tables"]) for view in category_views.values())


def test_payload_separates_performance_promotion_and_risk_domains() -> None:
    conn = _fresh_conn()
    try:
        payload = build_database_diagram_viewer.build_diagram_payload(conn)
    finally:
        conn.close()

    assert _table(payload, "equity_snapshots")["section"]["id"] == "performance"
    assert _table(payload, "daily_metrics")["section"]["id"] == "performance"
    assert _table(payload, "promotion_reviews")["section"]["id"] == "promotion"
    assert _table(payload, "promotion_review_events")["section"]["id"] == "promotion"
    assert _table(payload, "risk_snapshots")["section"]["id"] == "risk"
    assert _table(payload, "risk_decisions")["section"]["id"] == "risk"


def test_payload_role_views_partition_every_table() -> None:
    conn = _fresh_conn()
    try:
        payload = build_database_diagram_viewer.build_diagram_payload(conn)
    finally:
        conn.close()

    role_views = {str(view["id"]): view for view in payload["roleViews"]}
    assert set(role_views) == {
        "role_operational_state",
        "role_temporal_history",
        "role_decision_logs",
        "role_snapshots",
        "role_provenance",
    }
    # A few anchor classifications from the audit-architecture discussion.
    assert "rotation_decisions" in role_views["role_decision_logs"]["tables"]
    assert "book_strategy_history" in role_views["role_temporal_history"]["tables"]
    assert "promotion_reviews" in role_views["role_provenance"]["tables"]

    # The roles must be an exhaustive, disjoint partition of the schema.
    all_tables = {str(table["name"]) for table in payload["tables"]}
    role_tables = [name for view in role_views.values() for name in view["tables"]]
    assert sorted(role_tables) == sorted(all_tables)
    assert len(role_tables) == len(set(role_tables))


def test_build_html_contains_viewer_controls_and_schema_payload() -> None:
    html = build_database_diagram_viewer.build_html()

    assert "Trading Strategies Database Diagram Viewer" in html
    assert re.search(r"Generated: \d{2}:\d{2} \d{2}-\d{2}-\d{4} PST\.", html)
    assert "Full overview" in html
    assert "Account deletion" in html
    assert "Book execution spine" in html
    assert "schema-payload" in html
    assert "categoryTabs" in html
    assert "section-label" in html
    assert "groupedTables" in html
    assert "info-panel" in html
    assert "colorKey" in html
    assert "attachSectionDragHandlers" in html
    assert "restackDefaultLayout" in html
    assert "layoutMarginX" in html
    assert 'id="zoomIn"' not in html
    assert 'id="zoomOut"' not in html
    assert 'addEventListener("wheel"' in html
    assert "toggleConstraints" in html
    assert "toggleDeleteActions" in html
    assert "fk-arrow" in html
    assert 'markerWidth="11"' in html
    assert 'markerHeight="8"' in html
    assert "edgePoint" not in html
    assert "cardBounds" in html
    assert "columnBounds" in html
    assert "combineRelationships" in html
    assert "relationshipSourceBounds" in html
    assert "targetAnchorBounds" in html
    assert "targetSlotAssignments" in html
    assert "arrowStorageKey" in html
    assert "sectionStorageKey" in html
    assert "loadJson" in html
    assert "saveJson" in html
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
    assert "scoreRoute" in html
    assert "routeTableCrossingCount" in html
    assert "ROUTE_BEND_PENALTY" in html
    assert "routeBendCount" in html
    assert "routeOverlapScore" in html
    assert "routeOverlapCount" in html
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
    assert 'id="search"' not in html
    assert 'id="zoomReset"' not in html
    assert 'id="resetLayout"' not in html
    assert "Drag table cards or category titles independently" in html
    assert "child/FK table points to referenced parent table" in html
