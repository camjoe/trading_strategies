"""Catalog of schedulable runtime jobs and the declarative schedule loader.

The catalog is the single source of truth for each job's module path, task name,
schedule kind, and log file. The operator's schedule config names a job by its
``id`` and supplies only the time, day, args, and enabled flag; everything else
comes from the catalog here. A wrong module path can therefore not be typed into
the config, only into this one table.

See ``docs/reference/runtime-jobs.md`` for the config format and workflow.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from trading.interfaces.runtime.jobs.job_helpers import (
    DAILY_CHALLENGER_SHADOW_EVAL_MODULE,
    DAILY_PAPER_TRADING_MODULE,
    DAILY_TRADER_HEALTH_CHECK_MODULE,
    WEEKLY_DB_BACKUP_MODULE,
)
from trading.interfaces.runtime.scheduling.scheduler_installer import ScheduledTaskSpec, ScheduleKind


@dataclass(frozen=True)
class JobDefinition:
    """Fixed identity of one schedulable job, independent of when it runs."""

    job_id: str
    task_name: str
    module: str
    schedule_kind: ScheduleKind
    log_name: str


JOB_CATALOG: dict[str, JobDefinition] = {
    "daily_paper_trading": JobDefinition(
        job_id="daily_paper_trading",
        task_name=r"Trading\DailyPaperTrading",
        module=DAILY_PAPER_TRADING_MODULE,
        schedule_kind="weekdays",
        log_name="daily_paper_trading_scheduler.log",
    ),
    "daily_challenger_shadow_eval": JobDefinition(
        job_id="daily_challenger_shadow_eval",
        task_name=r"Trading\DailyChallengerShadowEval",
        module=DAILY_CHALLENGER_SHADOW_EVAL_MODULE,
        schedule_kind="daily",
        log_name="daily_challenger_shadow_eval_scheduler.log",
    ),
    "daily_trader_health": JobDefinition(
        job_id="daily_trader_health",
        task_name=r"Trading\DailyTraderHealthCheck",
        module=DAILY_TRADER_HEALTH_CHECK_MODULE,
        schedule_kind="weekdays",
        log_name="daily_trader_health_check_scheduler.log",
    ),
    "weekly_db_backup": JobDefinition(
        job_id="weekly_db_backup",
        task_name=r"Trading\WeeklyDbBackup",
        module=WEEKLY_DB_BACKUP_MODULE,
        schedule_kind="weekly",
        log_name="weekly_db_backup_scheduler.log",
    ),
}

# Every task name the catalog can install; the reconcile step removes the ones a
# config does not enable, so this must list all of them.
ALL_TASK_NAMES: tuple[str, ...] = tuple(definition.task_name for definition in JOB_CATALOG.values())


@dataclass(frozen=True)
class ScheduleResolution:
    """The two lists an apply needs: what to register and what to remove."""

    to_register: list[ScheduledTaskSpec] = field(default_factory=list)
    to_unregister: list[str] = field(default_factory=list)


def _spec_from_entry(entry: dict[str, object], definition: JobDefinition) -> ScheduledTaskSpec:
    time = entry.get("time")
    if not isinstance(time, str) or not time.strip():
        raise ValueError(f"Job '{definition.job_id}' needs a 'time' string in HH:MM format")

    raw_args = entry.get("args", [])
    if not isinstance(raw_args, list) or any(not isinstance(item, str) for item in raw_args):
        raise ValueError(f"Job '{definition.job_id}' 'args' must be a list of strings")

    day_of_week: str | None = None
    if definition.schedule_kind == "weekly":
        raw_day = entry.get("day_of_week")
        if not isinstance(raw_day, str) or not raw_day.strip():
            raise ValueError(f"Weekly job '{definition.job_id}' needs a 'day_of_week' string")
        day_of_week = raw_day.strip()

    return ScheduledTaskSpec(
        task_name=definition.task_name,
        module=definition.module,
        time=time.strip(),
        schedule_kind=definition.schedule_kind,
        day_of_week=day_of_week,
        args=tuple(raw_args),
        log_name=definition.log_name,
    )


def resolve_schedule_config(config_path: Path) -> ScheduleResolution:
    """Read the schedule config and split it into register and unregister lists.

    A job is registered when it is present and ``enabled`` is not false. Every
    other catalog job is scheduled for removal, so the installed set always
    matches the file after an apply.

    Raises ``FileNotFoundError`` for a missing file and ``ValueError`` for a
    malformed one; the CLI turns both into a non-zero exit.
    """
    if not config_path.exists():
        raise FileNotFoundError(
            f"Schedule config not found: {config_path}. "
            "Copy src/infrastructure/config/job_schedule.example.json to this path and set real times."
        )

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Schedule config must be a JSON object with a 'jobs' array")
    jobs = raw.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("Schedule config must have a 'jobs' array")

    to_register: list[ScheduledTaskSpec] = []
    enabled_ids: set[str] = set()
    for entry in jobs:
        if not isinstance(entry, dict):
            raise ValueError("Each entry in 'jobs' must be an object")
        job_id = entry.get("id")
        if not isinstance(job_id, str) or job_id not in JOB_CATALOG:
            allowed = ", ".join(JOB_CATALOG)
            raise ValueError(f"Unknown job id {job_id!r}. Use one of: {allowed}")
        if job_id in enabled_ids:
            raise ValueError(f"Job '{job_id}' is listed more than once")
        enabled_ids.add(job_id)

        enabled = entry.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError(f"Job '{job_id}' 'enabled' must be true or false")
        if enabled:
            to_register.append(_spec_from_entry(entry, JOB_CATALOG[job_id]))

    registered_names = {spec.task_name for spec in to_register}
    to_unregister = [name for name in ALL_TASK_NAMES if name not in registered_names]
    return ScheduleResolution(to_register=to_register, to_unregister=to_unregister)
