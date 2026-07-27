from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timedelta, timezone
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
PST = timezone(timedelta(hours=-8), name="PST")

SECTION_DEFINITIONS: tuple[dict[str, object], ...] = (
    {
        "id": "accounts",
        "label": "Accounts",
        "color": "#2563eb",
        "tables": ("accounts",),
    },
    {
        "id": "books",
        "label": "Books",
        "color": "#0f8b5f",
        "tables": ("books", "book_universe_history", "positions", "ledger"),
    },
    {
        "id": "orders",
        "label": "Orders",
        "color": "#dc2626",
        "tables": ("orders", "order_fills"),
    },
    {
        "id": "performance",
        "label": "Performance and metrics",
        "color": "#0891b2",
        "tables": ("equity_snapshots", "daily_metrics"),
    },
    {
        "id": "rotations",
        "label": "Rotations",
        "color": "#d97706",
        "tables": (
            "book_rotation_settings",
            "book_rotation_settings_change_events",
            "book_strategy_history",
            "rotation_decisions",
        ),
    },
    {
        "id": "research",
        "label": "Research",
        "color": "#7c3aed",
        "tables": (
            "backtest_runs",
            "backtest_executions",
            "backtest_equity_snapshots",
            "optimization_experiments",
            "optimization_windows",
            "optimization_trials",
            "optimization_run_manifests",
        ),
    },
    {
        "id": "promotion",
        "label": "Promotion governance",
        "color": "#db2777",
        "tables": ("promotion_reviews", "promotion_review_events"),
    },
    {
        "id": "risk",
        "label": "Risk controls",
        "color": "#0f766e",
        "tables": ("risk_snapshots", "risk_decisions"),
    },
    {
        "id": "catalogs",
        "label": "Catalogs and settings",
        "color": "#64748b",
        "tables": ("strategies", "feature_providers", "global_settings", "global_settings_change_events"),
    },
)

ACCOUNT_COLUMN_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("orders", ("broker_", "live_trading_")),
    ("performance", ("benchmark_",)),
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
            "books",
            "book_universe_history",
            "orders",
            "order_fills",
            "equity_snapshots",
            "daily_metrics",
            "rotation_decisions",
            "positions",
            "ledger",
            "backtest_runs",
            "backtest_executions",
            "backtest_equity_snapshots",
            "optimization_experiments",
            "optimization_windows",
            "optimization_trials",
            "optimization_run_manifests",
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
            "book_universe_history",
            "book_rotation_settings",
            "book_rotation_settings_change_events",
            "book_strategy_history",
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
            "backtest_executions",
            "backtest_equity_snapshots",
            "optimization_experiments",
            "optimization_windows",
            "optimization_trials",
            "optimization_run_manifests",
        ),
    },
    {
        "id": "promotion_governance",
        "label": "Promotion governance",
        "description": "Promotion review cases, event history, and their account and strategy anchors.",
        "tables": (
            "accounts",
            "strategies",
            "promotion_reviews",
            "promotion_review_events",
        ),
    },
    {
        "id": "risk_controls",
        "label": "Runtime risk controls",
        "description": "Account risk snapshots and pre-submit risk decisions, including book ownership.",
        "tables": (
            "accounts",
            "books",
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
            "global_settings_change_events",
            "book_rotation_settings",
            "book_rotation_settings_change_events",
            "book_strategy_history",
            "orders",
            "rotation_decisions",
            "backtest_runs",
        ),
    },
)

