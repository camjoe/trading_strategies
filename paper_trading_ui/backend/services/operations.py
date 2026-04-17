from __future__ import annotations

import datetime as dt
from pathlib import Path

from common.project_paths import DB_BACKUPS_DIR
from ..config import EXPORTS_DIR, LOGS_DIR
from trading.services.runtime_job_status import (
    DAILY_BACKTEST_REFRESH_COMPLETE_SENTINEL as DAILY_BACKTEST_REFRESH_SENTINEL,
    DAILY_PAPER_TRADING_COMPLETE_SENTINEL as DAILY_PAPER_TRADING_SENTINEL,
    DAILY_SNAPSHOT_COMPLETE_SENTINEL as DAILY_SNAPSHOT_SENTINEL,
    WEEKLY_DB_BACKUP_COMPLETE_SENTINEL as WEEKLY_DB_BACKUP_SENTINEL,
)

DAILY_PAPER_TRADING_RUN_HINT = (
    "./venv/bin/python -m trading.interfaces.runtime.jobs.daily_paper_trading --run-source manual"
)
DAILY_SNAPSHOT_RUN_HINT = (
    "./venv/bin/python -m trading.interfaces.runtime.jobs.daily_snapshot --enable-run"
)
DAILY_BACKTEST_REFRESH_RUN_HINT = (
    "./venv/bin/python -m trading.interfaces.runtime.jobs.daily_backtest_refresh --accounts all --enable-run"
)
WEEKLY_DB_BACKUP_RUN_HINT = (
    "./venv/bin/python -m trading.interfaces.runtime.jobs.weekly_db_backup"
)


def _log_has_sentinel(path: Path, sentinel: str) -> bool:
    try:
        return sentinel in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def _modified_at(path: Path) -> str:
    return dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc).isoformat(timespec="seconds")


def _sorted_files(paths: list[Path]) -> list[Path]:
    return sorted(paths, key=lambda path: path.stat().st_mtime, reverse=True)


def _file_ref(path: Path | None) -> dict[str, str] | None:
    if path is None:
        return None
    return {
        "name": path.name,
        "modifiedAt": _modified_at(path),
    }


def _build_job_status(
    *,
    key: str,
    label: str,
    cadence: str,
    pattern: str,
    current_tag: str,
    window_label: str,
    sentinel: str,
    run_hint: str,
) -> dict[str, object]:
    logs = _sorted_files([path for path in LOGS_DIR.glob(pattern) if path.is_file()])
    current_log = next((log for log in logs if current_tag in log.name), None)
    current_complete = current_log is not None and _log_has_sentinel(current_log, sentinel)
    last_success = next((log for log in logs if _log_has_sentinel(log, sentinel)), None)
    status = "ok" if current_complete else "warning" if current_log is not None else "missing"
    return {
        "key": key,
        "label": label,
        "cadence": cadence,
        "windowLabel": window_label,
        "status": status,
        "currentRunPresent": current_log is not None,
        "currentRunComplete": current_complete,
        "currentLog": _file_ref(current_log),
        "lastSuccess": _file_ref(last_success),
        "runHint": run_hint,
    }


def _list_artifacts(directory: Path, *, limit: int = 6, suffixes: tuple[str, ...] | None = None) -> list[dict[str, object]]:
    if not directory.exists():
        return []
    files = [path for path in directory.iterdir() if path.is_file()]
    if suffixes is not None:
        files = [path for path in files if path.suffix.lower() in suffixes]
    artifacts = _sorted_files(files)[:limit]
    return [
        {
            "name": artifact.name,
            "modifiedAt": _modified_at(artifact),
            "sizeBytes": int(artifact.stat().st_size),
        }
        for artifact in artifacts
    ]


def list_operations_overview() -> dict[str, object]:
    today = dt.date.today()
    week_tag = f"{today.isocalendar().year}_W{today.isocalendar().week:02d}"
    today_tag = today.strftime("%Y%m%d")
    return {
        "jobs": [
            _build_job_status(
                key="daily_paper_trading",
                label="Daily Paper Trading",
                cadence="daily",
                pattern="daily_paper_trading_[0-9]*_[0-9]*.log",
                current_tag=today_tag,
                window_label=today.isoformat(),
                sentinel=DAILY_PAPER_TRADING_SENTINEL,
                run_hint=DAILY_PAPER_TRADING_RUN_HINT,
            ),
            _build_job_status(
                key="daily_snapshot",
                label="Daily Snapshot",
                cadence="daily",
                pattern="daily_snapshot_*.log",
                current_tag=today_tag,
                window_label=today.isoformat(),
                sentinel=DAILY_SNAPSHOT_SENTINEL,
                run_hint=DAILY_SNAPSHOT_RUN_HINT,
            ),
            _build_job_status(
                key="daily_backtest_refresh",
                label="Daily Backtest Refresh",
                cadence="daily",
                pattern="daily_backtest_refresh_*.log",
                current_tag=today_tag,
                window_label=today.isoformat(),
                sentinel=DAILY_BACKTEST_REFRESH_SENTINEL,
                run_hint=DAILY_BACKTEST_REFRESH_RUN_HINT,
            ),
            _build_job_status(
                key="weekly_db_backup",
                label="Weekly DB Backup",
                cadence="weekly",
                pattern="weekly_db_backup_*.log",
                current_tag=week_tag,
                window_label=week_tag,
                sentinel=WEEKLY_DB_BACKUP_SENTINEL,
                run_hint=WEEKLY_DB_BACKUP_RUN_HINT,
            ),
        ],
        "dailyBacktestRefreshArtifacts": _list_artifacts(
            EXPORTS_DIR / "daily_backtest_refresh",
            suffixes=(".json",),
        ),
        "dailySnapshotArtifacts": _list_artifacts(
            EXPORTS_DIR / "daily_snapshots",
            suffixes=(".json",),
        ),
        "databaseBackups": _list_artifacts(
            DB_BACKUPS_DIR,
            suffixes=(".db", ".sqlite", ".sqlite3"),
        ),
    }
