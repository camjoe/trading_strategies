from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from common.files import sorted_by_mtime_desc

RUNTIME_ALERT_WEBHOOK_ENV = "TRADING_RUNTIME_ALERT_WEBHOOK_URL"

# Subprocess module path constants — update here if a module is ever relocated.
CLI_MAIN_MODULE = "trading.interfaces.cli.main"
ADMIN_MODULE = "trading.interfaces.runtime.data_ops.admin"
RUN_AUTO_TRADES_MODULE = "trading.interfaces.runtime.jobs.run_auto_trades"
DAILY_CHALLENGER_SHADOW_EVAL_MODULE = "trading.interfaces.runtime.jobs.daily.challenger_shadow_eval"

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


def week_tag(now: dt.datetime) -> str:
    """Return ISO week tag (YYYY_Www) for a timestamp."""
    iso_year, iso_week, _ = now.isocalendar()
    return f"{iso_year}_W{iso_week:02d}"


def month_tag(now: dt.datetime) -> str:
    """Return month tag (YYYY_MM) for a timestamp."""
    return now.strftime("%Y_%m")


def already_completed_for_period(
    *,
    log_dir: Path,
    job_name: str,
    period_tag: str,
    sentinel: str,
) -> bool:
    """Return True when any log for job+period contains completion sentinel."""
    for log_path in log_dir.glob(f"{job_name}_{period_tag}_*.log"):
        try:
            if sentinel in log_path.read_text(encoding="utf-8", errors="replace"):
                return True
        except OSError:
            continue
    return False


def skip_if_already_completed_for_period(
    *,
    log_path: Path,
    log_dir: Path,
    job_name: str,
    period_name: str,
    period_tag: str,
    sentinel: str,
    force_run: bool,
) -> bool:
    """Log and print a standardized skip message for duplicate periodic runs."""
    if force_run:
        return False
    if not already_completed_for_period(
        log_dir=log_dir,
        job_name=job_name,
        period_tag=period_tag,
        sentinel=sentinel,
    ):
        return False
    message = f"{job_name}: already completed this {period_name}; skipping. Use --force-run to override."
    tee_line(log_path, f"[{ts()}] SKIP: {message}")
    print(message)
    return True


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
    logs = sorted_by_mtime_desc(log_dir.glob(pattern))
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


@dataclass(frozen=True)
class AttemptOutcome:
    """Classification of a single command attempt for `run_command_with_retry`.

    *succeeded* marks a successful attempt; *retryable* is consulted only on
    failure (a non-retryable failure stops immediately); *extras* are merged into
    the result payload (e.g. a parsed ``run_id`` or an ``error`` marker).
    """

    succeeded: bool
    retryable: bool
    extras: dict[str, object]


def run_command_with_retry(
    *,
    log_path: Path,
    repo_root: Path,
    account: str,
    command: list[str],
    label_prefix: str,
    max_attempts: int,
    base_backoff_seconds: float,
    classify: Callable[[int, str], AttemptOutcome],
    result_defaults: dict[str, object] | None = None,
    run_command_fn: Callable[[Path, str, list[str], Path], tuple[int, str]] = run_command,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    """Run *command* up to *max_attempts* times, retrying on transient failures.

    The shared retry engine for account-scoped daily jobs. *classify* inspects
    each attempt's ``(exit_code, output)`` and decides success/retryability plus
    any payload extras; transient-error detection, exponential backoff, the RETRY
    log line, and attempt bookkeeping live here. Returns a result dict carrying
    ``account``/``status``/``attempts`` plus *result_defaults* and classify extras.
    """
    base_extras = dict(result_defaults or {})
    attempts = max(1, max_attempts)
    started_at = ts()

    def _result(
        *,
        status: str,
        attempt: int,
        exit_code: int,
        extras: dict[str, object],
        transient: bool | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "account": account,
            "status": status,
            "attempts": attempt,
            **base_extras,
            "started_at": started_at,
            "finished_at": ts(),
            "last_exit_code": exit_code,
        }
        if transient is not None:
            payload["transient"] = transient
        payload.update(extras)
        return payload

    for attempt in range(1, attempts + 1):
        label = f"{label_prefix} {account} (attempt {attempt}/{attempts})"
        exit_code, output = run_command_fn(log_path, label, command, repo_root)
        outcome = classify(exit_code, output)
        if outcome.succeeded:
            return _result(status="success", attempt=attempt, exit_code=exit_code, extras=outcome.extras)

        transient = is_transient_error(output)
        if not outcome.retryable or attempt >= attempts or not transient:
            return _result(
                status="failed",
                attempt=attempt,
                exit_code=exit_code,
                extras=outcome.extras,
                transient=transient,
            )

        delay_seconds = retry_delay_seconds(base_backoff_seconds, attempt)
        tee_line(
            log_path,
            f"[{ts()}] RETRY: account={account} attempt={attempt} delay_seconds={delay_seconds:.2f}",
        )
        sleep_fn(delay_seconds)

    return _result(status="failed", attempt=attempts, exit_code=1, extras={}, transient=False)
