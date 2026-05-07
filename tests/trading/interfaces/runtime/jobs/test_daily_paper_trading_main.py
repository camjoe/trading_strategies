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
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_MODULE}.load_runtime_eligible_account_names", lambda: ["acct_a"])

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
    assert payload["step_results"]
    assert payload["step_results"][0]["step"] == "00_ingest_market_and_account"
    assert payload["step_results"][-1]["step"] == "10_emit_report_and_alerts"


def test_optional_shadow_eval_step_runs_before_auto_trader(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, list[str]]] = []

    def _capture(_log_path, label, args, _cwd):
        calls.append((label, args))

    monkeypatch.setattr(
        f"{DAILY_PAPER_TRADING_MODULE}.stream_command",
        _capture,
    )
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_MODULE}.load_runtime_eligible_account_names", lambda: ["acct_a"])

    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        [
            "--accounts",
            "acct_a",
            "--run-challenger-shadow-eval",
            "--shadow-eval-rolling-window-days",
            "45",
        ],
    )

    assert code == 0
    assert calls
    assert calls[0][0] == "Challenger Shadow Eval"
    assert "trading.interfaces.runtime.jobs.daily_challenger_shadow_eval" in calls[0][1]
    assert "--rolling-window-days" in calls[0][1]


def test_shadow_eval_summary_is_embedded_in_daily_artifact(monkeypatch, tmp_path: Path) -> None:
    shadow_export_dir = tmp_path / "local" / "exports" / "daily_challenger_shadow_eval"
    shadow_export_dir.mkdir(parents=True, exist_ok=True)
    (shadow_export_dir / "daily_challenger_shadow_eval_20260507_120000.json").write_text(
        json.dumps(
            {
                "status": "success",
                "results": [
                    {
                        "account_name": "acct_a",
                        "sleeves": [
                            {"sleeve_id": 1, "challenger_count": 2},
                            {"sleeve_id": 2, "challenger_count": 1},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        f"{DAILY_PAPER_TRADING_MODULE}.stream_command",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_MODULE}.load_runtime_eligible_account_names", lambda: ["acct_a"])

    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a", "--run-challenger-shadow-eval"],
    )

    assert code == 0
    artifacts = list((tmp_path / "local" / "exports" / "daily_paper_trading").glob("daily_paper_trading_*.json"))
    assert len(artifacts) == 1
    payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
    score_steps = [step for step in payload["step_results"] if step["step"] == "03_score_incumbent_vs_challengers"]
    assert len(score_steps) == 1
    summary = score_steps[0]["details"]["shadow_eval_summary"]
    assert summary is not None
    assert summary["account_count"] == 1
    assert summary["sleeve_count"] == 2
    assert summary["challenger_count"] == 3

def test_unknown_account_returns_1(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_MODULE}.load_runtime_eligible_account_names", lambda: ["real_acct"])

    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "ghost_acct"],
    )

    assert code == 1
    assert "Unknown account" in capsys.readouterr().err


def test_no_accounts_returns_1(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_MODULE}.load_runtime_eligible_account_names", lambda: [])

    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "all"],
    )

    assert code == 1
    assert "No accounts" in capsys.readouterr().err

def test_invalid_primary_trade_cap_returns_1(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_MODULE}.load_runtime_eligible_account_names", lambda: ["acct_a"])

    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a", "--primary-min-trades", "5", "--primary-max-trades", "2"],
    )

    assert code == 1
    assert "primary-max-trades" in capsys.readouterr().err


def test_invalid_shadow_eval_window_returns_1(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_MODULE}.load_runtime_eligible_account_names", lambda: ["acct_a"])

    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a", "--shadow-eval-rolling-window-days", "0"],
    )

    assert code == 1
    assert "shadow-eval-rolling-window-days" in capsys.readouterr().err

def test_stream_command_exception_returns_1(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_MODULE}.load_runtime_eligible_account_names", lambda: ["acct_a"])
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
    artifacts = list((tmp_path / "local" / "exports" / "daily_paper_trading").glob("daily_paper_trading_*.json"))
    assert len(artifacts) == 1
    payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["failed_step"] == "05_build_position_targets_by_sleeve"
    failed_steps = [step for step in payload["step_results"] if step["status"] == "failed"]
    assert len(failed_steps) == 1
    assert failed_steps[0]["step"] == "05_build_position_targets_by_sleeve"


def test_step_results_preserve_dag_order(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_MODULE}.load_runtime_eligible_account_names", lambda: ["acct_a"])
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_MODULE}.stream_command", lambda *_args, **_kwargs: None)

    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a"],
    )

    assert code == 0
    artifacts = list((tmp_path / "local" / "exports" / "daily_paper_trading").glob("daily_paper_trading_*.json"))
    assert len(artifacts) == 1
    payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
    ordered_steps = [step["step"] for step in payload["step_results"]]
    assert ordered_steps == [step_id for step_id, _name in module.DAILY_DAG_STEPS]

def test_success_notification_requires_flag(monkeypatch, tmp_path: Path) -> None:
    sent: list[dict[str, object]] = []
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_MODULE}.load_runtime_eligible_account_names", lambda: ["acct_a"])
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
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_MODULE}.load_runtime_eligible_account_names", lambda: ["acct_a"])
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
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_MODULE}.load_runtime_eligible_account_names", lambda: ["acct_a"])
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
