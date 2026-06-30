"""Shared lifecycle runner for account-scoped runtime jobs.

Implements the sanctioned cross-cutting pattern from
`docs/adr/006-cross-cutting-decorators.md`: a decorator owns the call-flow (arg
parsing, optional enable-gate, dedup skip-guard, error-to-exit-code mapping,
success sentinel) while a context manager (`db_session`) owns the DB resource
lifecycle. Each job supplies only the per-job body, which receives a
`JobContext`.

Three public decorators, one per job shape, sit over the shared private core in
`_core.py`:

- `governance_job` — **whole-run**: `body(ctx) -> payload` runs once and returns
  the artifact payload. Used by the weekly/monthly governance jobs; writes a
  tagged `local/artifacts` artifact.
- `daily_account_job` — **per-account**: `body(ctx, account) -> result` runs once
  per account; the runner collects results, stops on the first non-success, and
  writes a combined ``results`` artifact under `local/exports/<subdir>`. Gated
  behind ``--enable-run``.
- `maintenance_job` — **non-account**: `body(ctx) -> exit_code` runs once with no
  accounts and no artifact (dedup + sentinel only). Used for housekeeping like
  the weekly DB backup.

To add a new job, use the `create-runtime-job` skill, which scaffolds the module,
its test, and the schedule wiring against the right decorator.
"""

from __future__ import annotations

from trading.interfaces.runtime.jobs.job_runner._core import JobContext
from trading.interfaces.runtime.jobs.job_runner.daily import daily_account_job
from trading.interfaces.runtime.jobs.job_runner.governance import governance_job
from trading.interfaces.runtime.jobs.job_runner.maintenance import maintenance_job

__all__ = ["JobContext", "daily_account_job", "governance_job", "maintenance_job"]
