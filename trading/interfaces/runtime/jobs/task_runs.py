from __future__ import annotations

import datetime as dt
import subprocess
import sys
from pathlib import Path

RUNTIME_ALERT_WEBHOOK_ENV = "TRADING_RUNTIME_ALERT_WEBHOOK_URL"


def logs_dir_for_repo(repo_root: Path) -> Path:
    return repo_root / "local" / "logs"


def tee_line(log_path: Path, text: str) -> None:
    print(text)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")


def latest_log_contains_sentinel(log_dir: Path, pattern: str, sentinel: str) -> bool:
    logs = sorted(log_dir.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    if not logs:
        return False

    latest = logs[0]
    try:
        return sentinel in latest.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def _ts() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat()


def run_command(log_path: Path, label: str, args: list[str], cwd: Path) -> tuple[int, str]:
    tee_line(log_path, f"[{_ts()}] START: {label}")
    process = subprocess.Popen(
        [sys.executable, *args],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    assert process.stdout is not None
    lines: list[str] = []
    for line in process.stdout:
        clean = line.rstrip("\n")
        lines.append(clean)
        tee_line(log_path, clean)
    exit_code = process.wait()
    combined_output = "\n".join(lines)
    if exit_code == 0:
        tee_line(log_path, f"[{_ts()}] DONE: {label}")
    else:
        tee_line(log_path, f"[{_ts()}] ERROR: {label} exit={exit_code}")
    return exit_code, combined_output


def stream_command(log_path: Path, label: str, args: list[str], cwd: Path) -> None:
    exit_code, _ = run_command(log_path, label, args, cwd)
    if exit_code != 0:
        raise RuntimeError(f"Step failed: {label} (exit={exit_code})")
