from __future__ import annotations

import argparse
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from common.paths.project_paths import REPO_ROOT
from infrastructure.database import migration_runner
from scripts.database_diagrams.html_viewer import render_html
from scripts.database_diagrams.sqlite_introspection import (
    columns,
    foreign_keys,
    indexes,
    table_names,
)

DEFAULT_OUTPUT_PATH = REPO_ROOT / "docs" / "reference" / "database-diagram-viewer.html"

SECTION_DEFINITIONS: tuple[dict[str, object], ...] = (
    {
        "id": "accounts",
        "label": "Accounts",
        "color": "#2563eb",
        "tables": ("accounts", "trades"),
    },
    {
        "id": "books",
        "label": "Books",
        "color": "#0f8b5f",
        "tables": ("books", "book_execution_settings", "book_option_settings", "positions", "ledger"),
    },
    {
        "id": "orders",
        "label": "Orders",
        "color": "#dc2626",
        "tables": ("orders", "order_fills"),
    },
    {
        "id": "snapshots",
        "label": "Snapshots and metrics",
        "color": "#0891b2",
        "tables": ("equity_snapshots", "daily_metrics", "backtest_equity_snapshots", "risk_snapshots"),
    },
    {
        "id": "rotations",
        "label": "Rotations",
        "color": "#d97706",
        "tables": ("book_rotation_settings", "book_strategy_assignments", "rotation_decisions"),
    },
    {
        "id": "research",
        "label": "Research",
        "color": "#7c3aed",
        "tables": ("backtest_runs", "backtest_trades", "walk_forward_groups", "walk_forward_group_runs"),
    },
    {
        "id": "governance",
        "label": "Promotion and risk",
        "color": "#db2777",
        "tables": ("promotion_reviews", "promotion_review_events", "risk_decisions"),
    },
    {
        "id": "catalogs",
        "label": "Catalogs and settings",
        "color": "#64748b",
        "tables": ("strategies", "feature_providers", "global_settings"),
    },
)

ACCOUNT_COLUMN_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "books",
        ("goal_", "learning_", "risk_policy", "stop_", "take_", "trade_size_", "max_", "instrument_", "option_"),
    ),
    ("rotations", ("rotation_",)),
    ("orders", ("broker_", "live_trading_")),
    ("snapshots", ("benchmark_",)),
)

VIEW_DEFINITIONS: tuple[dict[str, object], ...] = (
    {
        "id": "overview",
        "label": "Full overview",
        "description": "All tables and foreign-key relationships from the fresh code-defined schema.",
        "tables": "all",
    },
    {
        "id": "account_deletion",
        "label": "Account deletion",
        "description": "Tables affected directly or indirectly when account deletion behavior changes.",
        "tables": (
            "accounts",
            "trades",
            "books",
            "orders",
            "order_fills",
            "equity_snapshots",
            "daily_metrics",
            "rotation_decisions",
            "positions",
            "ledger",
            "backtest_runs",
            "backtest_trades",
            "backtest_equity_snapshots",
            "walk_forward_groups",
            "walk_forward_group_runs",
            "promotion_reviews",
            "promotion_review_events",
            "risk_snapshots",
            "risk_decisions",
        ),
    },
    {
        "id": "book_execution",
        "label": "Book execution spine",
        "description": "Book-owned runtime state, orders, accounting, metrics, and strategy assignment tables.",
        "tables": (
            "accounts",
            "books",
            "book_execution_settings",
            "book_option_settings",
            "book_rotation_settings",
            "book_strategy_assignments",
            "strategies",
            "orders",
            "order_fills",
            "positions",
            "ledger",
            "equity_snapshots",
            "daily_metrics",
            "rotation_decisions",
        ),
    },
    {
        "id": "research",
        "label": "Research and evaluation",
        "description": "Backtest and walk-forward tables plus their account and strategy anchors.",
        "tables": (
            "accounts",
            "strategies",
            "backtest_runs",
            "backtest_trades",
            "backtest_equity_snapshots",
            "walk_forward_groups",
            "walk_forward_group_runs",
        ),
    },
    {
        "id": "governance",
        "label": "Promotion and risk governance",
        "description": "Promotion review, event, risk snapshot, and risk decision relationships.",
        "tables": (
            "accounts",
            "books",
            "promotion_reviews",
            "promotion_review_events",
            "risk_snapshots",
            "risk_decisions",
        ),
    },
    {
        "id": "catalogs",
        "label": "Shared catalogs",
        "description": "Shared configuration and catalog tables that are not owned by account deletion.",
        "tables": (
            "strategies",
            "feature_providers",
            "global_settings",
            "book_rotation_settings",
            "book_strategy_assignments",
            "orders",
            "rotation_decisions",
            "backtest_runs",
            "walk_forward_groups",
        ),
    },
)

