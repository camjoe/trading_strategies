"""Shared lifecycle wrapper for account-scoped governance jobs.

Implements the sanctioned cross-cutting pattern from
`docs/adr/006-cross-cutting-decorators.md`: a decorator factory
(`governance_job`) owns the call-flow (arg parsing, dedup skip-guard,
error-to-exit-code mapping, success sentinel) while a context manager
(`_db_session`) owns the DB resource lifecycle. Each job supplies only the
per-job body, which receives a `JobContext` and returns the artifact payload.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Literal

from common.paths.repo_paths import get_repo_root
from infrastructure.database.init import DBConnection, db_session
from trading.interfaces.runtime.jobs.job_helpers import (
    logs_dir_for_repo,
    month_tag,
    resolve_accounts,
    skip_if_already_completed_for_period,
    tee_line,
    ts,
    week_tag,
    write_artifact,
)
from trading.services.accounts import load_runtime_eligible_account_names

REPO_ROOT = get_repo_root(__file__)

Period = Literal["week", "month"]

# Maps a job's cadence to the helper that builds its period tag (e.g. 2026_W26).
_TAG_FUNCS: dict[Period, Callable[[dt.datetime], str]] = {
    "week": week_tag,
    "month": month_tag,
}

# A job body: receives the prepared context, returns the artifact payload dict.
JobBody = Callable[["JobContext"], dict[str, object]]
# Optional hook a job uses to register its own CLI flags on the shared parser.
ArgAugmenter = Callable[[argparse.ArgumentParser], None]
# Optional hook validating parsed args; returns an error message, or None if valid.
ArgValidator = Callable[[argparse.Namespace], str | None]


@dataclass(frozen=True)
class JobContext:
    """Everything a governance-job body needs, prepared by the runner."""

    conn: DBConnection
    args: argparse.Namespace
    accounts: list[str]
    now: dt.datetime
    tag: str
    log_path: Path
    artifact_path: Path

    def log(self, message: str) -> None:
        """Tee a timestamped line to the run log (and stdout)."""
        tee_line(self.log_path, f"[{ts()}] {message}")


def _build_parser(*, description: str, period_label: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--accounts",
        default="all",
        help="Comma-separated account names, or 'all' (default: all)",
    )
    parser.add_argument(
        "--force-run",
        action="store_true",
        help=f"Allow duplicate same-{period_label} run",
    )
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="Repository root path (default: inferred from script location)",
    )
    return parser


def governance_job(
    *,
    job_name: str,
    sentinel: str,
    period: Period,
    description: str,
    add_arguments: ArgAugmenter | None = None,
    validate: ArgValidator | None = None,
) -> Callable[[JobBody], Callable[[], int]]:
    """Wrap an account-scoped governance-job body with the shared lifecycle.

    The body receives a fully-prepared `JobContext` and returns the artifact
    payload; the wrapper handles parsing, optional arg validation, the dedup
    skip-guard, the DB session, error-to-exit-code mapping, artifact write, and
    the completion sentinel.
    """
    period_label = period
    tag_for = _TAG_FUNCS[period]

    def decorator(body: JobBody) -> Callable[[], int]:
        @wraps(body)
        def main() -> int:
            parser = _build_parser(description=description, period_label=period_label)
            if add_arguments is not None:
                add_arguments(parser)
            args = parser.parse_args()

            if validate is not None:
                error = validate(args)
                if error is not None:
                    print(error, file=sys.stderr)
                    return 1

            repo_root = Path(args.repo_root).expanduser().resolve()
            logs_dir = logs_dir_for_repo(repo_root)
            artifacts_dir = repo_root / "local" / "artifacts"
            logs_dir.mkdir(parents=True, exist_ok=True)
            artifacts_dir.mkdir(parents=True, exist_ok=True)

            now = dt.datetime.now()
            tag = tag_for(now)
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            log_path = logs_dir / f"{job_name}_{tag}_{timestamp}.log"
            artifact_path = artifacts_dir / f"{job_name}_{tag}_{timestamp}.json"

            tee_line(
                log_path,
                f"[{ts()}] RUN META: job={job_name} {period_label}={tag} force={bool(args.force_run)}",
            )

            if skip_if_already_completed_for_period(
                log_path=log_path,
                log_dir=logs_dir,
                job_name=job_name,
                period_name=period_label,
                period_tag=tag,
                sentinel=sentinel,
                force_run=bool(args.force_run),
            ):
                return 0

            try:
                accounts = resolve_accounts(args.accounts, load_runtime_eligible_account_names())
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                return 1
            if not accounts:
                print("No accounts specified.", file=sys.stderr)
                return 1

            try:
                with db_session() as conn:
                    ctx = JobContext(
                        conn=conn,
                        args=args,
                        accounts=accounts,
                        now=now,
                        tag=tag,
                        log_path=log_path,
                        artifact_path=artifact_path,
                    )
                    payload = body(ctx)
                    write_artifact(artifact_path, payload)
                    tee_line(log_path, f"[{ts()}] {sentinel}")
                    return 0
            except Exception as exc:
                tee_line(log_path, f"[{ts()}] ERROR: {exc}")
                return 1

        return main

    return decorator
