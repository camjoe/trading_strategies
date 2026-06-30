"""Private shared lifecycle core for runtime jobs.

Not imported directly by jobs — use the public `governance_job` /
`daily_account_job` decorators (re-exported from the package `__init__`). This
module owns the call-flow (arg parsing, optional enable-gate, dedup skip-guard,
DB session, error-to-exit-code mapping, artifact write, success sentinel) and the
`JobContext` passed to each job body.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Literal

from common.paths.repo_paths import get_repo_root
from infrastructure.database.init import DBConnection, db_session
from trading.interfaces.runtime.jobs.job_helpers import (
    already_completed_for_period,
    day_tag,
    is_env_truthy,
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

Period = Literal["day", "week", "month"]

# Maps a job's cadence to the helper that builds its period tag (e.g. 2026_W26).
_TAG_FUNCS: dict[Period, Callable[[dt.datetime], str]] = {
    "day": day_tag,
    "week": week_tag,
    "month": month_tag,
}

# A whole-run job body: receives the prepared context, returns the payload dict.
JobBody = Callable[["JobContext"], dict[str, object]]
# A per-account job body: receives the context and one account, returns a result
# dict carrying at least a ``status`` key (``"success"`` marks the account done).
AccountJobBody = Callable[["JobContext", str], dict[str, object]]
# Optional hook a job uses to register its own CLI flags on the shared parser.
ArgAugmenter = Callable[[argparse.ArgumentParser], None]
# Optional hook validating parsed args; returns an error message, or None if valid.
ArgValidator = Callable[[argparse.Namespace], str | None]
# Optional hook contributing job-specific fields to a per-account run's metadata.
MetaAugmenter = Callable[[argparse.Namespace], dict[str, object]]


@dataclass(frozen=True)
class JobContext:
    """Everything a job body needs, prepared by the runner.

    ``conn`` is ``None`` for jobs that shell out to subprocesses rather than
    opening a DB session.
    """

    args: argparse.Namespace
    accounts: list[str]
    now: dt.datetime
    tag: str
    repo_root: Path
    log_path: Path
    artifact_path: Path
    conn: DBConnection | None = None

    def log(self, message: str) -> None:
        """Tee a timestamped line to the run log (and stdout)."""
        tee_line(self.log_path, f"[{ts()}] {message}")


def _build_parser(
    *,
    description: str,
    period_label: str,
    run_source_default: str | None,
    enable_gate: bool,
) -> argparse.ArgumentParser:
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
    if run_source_default is not None:
        parser.add_argument("--run-source", default=run_source_default)
    if enable_gate:
        parser.add_argument(
            "--enable-run",
            action="store_true",
            help="Explicitly enable execution for this invocation",
        )
    return parser


def _is_run_enabled(args: argparse.Namespace, enabled_env: str) -> bool:
    if bool(getattr(args, "enable_run", False)):
        return True
    return is_env_truthy(enabled_env)


@dataclass(frozen=True)
class _Prepared:
    """Parsed args plus the resolved run-scoped paths shared by both flows."""

    args: argparse.Namespace
    repo_root: Path
    logs_dir: Path
    now: dt.datetime
    tag: str
    log_path: Path
    artifact_path: Path


def _prepare_run(
    *,
    job_name: str,
    period: Period,
    description: str,
    run_source_default: str | None,
    enable_gate: bool,
    add_arguments: ArgAugmenter | None,
    export_subdir: str | None,
) -> _Prepared:
    parser = _build_parser(
        description=description,
        period_label=period,
        run_source_default=run_source_default,
        enable_gate=enable_gate,
    )
    if add_arguments is not None:
        add_arguments(parser)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    logs_dir = logs_dir_for_repo(repo_root)
    logs_dir.mkdir(parents=True, exist_ok=True)

    if export_subdir is None:
        artifacts_dir = repo_root / "local" / "artifacts"
    else:
        artifacts_dir = repo_root / "local" / "exports" / export_subdir
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    now = dt.datetime.now()
    tag = _TAG_FUNCS[period](now)
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"{job_name}_{tag}_{timestamp}.log"
    if export_subdir is None:
        artifact_path = artifacts_dir / f"{job_name}_{tag}_{timestamp}.json"
    else:
        artifact_path = artifacts_dir / f"{job_name}_{timestamp}.json"

    return _Prepared(
        args=args,
        repo_root=repo_root,
        logs_dir=logs_dir,
        now=now,
        tag=tag,
        log_path=log_path,
        artifact_path=artifact_path,
    )


def _resolve_or_exit(accounts_arg: str) -> list[str] | int:
    """Resolve accounts, returning an exit code on failure instead of the list."""
    try:
        accounts = resolve_accounts(accounts_arg, load_runtime_eligible_account_names())
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if not accounts:
        print("No accounts specified.", file=sys.stderr)
        return 1
    return accounts


def _run_whole_job(
    prep: _Prepared,
    *,
    job_name: str,
    sentinel: str,
    period: Period,
    body: JobBody,
) -> int:
    """Governance flow: skip-guard, single DB-backed body, one artifact."""
    tee_line(
        prep.log_path,
        f"[{ts()}] RUN META: job={job_name} {period}={prep.tag} force={bool(prep.args.force_run)}",
    )

    if skip_if_already_completed_for_period(
        log_path=prep.log_path,
        log_dir=prep.logs_dir,
        job_name=job_name,
        period_name=period,
        period_tag=prep.tag,
        sentinel=sentinel,
        force_run=bool(prep.args.force_run),
    ):
        return 0

    accounts = _resolve_or_exit(prep.args.accounts)
    if isinstance(accounts, int):
        return accounts

    try:
        with db_session() as conn:
            ctx = JobContext(
                args=prep.args,
                accounts=accounts,
                now=prep.now,
                tag=prep.tag,
                repo_root=prep.repo_root,
                log_path=prep.log_path,
                artifact_path=prep.artifact_path,
                conn=conn,
            )
            payload = body(ctx)
            write_artifact(prep.artifact_path, payload)
            tee_line(prep.log_path, f"[{ts()}] {sentinel}")
            return 0
    except Exception as exc:
        tee_line(prep.log_path, f"[{ts()}] ERROR: {exc}")
        return 1


def _run_per_account_job(
    prep: _Prepared,
    *,
    job_name: str,
    sentinel: str,
    period: Period,
    label: str,
    open_db: bool,
    extra_meta: MetaAugmenter | None,
    body: AccountJobBody,
) -> int:
    """Daily flow: per-account body, stop-on-first-failure, combined artifact."""
    accounts = _resolve_or_exit(prep.args.accounts)
    if isinstance(accounts, int):
        return accounts

    run_meta: dict[str, object] = {
        "job": job_name,
        "run_source": getattr(prep.args, "run_source", None),
        "force_run": bool(prep.args.force_run),
        f"{period}_tag": prep.tag,
        "accounts": accounts,
        **(extra_meta(prep.args) if extra_meta is not None else {}),
        "log_path": str(prep.log_path.relative_to(prep.repo_root)),
        "artifact_path": str(prep.artifact_path.relative_to(prep.repo_root)),
        "started_at": ts(),
    }
    tee_line(prep.log_path, f"[{ts()}] RUN META: {json.dumps(run_meta, sort_keys=True)}")

    if not prep.args.force_run and already_completed_for_period(
        log_dir=prep.logs_dir,
        job_name=job_name,
        period_tag=prep.tag,
        sentinel=sentinel,
    ):
        message = f"{job_name}: already completed this {period}; skipping duplicate run."
        tee_line(prep.log_path, f"[{ts()}] SKIP: {message}")
        write_artifact(
            prep.artifact_path,
            {
                **run_meta,
                "status": "skipped",
                "skip_reason": f"already-completed-this-{period}",
                "results": [],
                "finished_at": ts(),
            },
        )
        print(message)
        return 0

    try:
        if open_db:
            with db_session() as conn:
                return _process_accounts(
                    prep, accounts, run_meta, job_name=job_name, sentinel=sentinel, label=label, body=body, conn=conn
                )
        return _process_accounts(
            prep, accounts, run_meta, job_name=job_name, sentinel=sentinel, label=label, body=body, conn=None
        )
    except Exception as exc:
        tee_line(prep.log_path, f"[{ts()}] ERROR: {exc}")
        write_artifact(
            prep.artifact_path,
            {**run_meta, "status": "failed", "error": str(exc), "results": [], "finished_at": ts()},
        )
        return 1


def _process_accounts(
    prep: _Prepared,
    accounts: list[str],
    run_meta: dict[str, object],
    *,
    job_name: str,
    sentinel: str,
    label: str,
    body: AccountJobBody,
    conn: DBConnection | None,
) -> int:
    ctx = JobContext(
        args=prep.args,
        accounts=accounts,
        now=prep.now,
        tag=prep.tag,
        repo_root=prep.repo_root,
        log_path=prep.log_path,
        artifact_path=prep.artifact_path,
        conn=conn,
    )

    results: list[dict[str, object]] = []
    failed = False
    for account in accounts:
        result = body(ctx, account)
        results.append(result)
        if result.get("status") != "success":
            failed = True
            tee_line(
                prep.log_path,
                (
                    f"[{ts()}] ERROR: {label} failed for account={account} "
                    f"attempts={result.get('attempts')} transient={result.get('transient', False)}"
                ),
            )
            break

    if not failed:
        tee_line(prep.log_path, f"[{ts()}] {sentinel}")

    write_artifact(
        prep.artifact_path,
        {
            **run_meta,
            "status": "success" if not failed else "failed",
            "results": results,
            "finished_at": ts(),
        },
    )
    return 0 if not failed else 1


def account_job(
    *,
    job_name: str,
    sentinel: str,
    period: Period,
    description: str,
    add_arguments: ArgAugmenter | None = None,
    validate: ArgValidator | None = None,
    per_account: bool = False,
    enabled_env: str | None = None,
    disabled_message: str | None = None,
    run_source_default: str | None = None,
    export_subdir: str | None = None,
    label: str | None = None,
    open_db: bool = True,
    extra_meta: MetaAugmenter | None = None,
) -> Callable[[JobBody | AccountJobBody], Callable[[], int]]:
    """Shared lifecycle core behind the public `governance_job` /
    `daily_account_job` decorators — not called directly by jobs.

    Owns parsing, optional ``validate``, an optional enable-gate
    (``enabled_env``), the dedup skip-guard, the DB session, error-to-exit-code
    mapping, artifact write, and the completion sentinel. ``per_account`` selects
    the body shape and the daily-job behaviors (enable-gate, ``exports``
    artifact, combined ``results`` payload); the default is the whole-run
    governance flow.
    """

    def decorator(body: JobBody | AccountJobBody) -> Callable[[], int]:
        @wraps(body)
        def main() -> int:
            prep = _prepare_run(
                job_name=job_name,
                period=period,
                description=description,
                run_source_default=run_source_default,
                enable_gate=enabled_env is not None,
                add_arguments=add_arguments,
                export_subdir=export_subdir,
            )

            if validate is not None:
                error = validate(prep.args)
                if error is not None:
                    print(error, file=sys.stderr)
                    return 1

            if enabled_env is not None and not _is_run_enabled(prep.args, enabled_env):
                print(disabled_message or f"{job_name} is disabled. Use --enable-run to execute.", file=sys.stderr)
                return 0

            if per_account:
                return _run_per_account_job(
                    prep,
                    job_name=job_name,
                    sentinel=sentinel,
                    period=period,
                    label=label or job_name,
                    open_db=open_db,
                    extra_meta=extra_meta,
                    body=body,  # type: ignore[arg-type]
                )
            return _run_whole_job(
                prep,
                job_name=job_name,
                sentinel=sentinel,
                period=period,
                body=body,  # type: ignore[arg-type]
            )

        return main

    return decorator
