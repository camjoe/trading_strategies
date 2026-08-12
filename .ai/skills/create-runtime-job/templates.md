# Runtime Job Templates

Copy the template matching the shape chosen in `SKILL.md` step 1. Replace
`<...>` placeholders. Keep the module to constants, helpers, and the body.

## Daily account job

`src/trading/interfaces/runtime/jobs/daily/<name>.py`

```python
#!/usr/bin/env python3
"""<One-line description>."""

from __future__ import annotations

import argparse

from common.runtime_job_status import <SENTINEL_CONST>
from trading.interfaces.runtime.jobs.job_runner import JobContext, daily_account_job

JOB_NAME = "<job_name>"
COMPLETE_SENTINEL = <SENTINEL_CONST>
<ENABLED_ENV_CONST> = "<JOB>_ENABLED"


def _add_arguments(parser: argparse.ArgumentParser) -> None:
    # Job-specific flags only. The runner supplies --accounts, --force-run,
    # --repo-root, --run-source, and --enable-run.
    ...


def _validate(args: argparse.Namespace) -> str | None:
    # Return an error message string, or None when valid.
    return None


def _run_meta(args: argparse.Namespace) -> dict[str, object]:
    # Job-specific fields merged into the per-run artifact metadata.
    return {}


@daily_account_job(
    job_name=JOB_NAME,
    sentinel=COMPLETE_SENTINEL,
    description="<description>",
    enabled_env=<ENABLED_ENV_CONST>,
    disabled_message="<Job> is disabled. Use --enable-run or set <JOB>_ENABLED=1 to execute.",
    run_source_default="<run-source>",
    export_subdir="<exports_subdir>",
    label="<Label>",
    open_db=False,  # True only if the body uses ctx.conn in-process
    add_arguments=_add_arguments,
    validate=_validate,
    extra_meta=_run_meta,
)
def main(ctx: JobContext, account: str) -> dict[str, object]:
    # Do the per-account work; return a dict with a "status" key.
    # "success" lets the runner continue; anything else stops the run.
    ...


if __name__ == "__main__":
    raise SystemExit(main())
```

## Governance job

`src/trading/interfaces/runtime/jobs/governance/<weekly|monthly>/<name>.py`

```python
#!/usr/bin/env python3
"""<One-line description>."""

from __future__ import annotations

import argparse

from common.runtime_job_status import <SENTINEL_CONST>
from trading.interfaces.runtime.jobs.job_runner import JobContext, governance_job

JOB_NAME = "<job_name>"
COMPLETE_SENTINEL = <SENTINEL_CONST>


def _add_arguments(parser: argparse.ArgumentParser) -> None:
    ...


def _validate(args: argparse.Namespace) -> str | None:
    return None


@governance_job(
    job_name=JOB_NAME,
    sentinel=COMPLETE_SENTINEL,
    period="week",  # or "month"
    description="<description>",
    add_arguments=_add_arguments,
    validate=_validate,
)
def main(ctx: JobContext) -> dict[str, object]:
    # ctx.conn is an open DB session; ctx.accounts is the resolved list.
    # Return the artifact payload dict.
    ...


if __name__ == "__main__":
    raise SystemExit(main())
```

## Maintenance job

`src/trading/interfaces/runtime/jobs/maintenance/<name>.py`

```python
#!/usr/bin/env python3
"""<One-line description>."""

from __future__ import annotations

import argparse

from common.runtime_job_status import <SENTINEL_CONST>
from trading.interfaces.runtime.jobs.job_helpers import run_command
from trading.interfaces.runtime.jobs.job_runner import JobContext, maintenance_job

JOB_NAME = "<job_name>"
COMPLETE_SENTINEL = <SENTINEL_CONST>


def _add_arguments(parser: argparse.ArgumentParser) -> None:
    ...


@maintenance_job(
    job_name=JOB_NAME,
    sentinel=COMPLETE_SENTINEL,
    period="week",  # or "month"
    description="<description>",
    add_arguments=_add_arguments,
)
def main(ctx: JobContext) -> int:
    # No accounts, no artifact. Return a process exit code; the sentinel is
    # written only on a zero exit.
    exit_code, _ = run_command(ctx.log_path, "<Label>", ["-m", "<module>", "<cmd>"], ctx.repo_root)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
```

