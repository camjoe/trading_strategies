"""Read the schedule-drift artifact written by manage_job_schedules.

The web Admin panel imports this (services layer) because it may not import the
scheduling code in trading.interfaces that queries the OS scheduler. The artifact
is refreshed whenever the operator applies a schedule or runs ``--status``; this
reader returns ``None`` until then, which the web shows as "not available".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from common.paths import SCHEDULE_STATUS_ARTIFACT_PATH


def fetch_schedule_status(artifact_path: Path = SCHEDULE_STATUS_ARTIFACT_PATH) -> dict[str, Any] | None:
    """Return the last-written schedule drift status, or None if never written."""
    if not artifact_path.exists():
        return None
    try:
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
