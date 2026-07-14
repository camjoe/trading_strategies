from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

from tests.src.trading.interfaces.helpers import run_module_as_main
from tests.src.trading.interfaces.runtime.jobs.loaders import (
    check_daily_trader_health as module,
)


def run_main(monkeypatch, argv: list[str]) -> int:
    monkeypatch.setattr(sys, "argv", ["check_daily_trader_health"] + argv)
    return module.main()


def write_execution_log(job_root: Path, text: str) -> Path:
    path = job_root / "local" / "logs" / "daily_paper_trading_20260417_120000.log"
    path.write_text(text, encoding="utf-8")
    return path


def test_no_logs_returns_1(monkeypatch, job_root: Path, capsys) -> None:
    code = run_main(monkeypatch, ["--repo-root", str(job_root)])

    assert code == 1
    assert "No daily trader logs found" in capsys.readouterr().out


def test_stale_log_returns_1(monkeypatch, job_root: Path, capsys) -> None:
    log = write_execution_log(job_root, "anything\n")
    old_time = time.time() - 48 * 3600
    os.utime(log, (old_time, old_time))

    code = run_main(monkeypatch, ["--repo-root", str(job_root), "--max-age-hours", "24"])

    assert code == 1
    assert "stale" in capsys.readouterr().out


def test_recent_log_missing_sentinel_returns_1(monkeypatch, job_root: Path, capsys) -> None:
    write_execution_log(job_root, "partial run\n")

    code = run_main(monkeypatch, ["--repo-root", str(job_root), "--max-age-hours", "9999"])

    assert code == 1
    assert "sentinel" in capsys.readouterr().out


def test_recent_log_with_sentinel_returns_0(monkeypatch, job_root: Path) -> None:
    write_execution_log(job_root, f"run started\n{module.COMPLETE_SENTINEL}\n")

    assert run_main(monkeypatch, ["--repo-root", str(job_root), "--max-age-hours", "9999"]) == 0


def test_startup_log_is_ignored_when_execution_log_exists(monkeypatch, job_root: Path) -> None:
    write_execution_log(job_root, f"run started\n{module.COMPLETE_SENTINEL}\n")
    startup_log = job_root / "local" / "logs" / "daily_paper_trading_startup_20260417.log"
    startup_log.write_text("later startup without sentinel\n", encoding="utf-8")
    now = time.time()
    os.utime(startup_log, (now, now))

    assert run_main(monkeypatch, ["--repo-root", str(job_root), "--max-age-hours", "9999"]) == 0


def test_json_flag_emits_json(monkeypatch, job_root: Path, capsys) -> None:
    write_execution_log(job_root, f"{module.COMPLETE_SENTINEL}\n")

    code = run_main(
        monkeypatch,
        ["--repo-root", str(job_root), "--max-age-hours", "9999", "--json"],
    )

    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "ok"
    assert data["sentinel_found"] is True


def test_failure_sends_notification_when_webhook_configured(monkeypatch, job_root: Path) -> None:
    write_execution_log(job_root, "partial run\n")
    sent: list[dict[str, object]] = []
    monkeypatch.setattr(
        module,
        "notify_runtime_event",
        lambda **kwargs: sent.append(kwargs) or True,
    )

    code = run_main(
        monkeypatch,
        [
            "--repo-root",
            str(job_root),
            "--max-age-hours",
            "9999",
            "--notify-webhook-url",
            "https://example.test/webhook",
        ],
    )

    assert code == 1
    assert len(sent) == 1
    assert sent[0]["status"] == "fail"
    assert sent[0]["event"] == "daily-trader-health"


def test_success_does_not_send_notification_without_notify_on_ok(monkeypatch, job_root: Path) -> None:
    write_execution_log(job_root, f"{module.COMPLETE_SENTINEL}\n")
    sent: list[dict[str, object]] = []
    monkeypatch.setattr(
        module,
        "notify_runtime_event",
        lambda **kwargs: sent.append(kwargs) or True,
    )

    code = run_main(
        monkeypatch,
        [
            "--repo-root",
            str(job_root),
            "--max-age-hours",
            "9999",
            "--notify-webhook-url",
            "https://example.test/webhook",
        ],
    )

    assert code == 0
    assert sent == []


def test_success_sends_notification_with_notify_on_ok(monkeypatch, job_root: Path) -> None:
    write_execution_log(job_root, f"{module.COMPLETE_SENTINEL}\n")
    sent: list[dict[str, object]] = []
    monkeypatch.setattr(
        module,
        "notify_runtime_event",
        lambda **kwargs: sent.append(kwargs) or True,
    )

    code = run_main(
        monkeypatch,
        [
            "--repo-root",
            str(job_root),
            "--max-age-hours",
            "9999",
            "--notify-webhook-url",
            "https://example.test/webhook",
            "--notify-on-ok",
        ],
    )

    assert code == 0
    assert len(sent) == 1
    assert sent[0]["status"] == "ok"


def test_read_error_returns_1(monkeypatch, job_root: Path, capsys) -> None:
    log = write_execution_log(job_root, f"{module.COMPLETE_SENTINEL}\n")
    original_read_text = Path.read_text

    def _broken_read_text(self, *args, **kwargs):
        if self == log:
            raise OSError("boom")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _broken_read_text)

    code = run_main(monkeypatch, ["--repo-root", str(job_root), "--max-age-hours", "9999"])

    assert code == 1
    assert "Unable to read latest log" in capsys.readouterr().out


def test_daily_trader_health_module_main_entrypoint(monkeypatch, job_root: Path) -> None:
    monkeypatch.setattr(sys, "argv", ["check_daily_trader_health", "--repo-root", str(job_root)])

    with pytest.raises(SystemExit) as excinfo:
        run_module_as_main(module.__name__)

    assert excinfo.value.code == 1
