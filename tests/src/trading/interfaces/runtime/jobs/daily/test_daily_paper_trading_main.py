from __future__ import annotations

import datetime as dt
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

import trading.interfaces.runtime.jobs.daily.paper_trading.dag as dag_module
import trading.interfaces.runtime.jobs.daily.paper_trading.workflow as workflow_module
import trading.services.autonomy_monitor.artifacts as monitor_artifacts
from tests.src.trading.interfaces.helpers import run_module_as_main
from tests.src.trading.interfaces.runtime.jobs.loaders import (
    DAILY_PAPER_TRADING_MODULE,
    daily_paper_trading as module,
    load_single_artifact_json,
    run_runtime_job_main,
    set_runtime_eligible_accounts,
    write_completed_runtime_log,
)

WORKFLOW_MODULE = f"{DAILY_PAPER_TRADING_MODULE}.workflow"

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
        f"{WORKFLOW_MODULE}._build_daily_operator_report",
        lambda *_args, **_kwargs: dict(_STUB_OPERATOR_REPORT),
    )


@pytest.fixture
def _runtime_harness(monkeypatch, conn):
    """Stub the subprocess/notification surface and isolate the DB.

    Steps 06/07 (risk gate, submission summary) call ``ensure_db()`` for real —
    they are not routed through the stubbed ``stream_command``. Without ``conn``
    swapping the backend, they would silently open whatever ``local/paper_trading.db``
    happens to exist on disk: migrated and populated on a dev machine, absent (and
    then created empty) on a clean CI checkout, where every one of these tests
    would fail with a schema-revision mismatch instead of running against an
    isolated, empty, head-migrated database.
    """

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
    monkeypatch.setattr(f"{WORKFLOW_MODULE}.stream_command", _stream)
    # Snapshots retry with backoff; keep the failure paths from actually sleeping.
    monkeypatch.setattr(f"{WORKFLOW_MODULE}.SNAPSHOT_BACKOFF_SECONDS", 0)
    monkeypatch.setattr(
        f"{WORKFLOW_MODULE}.notify_runtime_event",
        lambda **kwargs: state.notifications.append(kwargs) or True,
    )
    return state


def test_run_skips_when_today_already_has_a_successful_run(monkeypatch, tmp_path: Path, _runtime_harness) -> None:
    # A second pass is a second full trading pass, not a no-op — step 05 submits a
    # fresh round of orders against a fresh per-run cap. The guard is what stops it.
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
        ["--accounts", "acct_a"],
    )

    assert code == 0
    # Nothing ran: no subprocess was streamed and no artifact was written. Exiting
    # 0 keeps a scheduler from treating an intentional skip as a failure.
    assert not _runtime_harness.stream_calls
    export_dir = tmp_path / "local" / "exports" / "daily_paper_trading"
    assert not list(export_dir.glob("daily_paper_trading_*.json"))


def test_force_run_overrides_the_duplicate_guard(monkeypatch, tmp_path: Path, _runtime_harness) -> None:
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
        ["--accounts", "acct_a", "--force-run"],
    )

    assert code == 0
    assert _runtime_harness.stream_calls
    payload = load_single_artifact_json(
        tmp_path / "local" / "exports" / "daily_paper_trading",
        "daily_paper_trading_*.json",
    )
    assert payload["status"] == "success"
    # Recorded so a run that traded a date twice says so in its own artifact.
    assert payload["force_run"] is True
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
    labels = [label for label, _ in calls]
    shadow_index = labels.index("Challenger Shadow Eval")
    assert shadow_index < labels.index("Auto Trader (up to 11 trades)")
    shadow_args = calls[shadow_index][1]
    assert "trading.interfaces.runtime.jobs.daily.challenger_shadow_eval" in shadow_args
    # An explicit operator window is forwarded to the shadow-eval job.
    window_index = shadow_args.index("--rolling-window-days")
    assert shadow_args[window_index + 1] == "45"


def test_shadow_eval_defaults_to_book_owned_window(monkeypatch, tmp_path: Path, _runtime_harness) -> None:
    # Without an operator override the flag is omitted, so each book's own
    # configured lookback drives the shadow evaluation (ADR 014).
    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a", "--run-challenger-shadow-eval"],
    )

    assert code == 0
    shadow_calls = [args for label, args in _runtime_harness.stream_calls if label == "Challenger Shadow Eval"]
    assert len(shadow_calls) == 1
    assert "--rolling-window-days" not in shadow_calls[0]


