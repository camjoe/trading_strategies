from __future__ import annotations

from pathlib import Path

from ._shared import file_ref, sorted_files


def log_has_sentinel(path: Path, sentinel: str) -> bool:
    try:
        return sentinel in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def build_job_status(
    *,
    logs_dir: Path,
    key: str,
    label: str,
    cadence: str,
    pattern: str,
    current_tag: str,
    window_label: str,
    sentinel: str,
    run_hint: str,
) -> dict[str, object]:
    logs = sorted_files([path for path in logs_dir.glob(pattern) if path.is_file()])
    current_log = next((log for log in logs if current_tag in log.name), None)
    current_complete = current_log is not None and log_has_sentinel(current_log, sentinel)
    last_success = next((log for log in logs if log_has_sentinel(log, sentinel)), None)
    status = "ok" if current_complete else "warning" if current_log is not None else "missing"
    return {
        "key": key,
        "label": label,
        "cadence": cadence,
        "windowLabel": window_label,
        "status": status,
        "currentRunPresent": current_log is not None,
        "currentRunComplete": current_complete,
        "currentLog": file_ref(current_log),
        "lastSuccess": file_ref(last_success),
        "runHint": run_hint,
    }
