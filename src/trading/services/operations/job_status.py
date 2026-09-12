"""Single source of truth for which runtime jobs are monitored, and their status.

Both the web Admin "Jobs & health" panel and ``scripts/check_jobs.py`` read
``evaluate_all_jobs`` here, so a job added to ``MONITORED_JOBS`` shows up in both
without either re-listing jobs. This sits in the services layer because the web
backend may import services but not ``trading.interfaces`` (enforced by
``layer_check``).

"Did it run this period" is answered by the per-run log files the jobs already
write: the current-period tag must appear in a matching file name, and the
completion sentinel must appear in that file. The tag spellings mirror
``job_helpers.day_tag`` / ``week_tag`` / ``month_tag``, which name those files;
``test_job_status`` guards the two against drift.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from common.files import sorted_by_mtime_desc
from common.runtime_job_status import (
    DAILY_CHALLENGER_SHADOW_EVAL_COMPLETE_SENTINEL,
    DAILY_PAPER_TRADING_COMPLETE_SENTINEL,
    MONTHLY_GOVERNANCE_M1_RISK_REBASELINE_COMPLETE_SENTINEL,
    MONTHLY_GOVERNANCE_M2_PARAMETER_GOVERNANCE_COMPLETE_SENTINEL,
    MONTHLY_GOVERNANCE_M3_PERFORMANCE_AUDIT_COMPLETE_SENTINEL,
    WEEKLY_DB_BACKUP_COMPLETE_SENTINEL,
    WEEKLY_GOVERNANCE_W1_LEADERBOARD_COMPLETE_SENTINEL,
    WEEKLY_GOVERNANCE_W2_PROMOTION_REVIEW_COMPLETE_SENTINEL,
    WEEKLY_GOVERNANCE_W3_ALLOCATION_REVIEW_COMPLETE_SENTINEL,
)

Cadence = Literal["daily", "weekly", "monthly"]
JobHealth = Literal["ok", "warning", "missing"]


@dataclass(frozen=True)
class MonitoredJob:
    """A scheduled job whose completion the operator watches."""

    key: str
    label: str
    cadence: Cadence
    log_pattern: str
    sentinel: str
    module: str
    args: tuple[str, ...] = ()

    @property
    def run_hint(self) -> str:
        """Copy-paste command a reader can run to fire the job by hand."""
        suffix = f" {' '.join(self.args)}" if self.args else ""
        return f"python -m {self.module}{suffix}"


@dataclass(frozen=True)
class JobStatus:
    """One job's monitored status for the current period."""

    job: MonitoredJob
    window_label: str
    status: JobHealth
    current_run_present: bool
    current_run_complete: bool
    current_log: Path | None
    last_success_log: Path | None


_DAILY: Cadence = "daily"
_WEEKLY: Cadence = "weekly"
_MONTHLY: Cadence = "monthly"

