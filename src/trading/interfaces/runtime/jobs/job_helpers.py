from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

from common.files import sorted_by_mtime_desc
from trading.interfaces.runtime.notifications import EmailNotificationConfig

RUNTIME_ALERT_WEBHOOK_ENV = "TRADING_RUNTIME_ALERT_WEBHOOK_URL"

# SMTP email-alert config: env-sourced, mirroring the webhook. Email
# stays fully opt-in — nothing is sent unless host, sender, and a recipient are set.
RUNTIME_ALERT_SMTP_HOST_ENV = "TRADING_RUNTIME_ALERT_SMTP_HOST"
RUNTIME_ALERT_SMTP_PORT_ENV = "TRADING_RUNTIME_ALERT_SMTP_PORT"
RUNTIME_ALERT_SMTP_USERNAME_ENV = "TRADING_RUNTIME_ALERT_SMTP_USERNAME"
RUNTIME_ALERT_SMTP_PASSWORD_ENV = "TRADING_RUNTIME_ALERT_SMTP_PASSWORD"
RUNTIME_ALERT_SMTP_FROM_ENV = "TRADING_RUNTIME_ALERT_SMTP_FROM"
RUNTIME_ALERT_SMTP_TO_ENV = "TRADING_RUNTIME_ALERT_SMTP_TO"
RUNTIME_ALERT_SMTP_USE_TLS_ENV = "TRADING_RUNTIME_ALERT_SMTP_USE_TLS"

# Default SMTP submission port (STARTTLS).
DEFAULT_SMTP_PORT = 587

# Explicit falsey spellings that disable STARTTLS; any other value (or unset) keeps it on.
_SMTP_TLS_DISABLED_VALUES = {"0", "false", "no", "off"}

# Subprocess module path constants — update here if a module is ever relocated.
CLI_MAIN_MODULE = "trading.interfaces.cli.main"
ADMIN_MODULE = "trading.interfaces.runtime.data_ops.admin"
RUN_AUTO_TRADES_MODULE = "trading.interfaces.runtime.jobs.daily.paper_trading.run_auto_trades"
RECONCILE_ORDERS_MODULE = "trading.interfaces.runtime.jobs.daily.paper_trading.reconcile_orders"
DAILY_CHALLENGER_SHADOW_EVAL_MODULE = "trading.interfaces.runtime.jobs.daily.challenger_shadow_eval"


def logs_dir_for_repo(repo_root: Path) -> Path:
    return repo_root / "local" / "logs"


def ts() -> str:
    """Return a human-readable local-timezone ISO timestamp for log lines."""
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat()


def is_env_truthy(env_var: str) -> bool:
    """Return True if the named environment variable is set to a truthy value."""
    return os.getenv(env_var, "").strip().lower() in {"1", "true", "yes", "on"}


def resolve_email_config_from_env() -> EmailNotificationConfig | None:
    """Build the runtime email-alert config from environment, or None if not configured.

    Returns None unless host, sender, and at least one recipient are all set, so email
    stays fully opt-in (like the webhook). Username/password are optional (unauthenticated
    relays are supported); STARTTLS is on unless explicitly disabled.
    """
    host = os.getenv(RUNTIME_ALERT_SMTP_HOST_ENV, "").strip()
    sender = os.getenv(RUNTIME_ALERT_SMTP_FROM_ENV, "").strip()
    recipients = tuple(item.strip() for item in os.getenv(RUNTIME_ALERT_SMTP_TO_ENV, "").split(",") if item.strip())
    if not host or not sender or not recipients:
        return None

    port_raw = os.getenv(RUNTIME_ALERT_SMTP_PORT_ENV, "").strip()
    try:
        port = int(port_raw) if port_raw else DEFAULT_SMTP_PORT
    except ValueError:
        port = DEFAULT_SMTP_PORT

    username = os.getenv(RUNTIME_ALERT_SMTP_USERNAME_ENV, "").strip() or None
    password = os.getenv(RUNTIME_ALERT_SMTP_PASSWORD_ENV) or None
    use_tls = os.getenv(RUNTIME_ALERT_SMTP_USE_TLS_ENV, "").strip().lower() not in _SMTP_TLS_DISABLED_VALUES

    return EmailNotificationConfig(
        host=host,
        port=port,
        sender=sender,
        recipients=recipients,
        username=username,
        password=password,
        use_tls=use_tls,
    )


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
