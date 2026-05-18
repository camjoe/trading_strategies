from __future__ import annotations

import datetime as dt
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from tests.support.runtime_jobs import (
    DAILY_PAPER_TRADING_MODULE,
    daily_paper_trading as module,
    load_single_artifact_json,
    run_runtime_job_main,
    set_runtime_eligible_accounts,
    write_completed_runtime_log,
)

_STUB_OPERATOR_REPORT = {
    "report_date": "2026-01-01",
    "account_count": 0,
    "account_reports": [],
    "artifact_path": "",
    "notify_on_success": False,
}


@pytest.fixture(autouse=True)
def _stub_build_daily_operator_report(monkeypatch):
    """Stub _build_daily_operator_report for all tests that don't need real DB access in step 10."""
    monkeypatch.setattr(
        f"{DAILY_PAPER_TRADING_MODULE}._build_daily_operator_report",
        lambda *_args, **_kwargs: dict(_STUB_OPERATOR_REPORT),
    )


@pytest.fixture
def _runtime_harness(monkeypatch):
    @dataclass
    class RuntimeHarnessState:
        accounts: list[str] = field(default_factory=lambda: ["acct_a"])
        stream_calls: list[tuple[str, list[str]]] = field(default_factory=list)
        stream_error: Exception | None = None
        notifications: list[dict[str, object]] = field(default_factory=list)

    state = RuntimeHarnessState()

    def _stream(_log_path, label, args, _cwd):
        state.stream_calls.append((label, args))
        error = state.stream_error
        if error is not None:
            raise error

    monkeypatch.setattr(
        f"{DAILY_PAPER_TRADING_MODULE}.load_runtime_eligible_account_names",
        lambda: list(state.accounts),
    )
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_MODULE}.stream_command", _stream)
    monkeypatch.setattr(
        f"{DAILY_PAPER_TRADING_MODULE}.notify_webhook_best_effort",
        lambda **kwargs: state.notifications.append(kwargs) or True,
    )
    return state


def test_duplicate_run_guard_skips_when_already_done(monkeypatch, tmp_path: Path, capsys) -> None:
    today = dt.date.today().strftime("%Y%m%d")
    write_completed_runtime_log(
        tmp_path,
        filename_prefix="daily_paper_trading",
        tag=today,
        sentinel=module.COMPLETE_SENTINEL,
        timestamp="000000",
    )

    monkeypatch.setattr(sys, "argv", ["daily_paper_trading", "--repo-root", str(tmp_path)])
    code = module.main()

    assert code == 0
    assert "skipping duplicate run" in capsys.readouterr().out


def test_force_run_bypasses_duplicate_guard(monkeypatch, tmp_path: Path, _runtime_harness) -> None:
    today = dt.date.today().strftime("%Y%m%d")
    write_completed_runtime_log(
        tmp_path,
        filename_prefix="daily_paper_trading",
        tag=today,
        sentinel=module.COMPLETE_SENTINEL,
        timestamp="000000",
    )

    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--force-run", "--accounts", "acct_a"],
    )

    assert code == 0
    assert _runtime_harness.stream_calls
    payload = load_single_artifact_json(
        tmp_path / "local" / "exports" / "daily_paper_trading",
        "daily_paper_trading_*.json",
    )
    assert payload["status"] == "success"
    assert payload["completed_steps"]
    assert payload["step_results"]
    assert payload["step_results"][0]["step"] == "00_ingest_market_and_account"
    assert payload["step_results"][-1]["step"] == "10_emit_report_and_alerts"


def test_optional_shadow_eval_step_runs_before_auto_trader(monkeypatch, tmp_path: Path, _runtime_harness) -> None:
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
    calls = _runtime_harness.stream_calls
    assert calls
    assert calls[0][0] == "Challenger Shadow Eval"
    assert "trading.interfaces.runtime.jobs.daily.challenger_shadow_eval" in calls[0][1]
    assert "--rolling-window-days" in calls[0][1]


def test_auto_trader_runs_in_sleeve_execution_mode(monkeypatch, tmp_path: Path, _runtime_harness) -> None:
    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a", "--force-run"],
    )

    assert code == 0
    auto_trader_calls = [args for label, args in _runtime_harness.stream_calls if label.startswith("Auto Trader")]
    assert len(auto_trader_calls) == 1
    args = auto_trader_calls[0]
    mode_index = args.index("--execution-mode")
    assert args[mode_index + 1] == "sleeve"


def test_shadow_eval_summary_is_embedded_in_daily_artifact(monkeypatch, tmp_path: Path, _runtime_harness) -> None:
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

    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a", "--run-challenger-shadow-eval"],
    )

    assert code == 0
    payload = load_single_artifact_json(
        tmp_path / "local" / "exports" / "daily_paper_trading",
        "daily_paper_trading_*.json",
    )
    score_steps = [step for step in payload["step_results"] if step["step"] == "03_score_incumbent_vs_challengers"]
    assert len(score_steps) == 1
    summary = score_steps[0]["details"]["shadow_eval_summary"]
    assert summary is not None
    assert summary["account_count"] == 1
    assert summary["sleeve_count"] == 2
    assert summary["challenger_count"] == 3


