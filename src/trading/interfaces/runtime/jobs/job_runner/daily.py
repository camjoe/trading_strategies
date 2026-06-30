"""Public decorator for per-account daily jobs."""

from __future__ import annotations

from collections.abc import Callable

from trading.interfaces.runtime.jobs.job_runner._core import (
    AccountJobBody,
    ArgAugmenter,
    ArgValidator,
    MetaAugmenter,
    account_job,
)


def daily_account_job(
    *,
    job_name: str,
    sentinel: str,
    description: str,
    enabled_env: str,
    export_subdir: str,
    run_source_default: str,
    disabled_message: str,
    label: str,
    open_db: bool = False,
    add_arguments: ArgAugmenter | None = None,
    validate: ArgValidator | None = None,
    extra_meta: MetaAugmenter | None = None,
) -> Callable[[AccountJobBody], Callable[[], int]]:
    """Per-account daily job: `body(ctx, account) -> result`.

    Runs the body once per runtime-eligible account, stops on the first
    non-``success`` result, and writes a combined ``results`` artifact under
    `local/exports/<export_subdir>`. Gated behind ``--enable-run`` /
    ``enabled_env``. Set ``open_db=True`` for bodies that run against the DB
    in-process (the runner opens the session); leave it False for bodies that
    shell out to subprocesses.
    """
    return account_job(  # type: ignore[return-value]
        job_name=job_name,
        sentinel=sentinel,
        period="day",
        description=description,
        add_arguments=add_arguments,
        validate=validate,
        per_account=True,
        enabled_env=enabled_env,
        disabled_message=disabled_message,
        run_source_default=run_source_default,
        export_subdir=export_subdir,
        label=label,
        open_db=open_db,
        extra_meta=extra_meta,
    )
