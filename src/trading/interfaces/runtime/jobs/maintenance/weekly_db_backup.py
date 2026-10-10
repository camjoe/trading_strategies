#!/usr/bin/env python3
"""Run a weekly DB backup with logging + duplicate-week guard."""

from __future__ import annotations

import argparse

from common.runtime_job_status import WEEKLY_DB_BACKUP_COMPLETE_SENTINEL
from trading.interfaces.runtime.jobs.job_helpers import ADMIN_MODULE, run_command
from trading.interfaces.runtime.jobs.job_runner import JobContext, maintenance_job

JOB_NAME = "weekly_db_backup"
COMPLETE_SENTINEL = WEEKLY_DB_BACKUP_COMPLETE_SENTINEL


def _add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--backup-dir",
        default="",
        help="Optional backup destination directory or .db file path",
    )


@maintenance_job(
    job_name=JOB_NAME,
    sentinel=COMPLETE_SENTINEL,
    period="week",
    description="Run weekly database backup.",
    add_arguments=_add_arguments,
)
def main(ctx: JobContext) -> int:
    cmd = ["-m", ADMIN_MODULE, "backup-db"]
    if ctx.args.backup_dir:
        cmd.append(ctx.args.backup_dir)
    exit_code, _ = run_command(ctx.log_path, "Database backup", cmd, ctx.repo_root)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
