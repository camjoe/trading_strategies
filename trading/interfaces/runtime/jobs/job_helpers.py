from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

RUNTIME_ALERT_WEBHOOK_ENV = "TRADING_RUNTIME_ALERT_WEBHOOK_URL"

# Subprocess module path constants — update here if a module is ever relocated.
CLI_MAIN_MODULE = "trading.interfaces.cli.main"
ADMIN_MODULE = "trading.interfaces.runtime.data_ops.admin"
RUN_AUTO_TRADES_MODULE = "trading.interfaces.runtime.jobs.run_auto_trades"

# Transient connectivity/rate-limit strings that indicate a retry may succeed.
TRANSIENT_ERROR_TOKENS = (
    "temporarily unavailable",
    "timed out",
    "timeout",
    "connection reset",
    "connection aborted",
    "connection error",
    "temporary failure",
    "try again",
    "rate limit",
    "too many requests",
)


def logs_dir_for_repo(repo_root: Path) -> Path:
    return repo_root / "local" / "logs"


def ts() -> str:
    """Return a human-readable local-timezone ISO timestamp for log lines."""
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat()


def is_env_truthy(env_var: str) -> bool:
    """Return True if the named environment variable is set to a truthy value."""
    return os.getenv(env_var, "").strip().lower() in {"1", "true", "yes", "on"}


def day_tag(now: dt.datetime | None = None) -> str:
    """Return YYYYMMDD tag for *now* (defaults to current local time)."""
    return (now or dt.datetime.now()).strftime("%Y%m%d")


def is_transient_error(output: str) -> bool:
    """Return True if *output* contains a known transient connectivity error token."""
    lowered = output.lower()
    return any(token in lowered for token in TRANSIENT_ERROR_TOKENS)


def retry_delay_seconds(base_delay_seconds: float, attempt_number: int) -> float:
    """Exponential back-off: base * 2^(attempt-1), clamped to >= 0."""
    return max(base_delay_seconds, 0.0) * (2 ** (attempt_number - 1))


def resolve_accounts(accounts_arg: str, all_accounts: list[str]) -> list[str]:
    """Resolve 'all' or a comma-separated list against *all_accounts*.

    Raises ValueError for unknown account names.
    """
    if accounts_arg.strip().lower() == "all":
        return all_accounts
    requested = [item.strip() for item in accounts_arg.split(",") if item.strip()]
    known = set(all_accounts)
    missing = [name for name in requested if name not in known]
    if missing:
        raise ValueError(f"Unknown account(s): {', '.join(missing)}")
    return requested


def write_artifact(artifact_path: Path, payload: dict[str, object]) -> None:
    """Write *payload* as pretty-printed JSON to *artifact_path*, creating parent dirs."""
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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


def run_command(log_path: Path, label: str, args: list[str], cwd: Path) -> tuple[int, str]:
    tee_line(log_path, f"[{ts()}] START: {label}")
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
        tee_line(log_path, f"[{ts()}] DONE: {label}")
    else:
        tee_line(log_path, f"[{ts()}] ERROR: {label} exit={exit_code}")
    return exit_code, combined_output


def stream_command(log_path: Path, label: str, args: list[str], cwd: Path) -> None:
    exit_code, _ = run_command(log_path, label, args, cwd)
    if exit_code != 0:
        raise RuntimeError(f"Step failed: {label} (exit={exit_code})")
