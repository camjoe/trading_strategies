"""Public decorator for non-account maintenance jobs."""

from __future__ import annotations

from collections.abc import Callable

from trading.interfaces.runtime.jobs.job_runner._core import (
    ArgAugmenter,
    ArgValidator,
    MaintenanceBody,
    Period,
    account_job,
)


def maintenance_job(
    *,
    job_name: str,
    sentinel: str,
    period: Period,
    description: str,
    add_arguments: ArgAugmenter | None = None,
    validate: ArgValidator | None = None,
) -> Callable[[MaintenanceBody], Callable[[], int]]:
    """Non-account maintenance job: `body(ctx) -> exit_code`.

    Dedups per period, runs the body once (no accounts, no artifact), and writes
    the sentinel only on a zero exit. Used for housekeeping jobs like the weekly
    DB backup.
    """
    return account_job(  # type: ignore[return-value]
        job_name=job_name,
        sentinel=sentinel,
        period=period,
        description=description,
        add_arguments=add_arguments,
        validate=validate,
        maintenance=True,
    )
