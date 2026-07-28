from __future__ import annotations

import datetime as dt

from common.paths.project_paths import DB_BACKUPS_DIR
from common.runtime_job_status import (
    DAILY_PAPER_TRADING_COMPLETE_SENTINEL as DAILY_PAPER_TRADING_SENTINEL,
    WEEKLY_DB_BACKUP_COMPLETE_SENTINEL as WEEKLY_DB_BACKUP_SENTINEL,
)

from ...config import LOGS_DIR
from ._artifacts import list_artifacts
from ._jobs import build_job_status

DAILY_PAPER_TRADING_RUN_HINT = "python -m trading.interfaces.runtime.jobs.daily.paper_trading --run-source manual"

WEEKLY_DB_BACKUP_RUN_HINT = "python -m trading.interfaces.runtime.jobs.maintenance.weekly_db_backup"


def list_operations_overview() -> dict[str, object]:
    today = dt.date.today()
    week_tag = f"{today.isocalendar().year}_W{today.isocalendar().week:02d}"
    today_tag = today.strftime("%Y%m%d")
    return {
        "jobs": [
            build_job_status(
                logs_dir=LOGS_DIR,
                key="daily_paper_trading",
                label="Daily Paper Trading",
                cadence="daily",
                pattern="daily_paper_trading_[0-9]*_[0-9]*.log",
                current_tag=today_tag,
                window_label=today.isoformat(),
                sentinel=DAILY_PAPER_TRADING_SENTINEL,
                run_hint=DAILY_PAPER_TRADING_RUN_HINT,
            ),
            build_job_status(
                logs_dir=LOGS_DIR,
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
        "databaseBackups": list_artifacts(
            DB_BACKUPS_DIR,
            suffixes=(".db", ".sqlite", ".sqlite3"),
        ),
    }