def test_pre_trade_snapshot_runs_before_the_auto_trader(monkeypatch, tmp_path: Path, _runtime_harness) -> None:
    # The pre-submit gate kills the run when the equity snapshot is missing or
    # stale, so the run has to take its own snapshot before trading.
    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a"],
    )

    assert code == 0
    labels = [label for label, _ in _runtime_harness.stream_calls]
    trader_index = labels.index("Auto Trader (up to 11 trades)")
    assert labels.index("Pre-trade snapshot acct_a") < trader_index
    # The post-trade pass still records end-state equity.
    assert trader_index < labels.index("Post-trade snapshot acct_a")


def test_broker_fills_are_reconciled_before_each_snapshot(monkeypatch, tmp_path: Path, _runtime_harness) -> None:
    # Async brokers (the IBKR socket path) report fills after submission, so each
    # snapshot has to be preceded by a reconciliation pass or the recorded equity
    # ignores those fills. Paper accounts make this a no-op.
    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a"],
    )

    assert code == 0
    calls = _runtime_harness.stream_calls
    labels = [label for label, _ in calls]
    assert labels.index("Pre-trade reconcile fills") < labels.index("Pre-trade snapshot acct_a")
    assert labels.index("Post-trade reconcile fills") < labels.index("Post-trade snapshot acct_a")
    reconcile_args = calls[labels.index("Pre-trade reconcile fills")][1]
    assert "trading.interfaces.runtime.jobs.daily.paper_trading.reconcile_orders" in reconcile_args
    assert reconcile_args[reconcile_args.index("--accounts") + 1] == "acct_a"


def test_auto_trader_argv_has_no_execution_mode_flag(monkeypatch, tmp_path: Path, _runtime_harness) -> None:
    # The execution-mode collapse (ADR 014): one path, no flag.
    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a"],
    )

    assert code == 0
    auto_trader_calls = [args for label, args in _runtime_harness.stream_calls if label.startswith("Auto Trader")]
    assert len(auto_trader_calls) == 1
    assert "--execution-mode" not in auto_trader_calls[0]


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
                        "books": [
                            {"book_id": 1, "challenger_count": 2},
                            {"book_id": 2, "challenger_count": 1},
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
    assert summary["book_count"] == 2
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
        ["--accounts", "acct_a", "--primary-max-trades", "0"],
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
    # The pre-trade snapshot is the run's first streamed command, so it is where
    # a blanket command failure surfaces.
    assert payload["failed_step"] == "01_mark_book_nav"
    failed_steps = [step for step in payload["step_results"] if step["status"] == "failed"]
    assert len(failed_steps) == 1
    assert failed_steps[0]["step"] == "01_mark_book_nav"


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
    assert ordered_steps == [step_id for step_id, _name in dag_module.DAILY_DAG_STEPS]


def test_risk_gate_and_submission_steps_report_instead_of_skipping(
    monkeypatch, tmp_path: Path, _runtime_harness
) -> None:
    """Steps 06 and 07 must record what the runtime did, not skip.

    They are the run's only account of what the risk gate blocked and what
    reached the broker — exactly the part worth reading once orders are real.
    """
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
    steps = {step["step"]: step for step in payload["step_results"]}

    assert steps["06_pretrade_risk_gate"]["status"] == "ok"
    assert steps["07_submit_ibkr_orders"]["status"] == "ok"
    assert "total_decisions" in steps["06_pretrade_risk_gate"]["details"]
    assert "order_count" in steps["07_submit_ibkr_orders"]["details"]


def test_run_artifact_is_readable_by_the_autonomy_monitor(monkeypatch, tmp_path: Path, _runtime_harness) -> None:
    """Contract guard: the monitor must read what the workflow actually writes.

    These two drifted apart once already — the reader looked for keys and paths
    no producer emitted, and its own tests passed because they asserted against
    invented fixtures. Feed a genuine run artifact through the real reader.
    """
    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a"],
    )
    assert code == 0

    status = monitor_artifacts.fetch_daily_workflow_status(repo_root=tmp_path)

    assert status["status"] == "success"
    assert status["latest_run_time"] is not None
    assert status["completed_steps"] == len(dag_module.DAILY_DAG_STEPS)
    assert status["failed_step"] is None


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
                "book_performance": [],
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
        f"{WORKFLOW_MODULE}._build_daily_operator_report",
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


def test_startup_log_swallows_os_errors(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "open", lambda *_a, **_kw: (_ for _ in ()).throw(OSError("boom")))

    module._startup_log("hello", tmp_path)