# Data-role classification: the five canonical roles a production schema sorts
# into. Unlike the domain sections/views above (which group tables by subject
# area), these group every table by *how* it is used — mutable current state vs.
# append-only logs vs. derived series — as a legibility lens over the whole
# schema. Together they partition all tables (enforced by a build-time check and
# a test), so the row doubles as a "is every table classified?" audit.
ROLE_DEFINITIONS: tuple[dict[str, object], ...] = (
    {
        "id": "role_operational_state",
        "label": "Operational state",
        "description": (
            "Mutable system-of-record tables: identity, configuration, catalogs, and live positions. "
            "Updated in place; they hold what is true now, not a history of changes."
        ),
        "tables": (
            "accounts",
            "books",
            "positions",
            "book_rotation_settings",
            "strategies",
            "feature_providers",
            "global_settings",
        ),
    },
    {
        "id": "role_temporal_history",
        "label": "Temporal history",
        "description": (
            "Effective-dated (valid-time / SCD Type 2) tables: one open row plus closed prior rows, "
            "bounded by effective_from/effective_to, reconstructing what was active at any past time."
        ),
        "tables": (
            "book_strategy_history",
            "book_universe_history",
        ),
    },
    {
        "id": "role_decision_logs",
        "label": "Decisions and execution events",
        "description": (
            "Automated decisions and execution/accounting events. Decision, fill, ledger, and review "
            "event rows preserve history; order rows are mutable lifecycle records reconciled in place."
        ),
        "tables": (
            "orders",
            "order_fills",
            "ledger",
            "rotation_decisions",
            "risk_decisions",
            "promotion_review_events",
            "global_settings_change_events",
            "book_rotation_settings_change_events",
        ),
    },
    {
        "id": "role_snapshots",
        "label": "Snapshots and time-series",
        "description": (
            "Periodic materialized state and computed results captured at a point in time: equity and "
            "risk snapshots, daily metrics, and backtest / walk-forward outputs."
        ),
        "tables": (
            "equity_snapshots",
            "risk_snapshots",
            "daily_metrics",
            "backtest_runs",
            "backtest_executions",
            "backtest_equity_snapshots",
            "optimization_experiments",
            "optimization_windows",
            "optimization_trials",
            "optimization_run_manifests",
        ),
    },
    {
        "id": "role_provenance",
        "label": "Provenance",
        "description": (
            "Frozen decision inputs: the full evaluation and assessment payload captured at decision "
            "time, so a past promotion decision can be re-justified against what it actually saw."
        ),
        "tables": ("promotion_reviews",),
    },
)

SECTION_BY_TABLE = {
    table_name: str(section["id"]) for section in SECTION_DEFINITIONS for table_name in section["tables"]
}
SECTION_BY_ID = {str(section["id"]): section for section in SECTION_DEFINITIONS}

CATEGORY_VIEW_ANCHORS: tuple[str, ...] = ("accounts", "books")


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


def _assert_roles_partition(table_set: set[str]) -> None:
    """Fail loudly if the data-role classification is not a clean partition.

    Every table must belong to exactly one role. A new table added without a
    role assignment (or a table double-classified, or a role naming a table the
    schema no longer has) trips this — the role row is only trustworthy as a
    "how is each table used?" audit if it stays exhaustive and disjoint.
    """
    assigned: list[str] = [name for role in ROLE_DEFINITIONS for name in role["tables"]]
    assigned_set = set(assigned)
    duplicates = sorted({name for name in assigned if assigned.count(name) > 1})
    unclassified = sorted(table_set - assigned_set)
    unknown = sorted(assigned_set - table_set)
    if duplicates or unclassified or unknown:
        raise ValueError(
            "Data-role classification is not a clean partition of the schema: "
            f"unclassified tables={unclassified}, tables in multiple roles={duplicates}, "
            f"roles naming unknown tables={unknown}."
        )


def build_diagram_payload(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return the schema payload consumed by the HTML diagram viewer.

    Uses the project-agnostic introspection from ``scripts.database_diagrams``
    and decorates the neutral payload with this repo's section and view metadata.
    """
    # Code-defined application schema only — Alembic's bookkeeping table is not
    # part of it (build_html drops it upstream; this guard keeps direct callers,
    # e.g. tests, from feeding it in and tripping the role partition check).
    names = [name for name in table_names(conn) if name != "alembic_version"]
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
    role_views: list[dict[str, object]] = []
    for role in ROLE_DEFINITIONS:
        role_views.append(
            {
                "id": role["id"],
                "label": role["label"],
                "description": role["description"],
                "tables": [name for name in role["tables"] if name in table_set],
            }
        )
    _assert_roles_partition(table_set)
    category_views: list[dict[str, object]] = []
    for section in SECTION_DEFINITIONS:
        if section["id"] == "accounts":
            continue
        category_tables = dict.fromkeys((*CATEGORY_VIEW_ANCHORS, *section["tables"]))
        category_views.append(
            {
                "id": f"category_{section['id']}",
                "label": section["label"],
                "description": f"{section['label']} tables with the accounts and books anchors.",
                "tables": [name for name in category_tables if name in table_set],
            }
        )
    return {
        "title": "Trading Strategies Database Diagram Viewer",
        "source": "fresh code schema",
        "generatedAt": datetime.now(PST).strftime("%H:%M %d-%m-%Y %Z"),
        "sections": SECTION_DEFINITIONS,
        "tables": tables,
        "views": views,
        "categoryViews": category_views,
        "roleViews": role_views,
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
