from __future__ import annotations

from typing import Any

from common.paths import DB_BACKUPS_DIR, SCHEDULE_STATUS_ARTIFACT_PATH
from common.runtime_job_status import (
    DAILY_PAPER_TRADING_COMPLETE_SENTINEL as DAILY_PAPER_TRADING_SENTINEL,
    WEEKLY_DB_BACKUP_COMPLETE_SENTINEL as WEEKLY_DB_BACKUP_SENTINEL,
)
from trading.services.operations.job_status import JobStatus, evaluate_all_jobs
from trading.services.operations.schedule_status import fetch_schedule_status

from ...config import LOGS_DIR
from ._artifacts import list_artifacts
from ._shared import file_ref

# Module-level so tests can point it at a temp artifact.
SCHEDULE_STATUS_PATH = SCHEDULE_STATUS_ARTIFACT_PATH

__all__ = [
    "DAILY_PAPER_TRADING_SENTINEL",
    "WEEKLY_DB_BACKUP_SENTINEL",
    "list_operations_overview",
]


def _job_status_payload(status: JobStatus) -> dict[str, object]:
    """Shape one monitored-job status for the frontend (camelCase, file refs)."""
    return {
        "key": status.job.key,
        "label": status.job.label,
        "cadence": status.job.cadence,
        "windowLabel": status.window_label,
        "status": status.status,
        "currentRunPresent": status.current_run_present,
        "currentRunComplete": status.current_run_complete,
        "currentLog": file_ref(status.current_log),
        "lastSuccess": file_ref(status.last_success_log),
        "runHint": status.job.run_hint,
    }


def _schedule_status_payload(raw: dict[str, Any] | None) -> dict[str, object] | None:
    """Map the snake_case drift artifact to the camelCase the frontend expects."""
    if raw is None:
        return None
    jobs = raw.get("jobs", [])
    return {
        "generatedAt": raw.get("generated_at"),
        "host": raw.get("host"),
        "scheduler": raw.get("scheduler"),
        "inSync": bool(raw.get("in_sync")),
        "installedReadable": bool(raw.get("installed_readable")),
        "jobs": [
            {
                "taskName": job.get("task_name"),
                "desired": job.get("desired"),
                "registered": job.get("registered"),
                "state": job.get("state"),
            }
            for job in jobs
            if isinstance(job, dict)
        ],
    }


def list_operations_overview() -> dict[str, object]:
    """Every monitored job's status, schedule drift, and the database-backup artifacts.

    Job list and status come from trading.services.operations, so the web panel
    and check_jobs report the same jobs and can't drift.
    """
    return {
        "jobs": [_job_status_payload(status) for status in evaluate_all_jobs(logs_dir=LOGS_DIR)],
        "scheduleStatus": _schedule_status_payload(fetch_schedule_status(SCHEDULE_STATUS_PATH)),
        "databaseBackups": list_artifacts(
            DB_BACKUPS_DIR,
            suffixes=(".db", ".sqlite", ".sqlite3"),
        ),
    }
