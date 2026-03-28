from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..config import LOGS_DIR

router = APIRouter()


@router.get("/api/logs/files")
def api_log_files() -> dict[str, list[str]]:
    if not LOGS_DIR.exists():
        return {"files": []}
    files = sorted([path.name for path in LOGS_DIR.glob("*.log")], reverse=True)
    return {"files": files}


@router.get("/api/logs/{file_name}")
def api_log_file(
    file_name: str,
    limit: int = Query(default=400, ge=10, le=4000),
    contains: str | None = Query(default=None),
) -> dict[str, object]:
    path = (LOGS_DIR / file_name).resolve()
    if not str(path).startswith(str(LOGS_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid log path")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Log file not found")

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if contains:
        needle = contains.lower().strip()
        lines = [line for line in lines if needle in line.lower()]

    sliced = lines[-limit:]
    return {
        "file": file_name,
        "lineCount": len(lines),
        "returned": len(sliced),
        "lines": sliced,
    }