SECTION_BY_TABLE = {
    table_name: str(section["id"]) for section in SECTION_DEFINITIONS for table_name in section["tables"]
}
SECTION_BY_ID = {str(section["id"]): section for section in SECTION_DEFINITIONS}


def _connect_fresh_schema() -> sqlite3.Connection:
    conn = migration_runner.build_reference_connection()
    # Code-defined application schema only — Alembic bookkeeping is not part of it.
    conn.execute("DROP TABLE alembic_version")
    return conn


def _section_payload(section_id: str | None) -> dict[str, str] | None:
    if section_id is None:
        return None
    section = SECTION_BY_ID.get(section_id)
    if section is None:
        return None
    return {
        "id": str(section["id"]),
        "label": str(section["label"]),
        "color": str(section["color"]),
    }


def _column_section_id(table_name: str, column_name: str, foreign_keys: list[dict[str, str]]) -> str | None:
    for foreign_key in foreign_keys:
        if foreign_key["column"] == column_name:
            return SECTION_BY_TABLE.get(foreign_key["referencesTable"])

    if table_name == "accounts":
        for section_id, prefixes in ACCOUNT_COLUMN_SECTIONS:
            if any(column_name.startswith(prefix) for prefix in prefixes):
                return section_id
    return None


def build_diagram_payload(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return the schema payload consumed by the HTML diagram viewer.

    Uses the project-agnostic introspection from ``scripts.database_diagrams``
    and decorates the neutral payload with this repo's section and view metadata.
    """
    names = table_names(conn)
    tables: list[dict[str, Any]] = []
    for table_name in names:
        table_foreign_keys = foreign_keys(conn, table_name)
        table_columns = columns(conn, table_name)
        for column in table_columns:
            column["section"] = _section_payload(
                _column_section_id(table_name, str(column["name"]), table_foreign_keys)
            )
        tables.append(
            {
                "name": table_name,
                "section": _section_payload(SECTION_BY_TABLE.get(table_name)),
                "columns": table_columns,
                "indexes": indexes(conn, table_name),
                "foreignKeys": table_foreign_keys,
            }
        )
    table_set = set(names)
    views: list[dict[str, object]] = []
    for view in VIEW_DEFINITIONS:
        view_tables = names if view["tables"] == "all" else [name for name in view["tables"] if name in table_set]
        views.append(
            {
                "id": view["id"],
                "label": view["label"],
                "description": view["description"],
                "tables": view_tables,
            }
        )
    return {
        "title": "Trading Strategies Database Diagram Viewer",
        "source": "fresh code schema",
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "sections": SECTION_DEFINITIONS,
        "tables": tables,
        "views": views,
    }


def build_html() -> str:
    """Build the self-contained database diagram viewer HTML."""
    conn = _connect_fresh_schema()
    try:
        payload = build_diagram_payload(conn)
    finally:
        conn.close()
    return render_html(payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a self-contained HTML database diagram viewer from the fresh code-defined schema.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Output HTML path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    html_text = build_html()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html_text, encoding="utf-8")
    print(f"Wrote database diagram viewer: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
