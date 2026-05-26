from __future__ import annotations

import json
from pathlib import Path

from trading.interfaces.runtime.jobs.daily import paper_trading_reporting as module


def test_latest_shadow_eval_summary_returns_none_when_no_artifacts(tmp_path: Path) -> None:
    assert module.latest_shadow_eval_summary(tmp_path) is None


def test_latest_shadow_eval_summary_handles_non_list_results(tmp_path: Path) -> None:
    export_dir = tmp_path / module.SHADOW_EVAL_EXPORT_DIR
    export_dir.mkdir(parents=True)
    artifact = export_dir / "daily_challenger_shadow_eval_20260327_080910.json"
    artifact.write_text(json.dumps({"status": "ok", "results": "bad"}), encoding="utf-8")

    summary = module.latest_shadow_eval_summary(tmp_path)

    assert summary == {
        "status": "ok",
        "artifact_path": str(artifact.relative_to(tmp_path)),
        "account_count": 0,
        "sleeve_count": 0,
        "challenger_count": 0,
    }


def test_latest_shadow_eval_summary_counts_valid_sleeves_and_challengers(tmp_path: Path) -> None:
    export_dir = tmp_path / module.SHADOW_EVAL_EXPORT_DIR
    export_dir.mkdir(parents=True)
    artifact = export_dir / "daily_challenger_shadow_eval_20260327_080910.json"
    artifact.write_text(
        json.dumps(
            {
                "status": "ok",
                "results": [
                    {"sleeves": [{"challenger_count": 2}, {"challenger_count": 0}, "bad"]},
                    {"sleeves": "not-a-list"},
                    "not-a-dict",
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = module.latest_shadow_eval_summary(tmp_path)

    assert summary == {
        "status": "ok",
        "artifact_path": str(artifact.relative_to(tmp_path)),
        "account_count": 3,
        "sleeve_count": 3,
        "challenger_count": 2,
    }


def test_build_daily_operator_report_skips_missing_accounts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        module.dt,
        "date",
        type("FakeDate", (), {"today": classmethod(lambda cls: cls()), "isoformat": lambda self: "2026-03-27"}),
    )
    monkeypatch.setattr(module, "ensure_db", lambda: object())
    monkeypatch.setattr(
        module,
        "fetch_account_by_name",
        lambda _conn, account_name: {"id": 7} if account_name == "acct1" else None,
    )
    monkeypatch.setattr(
        module,
        "build_account_daily_report",
        lambda _conn, *, account_id, account_name, report_date: {
            "account_id": account_id,
            "account_name": account_name,
            "report_date": report_date,
        },
    )
    monkeypatch.setattr(module, "account_daily_report_as_dict", lambda report: report)

    report = module.build_daily_operator_report(
        accounts=["acct1", "missing"],
        artifact_path=tmp_path / "reports" / "daily.json",
        repo_root=tmp_path,
        notify_on_success=True,
    )

    assert report == {
        "artifact_path": "reports/daily.json",
        "notify_on_success": True,
        "report_date": "2026-03-27",
        "account_count": 1,
        "account_reports": [{"account_id": 7, "account_name": "acct1", "report_date": "2026-03-27"}],
    }


def test_maybe_send_notification_skips_success_when_notifications_disabled() -> None:
    calls: list[dict[str, object]] = []

    module.maybe_send_notification(
        notifier=lambda **kwargs: calls.append(kwargs),
        webhook_url="https://example.invalid",
        notify_on_success=False,
        status="ok",
        message="done",
        details={"count": 1},
    )

    assert calls == []


def test_maybe_send_notification_calls_notifier_for_errors() -> None:
    calls: list[dict[str, object]] = []

    module.maybe_send_notification(
        notifier=lambda **kwargs: calls.append(kwargs),
        webhook_url="https://example.invalid",
        notify_on_success=False,
        status="error",
        message="failed",
        details={"count": 1},
    )

    assert calls == [
        {
            "webhook_url": "https://example.invalid",
            "event": "daily-paper-trading",
            "status": "error",
            "message": "failed",
            "details": {"count": 1},
        }
    ]