def test_run_auto_trader_group_skips_empty_groups(monkeypatch, tmp_path: Path) -> None:
    stream = pytest.MonkeyPatch()
    try:
        called: list[tuple[str, list[str]]] = []
        stream.setattr(
            workflow_module, "stream_command", lambda log_path, label, args, repo_root: called.append((label, args))
        )
        workflow_module.run_auto_trader_group(tmp_path / "run.log", tmp_path, "Auto Trader", [], 5, 0.0, None)
    finally:
        stream.undo()

    assert called == []


def test_run_auto_trader_group_includes_seed_when_present(monkeypatch, tmp_path: Path) -> None:
    called: list[list[str]] = []
    monkeypatch.setattr(workflow_module, "stream_command", lambda _log, _label, args, _root: called.append(args))

    workflow_module.run_auto_trader_group(tmp_path / "run.log", tmp_path, "Auto Trader", ["acct_a"], 5, 0.0, 7)

    assert "--seed" in called[0]
    assert called[0][called[0].index("--seed") + 1] == "7"


def test_main_validates_other_trade_ranges(monkeypatch, tmp_path: Path, capsys, _runtime_harness) -> None:
    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a", "--other-max-trades", "0"],
    )
    assert code == 1
    assert "other-max-trades" in capsys.readouterr().err


def test_main_rejects_invalid_account_trade_caps_override(
    monkeypatch, tmp_path: Path, capsys, _runtime_harness
) -> None:
    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a", "--account-trade-caps", "acct_a"],
    )

    assert code == 1
    assert "account:max" in capsys.readouterr().err


def test_main_rejects_unknown_account_trade_cap_overrides(
    monkeypatch, tmp_path: Path, capsys, _runtime_harness
) -> None:
    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a", "--account-trade-caps", "ghost:2"],
    )

    assert code == 1
    assert "Unknown account(s) in --account-trade-caps: ghost" in capsys.readouterr().err


def test_paper_trading_module_import_logs_account_import_failures(monkeypatch, tmp_path: Path) -> None:
    import builtins

    import common.git as git_module

    original_import = builtins.__import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "trading.services.accounts" and "load_runtime_eligible_account_names" in fromlist:
            raise ImportError("boom")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(git_module, "get_repo_root", lambda _file: tmp_path)
    monkeypatch.setattr(builtins, "__import__", _fake_import)

    with pytest.raises(ImportError, match="boom"):
        run_module_as_main(module.__name__)


def test_paper_trading_module_main_entrypoint(monkeypatch, tmp_path: Path, _runtime_harness) -> None:
    # Run the package's __main__ shim (not the package itself): popping/re-executing
    # the package __init__ via runpy would corrupt the shared module object for
    # sibling tests. _runtime_harness keeps get_backend() off the real on-disk database.
    monkeypatch.setattr(
        sys,
        "argv",
        ["daily_paper_trading", "--accounts", "acct_a", "--primary-max-trades", "0", "--repo-root", str(tmp_path)],
    )

    with pytest.raises(SystemExit) as excinfo:
        run_module_as_main(module.__name__ + ".__main__")

    assert excinfo.value.code == 1


def test_replay_reports_the_replayed_date_not_today(monkeypatch, tmp_path: Path, _runtime_harness) -> None:
    """A --as-of-date replay must report that date's rows, not today's.

    Steps 06/07/10 all read persisted rows for a date. Resolving that date once
    on the run context is what keeps them from each calling date.today() and
    putting a different date in the same artifact.
    """
    # Each of these takes the report date as its last positional argument.
    seen: dict[str, str] = {}

    def _record(name):
        def _stub(*args, **_kwargs) -> dict[str, object]:
            seen[name] = args[-1]
            return {}

        return _stub

    for step_fn in ("_risk_gate_step_result", "_submission_step_result", "_build_daily_operator_report"):
        monkeypatch.setattr(f"{WORKFLOW_MODULE}.{step_fn}", _record(step_fn))

    code = run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct_a", "--as-of-date", "2026-03-27"],
    )

    assert code == 0
    payload = load_single_artifact_json(
        tmp_path / "local" / "exports" / "daily_paper_trading",
        "daily_paper_trading_*.json",
    )
    assert payload["as_of_date"] == "2026-03-27"
    assert payload["report_date"] == "2026-03-27"

    # Every step that reads rows for a date got the replayed date, not today's.
    assert seen == {
        "_risk_gate_step_result": "2026-03-27",
        "_submission_step_result": "2026-03-27",
        "_build_daily_operator_report": "2026-03-27",
    }
