from __future__ import annotations

import csv
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

from trading.database.code.db_backend import SQLiteBackend, get_backend
from trading.database.code.db_config import get_db_path

DEFAULT_EXPORT_TABLES: tuple[str, ...] = (
    "accounts",
    "equity_snapshots",
    "trades",
    "backtest_runs",
    "backtest_trades",
)


@dataclass(frozen=True)
class TableExportResult:
    table: str
    output_path: Path
    row_count: int


@dataclass(frozen=True)
class ExportBatchResult:
    db_path: Path
    output_dir: Path
    started_at_utc: str
    tables: tuple[TableExportResult, ...]


def zip_export_directory(export_dir: Path) -> Path:
    """Create a .zip archive for an export directory and return its path."""
    resolved_dir = export_dir.resolve()
    if not resolved_dir.exists() or not resolved_dir.is_dir():
        raise FileNotFoundError(f"Export directory not found: {resolved_dir}")

    archive_base = resolved_dir.parent / resolved_dir.name
    archive_path = Path(shutil.make_archive(str(archive_base), "zip", root_dir=str(resolved_dir.parent), base_dir=resolved_dir.name))
    return archive_path


def _normalize_table_name(name: str) -> str:
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


def export_table_to_csv(conn: sqlite3.Connection, table: str, output_path: Path) -> TableExportResult:
    normalized_table = _normalize_table_name(table)
    if not _table_exists(conn, normalized_table):
        raise ValueError(f"Table not found: {normalized_table}")

    query = _ordered_select_sql(conn, normalized_table)
    cur = conn.execute(query)

    headers = [str(item[0]) for item in cur.description or []]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    row_count = 0
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if headers:
            writer.writerow(headers)
        for row in cur:
            writer.writerow(list(row))
            row_count += 1

    return TableExportResult(
        table=normalized_table,
        output_path=output_path,
        row_count=row_count,
    )


def export_tables_to_csv(
    *,
    tables: Sequence[str] = DEFAULT_EXPORT_TABLES,
    output_base_dir: Path,
    db_path: Path | None = None,
) -> ExportBatchResult:
    resolved_db_path = (db_path or get_db_path()).resolve()
    if not resolved_db_path.exists():
        raise FileNotFoundError(f"Database file not found: {resolved_db_path}")

    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    export_dir = output_base_dir.resolve() / f"db_csv_{stamp}"
    export_dir.mkdir(parents=True, exist_ok=True)

    if db_path is None:
        conn = get_backend().open_connection()
    else:
        conn = SQLiteBackend(resolved_db_path).open_connection()
    try:
        results: list[TableExportResult] = []
        for table in tables:
            normalized = _normalize_table_name(table)
            result = export_table_to_csv(
                conn,
                normalized,
                export_dir / f"{normalized}.csv",
            )
            results.append(result)
    finally:
        conn.close()

    return ExportBatchResult(
        db_path=resolved_db_path,
        output_dir=export_dir,
        started_at_utc=datetime.utcnow().isoformat(timespec="seconds") + "Z",
        tables=tuple(results),
    )
