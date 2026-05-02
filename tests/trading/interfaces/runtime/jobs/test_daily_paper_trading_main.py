from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

from tests.support.runtime_jobs import DAILY_PAPER_TRADING_MODULE, daily_paper_trading as module, run_runtime_job_main


def test_duplicate_run_guard_skips_when_already_done(monkeypatch, tmp_path: Path, capsys) -> None:
    log_dir = tmp_path / "local" / "logs"
    log_dir.mkdir(parents=True)
    today = dt.date.today().strftime("%Y%m%d")
    (log_dir / f"daily_paper_trading_{today}_000000.log").write_text(
        f"{module.COMPLETE_SENTINEL}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "argv", ["daily_paper_trading", "--repo-root", str(tmp_path)])
    code = module.main()

    assert code == 0
    assert "skipping duplicate run" in capsys.readouterr().out

def test_force_run_bypasses_duplicate_guard(monkeypatch, tmp_path: Path) -> None:
    log_dir = tmp_path / "local" / "logs"
    log_dir.mkdir(parents=True)
    today = dt.date.today().strftime("%Y%m%d")
    (log_dir / f"daily_paper_trading_{today}_000000.log").write_text(
        f"{module.COMPLETE_SENTINEL}\n",
        encoding="utf-8",
    )

    stream_calls: list[str] = []
    monkeypatch.setattr(
        f"{DAILY_PAPER_TRADING_MODULE}.stream_command",
        lambda _log_path, label, _args, _cwd: stream_calls.append(label),
    )
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_MODULE}.load_runtime_job_account_names", lambda: ["acct_a"])

    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--force-run", "--accounts", "acct_a"],
    )

    assert code == 0
    assert stream_calls
    artifacts = list((tmp_path / "local" / "exports" / "daily_paper_trading").glob("daily_paper_trading_*.json"))
    assert len(artifacts) == 1
    payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert payload["status"] == "success"
    assert payload["completed_steps"]

def test_unknown_account_returns_1(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_MODULE}.load_runtime_job_account_names", lambda: ["real_acct"])

    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "ghost_acct"],
    )

    assert code == 1
    assert "Unknown account" in capsys.readouterr().err


def test_manual_only_test_account_alias_returns_1(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_MODULE}.load_runtime_job_account_names", lambda: ["real_acct"])

    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "test_account"],
    )

    assert code == 1
    assert "excluded from automated runtime jobs" in capsys.readouterr().err

def test_no_accounts_returns_1(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_MODULE}.load_runtime_job_account_names", lambda: [])

    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "all"],
    )

    assert code == 1
    assert "No accounts" in capsys.readouterr().err

def test_invalid_primary_trade_cap_returns_1(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_MODULE}.load_runtime_job_account_names", lambda: ["acct_a"])

    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a", "--primary-min-trades", "5", "--primary-max-trades", "2"],
    )

    assert code == 1
    assert "primary-max-trades" in capsys.readouterr().err

def test_stream_command_exception_returns_1(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_MODULE}.load_runtime_job_account_names", lambda: ["acct_a"])
    monkeypatch.setattr(
        f"{DAILY_PAPER_TRADING_MODULE}.stream_command",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("step failed")),
    )

    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a"],
    )

    assert code == 1

def test_success_notification_requires_flag(monkeypatch, tmp_path: Path) -> None:
    sent: list[dict[str, object]] = []
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_MODULE}.load_runtime_job_account_names", lambda: ["acct_a"])
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_MODULE}.stream_command", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        f"{DAILY_PAPER_TRADING_MODULE}.notify_webhook_best_effort",
        lambda **kwargs: sent.append(kwargs) or True,
    )

    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a", "--notify-webhook-url", "https://example.test/webhook"],
    )

    assert code == 0
    assert sent == []

def test_success_notification_sent_when_enabled(monkeypatch, tmp_path: Path) -> None:
    sent: list[dict[str, object]] = []
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_MODULE}.load_runtime_job_account_names", lambda: ["acct_a"])
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_MODULE}.stream_command", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        f"{DAILY_PAPER_TRADING_MODULE}.notify_webhook_best_effort",
        lambda **kwargs: sent.append(kwargs) or True,
    )

    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        [
            "--accounts",
            "acct_a",
            "--notify-webhook-url",
            "https://example.test/webhook",
            "--notify-on-success",
        ],
    )

    assert code == 0
    assert len(sent) == 1
    assert sent[0]["status"] == "ok"
    assert sent[0]["event"] == "daily-paper-trading"

def test_failure_notification_sent_when_run_fails(monkeypatch, tmp_path: Path) -> None:
    sent: list[dict[str, object]] = []
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_MODULE}.load_runtime_job_account_names", lambda: ["acct_a"])
    monkeypatch.setattr(
        f"{DAILY_PAPER_TRADING_MODULE}.stream_command",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("step failed")),
    )
    monkeypatch.setattr(
        f"{DAILY_PAPER_TRADING_MODULE}.notify_webhook_best_effort",
        lambda **kwargs: sent.append(kwargs) or True,
    )

    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a", "--notify-webhook-url", "https://example.test/webhook"],
    )

    assert code == 1
    assert len(sent) == 1
    assert sent[0]["status"] == "fail"
    artifacts = list((tmp_path / "local" / "exports" / "daily_paper_trading").glob("daily_paper_trading_*.json"))
    assert len(artifacts) == 1
    payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["error"] == "step failed"
