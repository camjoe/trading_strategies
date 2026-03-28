from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from ..config import EXPORTS_DIR


def resolve_csv_export_file(export_name: str, file_name: str) -> Path:
    base = EXPORTS_DIR.resolve()
    candidate = (base / export_name / file_name).resolve()

    if os.path.commonpath([str(base), str(candidate)]) != str(base):
        raise HTTPException(status_code=400, detail="Invalid export path")
    if candidate.suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    return candidate


def list_csv_exports() -> dict[str, object]:
    if not EXPORTS_DIR.exists():
        return {"exports": []}

    export_dirs = sorted(
        [path for path in EXPORTS_DIR.iterdir() if path.is_dir() and path.name.startswith("db_csv_")],
        key=lambda path: path.name,
        reverse=True,
    )

    exports: list[dict[str, object]] = []
    for export_dir in export_dirs:
        csv_files = sorted(export_dir.glob("*.csv"), key=lambda path: path.name)
        files = [{"name": csv_file.name, "sizeBytes": int(csv_file.stat().st_size)} for csv_file in csv_files]
        exports.append(
            {
                "name": export_dir.name,
                "modifiedAt": datetime.fromtimestamp(export_dir.stat().st_mtime).isoformat(timespec="seconds"),
                "files": files,
            }
        )

    return {"exports": exports}


def preview_csv_export(export_name: str, file_name: str, limit: int) -> dict[str, object]:
    path = resolve_csv_export_file(export_name, file_name)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="CSV file not found")

    with path.open("r", encoding="utf-8", errors="replace", newline="") as file_handle:
        reader = csv.reader(file_handle)
        header = next(reader, [])
        rows: list[list[str]] = []
        for _ in range(limit):
            try:
                rows.append([str(cell) for cell in next(reader)])
            except StopIteration:
                break

        truncated = False
        try:
            next(reader)
            truncated = True
        except StopIteration:
            truncated = False

    return {
        "exportName": export_name,
        "fileName": file_name,
        "header": [str(col) for col in header],
        "rows": rows,
        "returned": len(rows),
        "truncated": truncated,
    }
