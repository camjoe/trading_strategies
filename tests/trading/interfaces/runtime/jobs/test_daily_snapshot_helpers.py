from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

from tests.support import daily_snapshot as module


def test_already_completed_today_detects_sentinel(tmp_path: Path) -> None:
    day_tag = "20260325"
    log = tmp_path / f"daily_snapshot_{day_tag}_010101.log"
    log.write_text(f"anything\n{module.COMPLETE_SENTINEL}\n", encoding="utf-8")

    assert module.already_completed_today(tmp_path, day_tag) is True


def test_retry_delay_seconds_doubles_each_attempt() -> None:
    assert module.retry_delay_seconds(2.0, 1) == 2.0
    assert module.retry_delay_seconds(2.0, 2) == 4.0
    assert module.retry_delay_seconds(2.0, 3) == 8.0


def test_run_snapshot_with_retry_retries_transient_then_succeeds(tmp_path: Path) -> None:
    responses = [
        (1, "temporary failure while fetching prices; try again"),
        (0, "snapshot saved"),
    ]
    run_command = Mock(side_effect=lambda *_args, **_kwargs: responses.pop(0))
    sleep = Mock()

    result = module.run_snapshot_with_retry(
        log_path=tmp_path / "run.log",
        repo_root=tmp_path,
        account="acct1",
        max_attempts=3,
        base_backoff_seconds=1.5,
        run_command_fn=run_command,
        sleep_fn=sleep,
    )

    assert result["status"] == "success"
    assert result["attempts"] == 2
    assert run_command.call_count == 2
    sleep.assert_called_once_with(1.5)


def test_run_snapshot_with_retry_stops_on_non_transient(tmp_path: Path) -> None:
    run_command = Mock(return_value=(1, "unknown account"))

    result = module.run_snapshot_with_retry(
        log_path=tmp_path / "run.log",
        repo_root=tmp_path,
        account="acct1",
        max_attempts=5,
        base_backoff_seconds=1.0,
        run_command_fn=run_command,
        sleep_fn=lambda _seconds: None,
    )

    assert result["status"] == "failed"
    assert result["attempts"] == 1
    assert result["transient"] is False
