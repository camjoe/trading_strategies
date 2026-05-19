from pathlib import Path
from unittest.mock import Mock

from tests.trading.interfaces.runtime.jobs.helpers import (
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
