from pathlib import Path
from unittest.mock import Mock

from tests.src.trading.interfaces.runtime.jobs.loaders import (
    daily_backtest_refresh as module,
    make_daily_backtest_refresh_args,
)


def test_run_backtest_refresh_with_retry_retries_transient_then_succeeds(tmp_path: Path) -> None:
    responses = [
        (1, "temporary failure while fetching market data; try again"),
        (0, "Backtest complete: run_id=77 account=acct1"),
    ]
    run_command = Mock(side_effect=lambda *_args, **_kwargs: responses.pop(0))
    sleep = Mock()

    result = module.run_backtest_refresh_with_retry(
        log_path=tmp_path / "run.log",
        repo_root=tmp_path,
        account="acct1",
        args=make_daily_backtest_refresh_args(backoff_seconds=1.5, max_attempts=3),
        day_tag="20260414",
        run_command_fn=run_command,
        sleep_fn=sleep,
    )

    assert result["status"] == "success"
    assert result["attempts"] == 2
    assert result["run_id"] == 77
    assert run_command.call_count == 2
    sleep.assert_called_once_with(1.5)


def test_run_backtest_refresh_with_retry_fails_when_run_id_missing(tmp_path: Path) -> None:
    run_command = Mock(return_value=(0, "Backtest complete but summary changed"))

    result = module.run_backtest_refresh_with_retry(
        log_path=tmp_path / "run.log",
        repo_root=tmp_path,
        account="acct1",
        args=make_daily_backtest_refresh_args(max_attempts=1),
        day_tag="20260414",
        run_command_fn=run_command,
        sleep_fn=lambda _seconds: None,
    )

    assert result["status"] == "failed"
    assert result["error"] == "missing_run_id"
    assert result["run_id"] is None


def test_run_backtest_refresh_with_retry_stops_on_non_transient_failure(tmp_path: Path) -> None:
    run_command = Mock(return_value=(1, "permanent failure"))
    sleep = Mock()

    result = module.run_backtest_refresh_with_retry(
        log_path=tmp_path / "run.log",
        repo_root=tmp_path,
        account="acct1",
        args=make_daily_backtest_refresh_args(max_attempts=3),
        day_tag="20260414",
        run_command_fn=run_command,
        sleep_fn=sleep,
    )

    assert result["status"] == "failed"
    assert result["attempts"] == 1
    sleep.assert_not_called()


def test_run_backtest_refresh_with_retry_uses_fallback_when_loop_never_runs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("builtins.max", lambda _a, _b: 0)

    result = module.run_backtest_refresh_with_retry(
        log_path=tmp_path / "run.log",
        repo_root=tmp_path,
        account="acct1",
        args=make_daily_backtest_refresh_args(max_attempts=3),
        day_tag="20260414",
        run_command_fn=lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("should not run")),
        sleep_fn=lambda _seconds: None,
    )

    assert result["status"] == "failed"
    assert result["attempts"] == 0
    assert result["run_id"] is None
