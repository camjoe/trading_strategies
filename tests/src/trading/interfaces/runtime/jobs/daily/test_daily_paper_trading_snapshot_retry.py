from __future__ import annotations

from pathlib import Path

import pytest

import trading.interfaces.runtime.jobs.daily.paper_trading.workflow as workflow


def _record_calls(monkeypatch, *, failures: int) -> tuple[list[str], list[float]]:
    """Stub the subprocess step to fail *failures* times, then succeed."""
    labels: list[str] = []
    slept: list[float] = []

    def fake_stream_command(_log_path, label, _args, _cwd) -> None:
        labels.append(label)
        if len(labels) <= failures:
            raise RuntimeError(f"snapshot attempt {len(labels)} failed")

    monkeypatch.setattr(workflow, "stream_command", fake_stream_command)
    monkeypatch.setattr(workflow, "tee_line", lambda *_a, **_kw: None)
    return labels, slept


def test_snapshot_succeeds_without_retrying(monkeypatch, tmp_path: Path) -> None:
    labels, slept = _record_calls(monkeypatch, failures=0)

    workflow.snapshot_account_with_retry(tmp_path / "run.log", tmp_path, "acct1", "pre-trade", sleep_fn=slept.append)

    assert labels == ["pre-trade snapshot acct1"]
    assert slept == []


def test_snapshot_retries_transient_failures_with_exponential_backoff(monkeypatch, tmp_path: Path) -> None:
    labels, slept = _record_calls(monkeypatch, failures=2)

    workflow.snapshot_account_with_retry(tmp_path / "run.log", tmp_path, "acct1", "pre-trade", sleep_fn=slept.append)

    assert len(labels) == 3
    # base, then base doubled — the gate refuses to trade on a stale snapshot, so
    # a flaky read is worth waiting out rather than failing the run.
    assert slept == [workflow.SNAPSHOT_BACKOFF_SECONDS, workflow.SNAPSHOT_BACKOFF_SECONDS * 2]


def test_snapshot_reraises_once_attempts_are_exhausted(monkeypatch, tmp_path: Path) -> None:
    labels, slept = _record_calls(monkeypatch, failures=workflow.SNAPSHOT_MAX_ATTEMPTS)

    with pytest.raises(RuntimeError, match="snapshot attempt 3 failed"):
        workflow.snapshot_account_with_retry(
            tmp_path / "run.log", tmp_path, "acct1", "pre-trade", sleep_fn=slept.append
        )

    assert len(labels) == workflow.SNAPSHOT_MAX_ATTEMPTS
    # No sleep after the final attempt — the caller is failing, not waiting.
    assert len(slept) == workflow.SNAPSHOT_MAX_ATTEMPTS - 1