MONITORED_JOBS: tuple[MonitoredJob, ...] = (
    MonitoredJob(
        key="daily_paper_trading",
        label="Daily Paper Trading",
        cadence=_DAILY,
        # Digit-guarded so the daily_paper_trading_startup_<date>.log is not matched.
        log_pattern="daily_paper_trading_[0-9]*_[0-9]*.log",
        sentinel=DAILY_PAPER_TRADING_COMPLETE_SENTINEL,
        module="trading.interfaces.runtime.jobs.daily.paper_trading",
        args=("--run-source", "manual"),
    ),
    MonitoredJob(
        key="daily_challenger_shadow_eval",
        label="Daily Challenger Shadow Eval",
        cadence=_DAILY,
        log_pattern="daily_challenger_shadow_eval_*.log",
        sentinel=DAILY_CHALLENGER_SHADOW_EVAL_COMPLETE_SENTINEL,
        module="trading.interfaces.runtime.jobs.daily.challenger_shadow_eval",
        args=("--enable-run",),
    ),
    MonitoredJob(
        key="weekly_db_backup",
        label="Weekly DB Backup",
        cadence=_WEEKLY,
        log_pattern="weekly_db_backup_*.log",
        sentinel=WEEKLY_DB_BACKUP_COMPLETE_SENTINEL,
        module="trading.interfaces.runtime.jobs.maintenance.weekly_db_backup",
    ),
    MonitoredJob(
        key="weekly_governance_w1_leaderboard",
        label="Weekly W1 Leaderboard",
        cadence=_WEEKLY,
        log_pattern="weekly_governance_w1_leaderboard_*.log",
        sentinel=WEEKLY_GOVERNANCE_W1_LEADERBOARD_COMPLETE_SENTINEL,
        module="trading.interfaces.runtime.jobs.governance.weekly.w1_leaderboard",
    ),
    MonitoredJob(
        key="weekly_governance_w2_promotion_review",
        label="Weekly W2 Promotion Review",
        cadence=_WEEKLY,
        log_pattern="weekly_governance_w2_promotion_review_*.log",
        sentinel=WEEKLY_GOVERNANCE_W2_PROMOTION_REVIEW_COMPLETE_SENTINEL,
        module="trading.interfaces.runtime.jobs.governance.weekly.w2_promotion_review",
    ),
    MonitoredJob(
        key="weekly_governance_w3_allocation_review",
        label="Weekly W3 Allocation Review",
        cadence=_WEEKLY,
        log_pattern="weekly_governance_w3_allocation_review_*.log",
        sentinel=WEEKLY_GOVERNANCE_W3_ALLOCATION_REVIEW_COMPLETE_SENTINEL,
        module="trading.interfaces.runtime.jobs.governance.weekly.w3_allocation_review",
    ),
    MonitoredJob(
        key="monthly_governance_m1_risk_rebaseline",
        label="Monthly M1 Risk Rebaseline",
        cadence=_MONTHLY,
        log_pattern="monthly_governance_m1_risk_rebaseline_*.log",
        sentinel=MONTHLY_GOVERNANCE_M1_RISK_REBASELINE_COMPLETE_SENTINEL,
        module="trading.interfaces.runtime.jobs.governance.monthly.m1_risk_rebaseline",
    ),
    MonitoredJob(
        key="monthly_governance_m2_parameter_governance",
        label="Monthly M2 Parameter Governance",
        cadence=_MONTHLY,
        log_pattern="monthly_governance_m2_parameter_governance_*.log",
        sentinel=MONTHLY_GOVERNANCE_M2_PARAMETER_GOVERNANCE_COMPLETE_SENTINEL,
        module="trading.interfaces.runtime.jobs.governance.monthly.m2_parameter_governance",
    ),
    MonitoredJob(
        key="monthly_governance_m3_performance_audit",
        label="Monthly M3 Performance Audit",
        cadence=_MONTHLY,
        log_pattern="monthly_governance_m3_performance_audit_*.log",
        sentinel=MONTHLY_GOVERNANCE_M3_PERFORMANCE_AUDIT_COMPLETE_SENTINEL,
        module="trading.interfaces.runtime.jobs.governance.monthly.m3_performance_audit",
    ),
)


def period_tag(cadence: Cadence, now: dt.datetime) -> str:
    """Return the tag that names *now*'s period in a run's log file name."""
    if cadence == _WEEKLY:
        iso = now.isocalendar()
        return f"{iso.year}_W{iso.week:02d}"
    if cadence == _MONTHLY:
        return now.strftime("%Y_%m")
    return now.strftime("%Y%m%d")


def _log_has_sentinel(path: Path, sentinel: str) -> bool:
    try:
        return sentinel in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def evaluate_job(job: MonitoredJob, *, logs_dir: Path, now: dt.datetime) -> JobStatus:
    logs = sorted_by_mtime_desc([path for path in logs_dir.glob(job.log_pattern) if path.is_file()])
    tag = period_tag(job.cadence, now)
    current_log = next((log for log in logs if tag in log.name), None)
    current_complete = current_log is not None and _log_has_sentinel(current_log, job.sentinel)
    last_success = next((log for log in logs if _log_has_sentinel(log, job.sentinel)), None)
    status: JobHealth = "ok" if current_complete else "warning" if current_log is not None else "missing"
    return JobStatus(
        job=job,
        window_label=tag,
        status=status,
        current_run_present=current_log is not None,
        current_run_complete=current_complete,
        current_log=current_log,
        last_success_log=last_success,
    )


def evaluate_all_jobs(*, logs_dir: Path, now: dt.datetime | None = None) -> list[JobStatus]:
    resolved_now = now or dt.datetime.now()
    return [evaluate_job(job, logs_dir=logs_dir, now=resolved_now) for job in MONITORED_JOBS]