## Test (daily account job)

`tests/src/trading/interfaces/runtime/jobs/daily/test_<name>_main.py`

```python
from __future__ import annotations

import datetime as dt
from pathlib import Path

import trading.interfaces.runtime.jobs.job_runner._core as job_runner
from trading.interfaces.runtime.jobs.job_helpers import day_tag
from tests.src.trading.interfaces.runtime.jobs.loaders import (
    load_single_artifact_json,
    run_runtime_job_with_args,
    write_completed_runtime_log,
)

MODULE_NAME = "trading.interfaces.runtime.jobs.daily.<name>"
import trading.interfaces.runtime.jobs.daily.<name> as module  # noqa: E402
EXPORTS_DIR_PARTS = ("local", "exports", "<exports_subdir>")
ARTIFACT_GLOB = "<job_name>_*.json"


def _run(monkeypatch, tmp_path: Path, args: tuple[str, ...]) -> int:
    return run_runtime_job_with_args(monkeypatch, tmp_path, MODULE_NAME, args)


def _stub_accounts(monkeypatch, accounts: list[str]) -> None:
    monkeypatch.setattr(job_runner, "load_account_names", lambda: list(accounts))


def test_reports_disabled_runs(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.delenv(module.<ENABLED_ENV_CONST>, raising=False)
    assert _run(monkeypatch, tmp_path, ()) == 0
    assert "disabled" in capsys.readouterr().err


def test_success_writes_artifact(monkeypatch, tmp_path) -> None:
    _stub_accounts(monkeypatch, ["acct1"])
    monkeypatch.setattr(module, "<body_helper>", lambda **_kw: {"account": "acct1", "status": "success"})
    assert _run(monkeypatch, tmp_path, ("--enable-run", "--force-run")) == 0
    payload = load_single_artifact_json(tmp_path.joinpath(*EXPORTS_DIR_PARTS), ARTIFACT_GLOB)
    assert payload["status"] == "success"


def test_skips_duplicate_run(monkeypatch, tmp_path) -> None:
    _stub_accounts(monkeypatch, ["acct1"])
    write_completed_runtime_log(
        tmp_path, filename_prefix="<job_name>", tag=day_tag(dt.datetime.now()), sentinel=module.COMPLETE_SENTINEL
    )
    assert _run(monkeypatch, tmp_path, ("--enable-run",)) == 0
```

## Test (maintenance job)

```python
import trading.interfaces.runtime.jobs.job_helpers as job_helpers
from tests.src.trading.interfaces.runtime.jobs.loaders import run_runtime_job_main, write_completed_runtime_log

MODULE_NAME = "trading.interfaces.runtime.jobs.maintenance.<name>"


def test_runs_and_writes_sentinel(monkeypatch, tmp_path) -> None:
    import importlib
    module = importlib.import_module(MODULE_NAME)
    monkeypatch.setattr(module, "run_command", lambda *_a: (0, "ok"))
    assert run_runtime_job_main(monkeypatch, tmp_path, MODULE_NAME, ["--force-run"]) == 0
```

## Governance test

Mirror `tests/src/trading/interfaces/runtime/jobs/governance/weekly/test_w1_leaderboard.py`: it uses
`run_runtime_job_with_args` plus `stub_runtime_job_basics(monkeypatch, module, ...)` to stub
the DB/account surfaces, and reads the artifact from `tmp_path / "local" / "artifacts"`.

## Sentinel + schedule snippets

`src/common/runtime_job_status.py`:

```python
<JOB>_COMPLETE_SENTINEL = "<Job> run succeeded."
# ...add the name to __all__
```

`manage_job_schedules.py` (daily/maintenance only):

```python
<NAME>_MODULE = "trading.interfaces.runtime.jobs.<area>.<name>"
DEFAULT_<NAME>_TASK_NAME = r"Trading\<TaskName>"
# parse_args: parser.add_argument("--<name>-time", default="", help="HH:MM ...")
# build_scheduled_tasks: append _scheduled_task(...) when args.<name>_time is set
# default_task_names: include args.<name>_task_name
```