def test_unknown_account_returns_1(monkeypatch, tmp_path: Path, capsys) -> None:
    set_runtime_eligible_accounts(monkeypatch, DAILY_PAPER_TRADING_MODULE, ["real_acct"])

    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "ghost_acct"],
    )

    assert code == 1
    assert "Unknown account" in capsys.readouterr().err


def test_no_accounts_returns_1(monkeypatch, tmp_path: Path, capsys, _runtime_harness) -> None:
    _runtime_harness.accounts = []

    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "all"],
    )

    assert code == 1
    assert "No accounts" in capsys.readouterr().err


def test_invalid_primary_trade_cap_returns_1(monkeypatch, tmp_path: Path, capsys, _runtime_harness) -> None:
    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a", "--primary-min-trades", "5", "--primary-max-trades", "2"],
    )

    assert code == 1
    assert "primary-max-trades" in capsys.readouterr().err


def test_invalid_shadow_eval_window_returns_1(monkeypatch, tmp_path: Path, capsys, _runtime_harness) -> None:
    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a", "--shadow-eval-rolling-window-days", "0"],
    )

    assert code == 1
    assert "shadow-eval-rolling-window-days" in capsys.readouterr().err


def test_stream_command_exception_returns_1(monkeypatch, tmp_path: Path, _runtime_harness) -> None:
    _runtime_harness.stream_error = RuntimeError("step failed")
    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a"],
    )

    assert code == 1
    payload = load_single_artifact_json(
        tmp_path / "local" / "exports" / "daily_paper_trading",
        "daily_paper_trading_*.json",
    )
    assert payload["status"] == "failed"
    assert payload["failed_step"] == "05_build_position_targets_by_sleeve"
    failed_steps = [step for step in payload["step_results"] if step["status"] == "failed"]
    assert len(failed_steps) == 1
    assert failed_steps[0]["step"] == "05_build_position_targets_by_sleeve"


def test_step_results_preserve_dag_order(monkeypatch, tmp_path: Path, _runtime_harness) -> None:
    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a"],
    )

    assert code == 0
    payload = load_single_artifact_json(
        tmp_path / "local" / "exports" / "daily_paper_trading",
        "daily_paper_trading_*.json",
    )
    ordered_steps = [step["step"] for step in payload["step_results"]]
    assert ordered_steps == [step_id for step_id, _name in module.DAILY_DAG_STEPS]


def test_success_notification_requires_flag(monkeypatch, tmp_path: Path, _runtime_harness) -> None:
    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a", "--notify-webhook-url", "https://example.test/webhook"],
    )

    assert code == 0
    assert _runtime_harness.notifications == []


def test_success_notification_sent_when_enabled(monkeypatch, tmp_path: Path, _runtime_harness) -> None:
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
    assert len(_runtime_harness.notifications) == 1
    sent = _runtime_harness.notifications[0]
    assert sent["status"] == "ok"
    assert sent["event"] == "daily-paper-trading"


def test_failure_notification_sent_when_run_fails(monkeypatch, tmp_path: Path, _runtime_harness) -> None:
    _runtime_harness.stream_error = RuntimeError("step failed")
    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a", "--notify-webhook-url", "https://example.test/webhook"],
    )

    assert code == 1
    assert len(_runtime_harness.notifications) == 1
    assert _runtime_harness.notifications[0]["status"] == "fail"
    payload = load_single_artifact_json(
        tmp_path / "local" / "exports" / "daily_paper_trading",
        "daily_paper_trading_*.json",
    )
    assert payload["status"] == "failed"
    assert payload["error"] == "step failed"


def test_step_10_operator_report_embedded_in_artifact(monkeypatch, tmp_path: Path, _runtime_harness) -> None:
    fake_report = {
        "artifact_path": "local/exports/daily_paper_trading/run.json",
        "notify_on_success": False,
        "report_date": "2026-05-07",
        "account_count": 1,
        "account_reports": [
            {
                "account_id": 1,
                "account_name": "acct_a",
                "report_date": "2026-05-07",
                "sleeve_performance": [],
                "risk_violations": {
                    "total_decisions": 0,
                    "block_count": 0,
                    "rescale_count": 0,
                    "allow_count": 0,
                    "kill_switch_triggered": False,
                    "top_reason_codes": [],
                },
                "rotation_decisions": [],
            }
        ],
    }
    monkeypatch.setattr(
        f"{DAILY_PAPER_TRADING_MODULE}._build_daily_operator_report",
        lambda *_args, **_kwargs: fake_report,
    )

    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a"],
    )

    assert code == 0
    payload = load_single_artifact_json(
        tmp_path / "local" / "exports" / "daily_paper_trading",
        "daily_paper_trading_*.json",
    )
    step_10 = next(s for s in payload["step_results"] if s["step"] == "10_emit_report_and_alerts")
    assert step_10["status"] == "ok"
    details = step_10["details"]
    assert details["report_date"] == "2026-05-07"
    assert details["account_count"] == 1
    assert len(details["account_reports"]) == 1
    assert details["account_reports"][0]["account_name"] == "acct_a"
