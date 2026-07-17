"""Public decorator for whole-run governance jobs."""

from __future__ import annotations

from collections.abc import Callable

from trading.interfaces.runtime.jobs.job_runner._core import (
    ArgAugmenter,
    ArgValidator,
    JobBody,
    Period,
    account_job,
)


def governance_job(
    *,
    job_name: str,
    sentinel: str,
    period: Period,
    description: str,
    add_arguments: ArgAugmenter | None = None,
    validate: ArgValidator | None = None,
) -> Callable[[JobBody], Callable[[], int]]:
    """Whole-run governance job: `body(ctx) -> payload`.

    Writes a tagged `local/artifacts` artifact, dedups per period (week/month),
    opens a DB session, and has no enable-gate. Exposes only the parameters a
    governance job needs.
    """
    return account_job(  # type: ignore[return-value]
        job_name=job_name,
        sentinel=sentinel,
        period=period,
        description=description,
        add_arguments=add_arguments,
        validate=validate,
    )
