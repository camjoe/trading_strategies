from __future__ import annotations

from pathlib import Path

from trading.interfaces.runtime.jobs.job_helpers import (
    latest_log_contains_sentinel,
    logs_dir_for_repo,
    run_command,
    stream_command,
    tee_line,
)


def test_logs_dir_for_repo_uses_local_logs(tmp_path: Path):
    assert logs_dir_for_repo(tmp_path) == tmp_path / "local" / "logs"


def test_tee_line_appends_and_prints(tmp_path: Path, capsys):
    log_path = tmp_path / "task.log"

    tee_line(log_path, "hello")

    captured = capsys.readouterr()
    assert captured.out == "hello\n"
    assert log_path.read_text(encoding="utf-8") == "hello\n"


def test_latest_log_contains_sentinel_uses_newest_match(tmp_path: Path):
    older = tmp_path / "job_older.log"
    newer = tmp_path / "job_newer.log"
    older.write_text("COMPLETE\n", encoding="utf-8")
    newer.write_text("incomplete\n", encoding="utf-8")

    assert latest_log_contains_sentinel(tmp_path, "job_*.log", "COMPLETE") is False


def test_latest_log_contains_sentinel_returns_false_without_matches(tmp_path: Path):
    assert latest_log_contains_sentinel(tmp_path, "missing_*.log", "COMPLETE") is False


def test_run_command_returns_exit_code_and_output(tmp_path: Path):
    log_path = tmp_path / "run.log"
    exit_code, output = run_command(
        log_path,
        "echo-test",
        ["-c", "print('hello from subprocess')"],
        tmp_path,
    )
    assert exit_code == 0
    assert "hello from subprocess" in output
    log_text = log_path.read_text(encoding="utf-8")
    assert "START: echo-test" in log_text
    assert "DONE: echo-test" in log_text


def test_run_command_captures_nonzero_exit(tmp_path: Path):
    log_path = tmp_path / "run.log"
    exit_code, output = run_command(
        log_path,
        "failing-step",
        ["-c", "import sys; sys.exit(2)"],
        tmp_path,
    )
    assert exit_code == 2
    assert "ERROR: failing-step" in log_path.read_text(encoding="utf-8")


def test_stream_command_raises_on_nonzero(tmp_path: Path):
    import pytest

    log_path = tmp_path / "run.log"
    with pytest.raises(RuntimeError, match="Step failed: bad-step"):
        stream_command(
            log_path,
            "bad-step",
            ["-c", "import sys; sys.exit(1)"],
            tmp_path,
        )


def test_stream_command_succeeds_silently(tmp_path: Path):
    log_path = tmp_path / "run.log"
    stream_command(
        log_path,
        "ok-step",
        ["-c", "print('output')"],
        tmp_path,
    )
    log_text = log_path.read_text(encoding="utf-8")
    assert "DONE: ok-step" in log_text
