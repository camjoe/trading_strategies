from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

from paper_trading_ui.backend.services import operations as services_operations
from paper_trading_ui.backend.services import promotion as services_promotion


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_list_operations_overview_reports_jobs_and_artifacts(tmp_path, monkeypatch) -> None:
    logs_dir = tmp_path / "logs"
    exports_dir = tmp_path / "exports"
    backups_dir = tmp_path / "local" / "db_backups"
    today = dt.date.today()
    today_tag = today.strftime("%Y%m%d")
    week_tag = f"{today.isocalendar().year}_W{today.isocalendar().week:02d}"

    _write(
        logs_dir / f"daily_paper_trading_{today_tag}_131001.log",
        f"header\n{services_operations.DAILY_PAPER_TRADING_SENTINEL}\n",
    )
    _write(logs_dir / f"daily_snapshot_{today_tag}_131500.log", "started only\n")
    _write(
        logs_dir / f"weekly_db_backup_{week_tag}_090000.log",
        f"header\n{services_operations.WEEKLY_DB_BACKUP_SENTINEL}\n",
    )
    _write(
        exports_dir / "scheduled_backtest_refresh" / f"scheduled_backtest_refresh_{today_tag}_131800.json",
        "{}\n",
    )
    _write(
        exports_dir / "daily_snapshots" / f"daily_snapshot_{today_tag}_132000.json",
        "{}\n",
    )
    _write(backups_dir / f"paper_trading_{today_tag}_133000.db", "db")

    monkeypatch.setattr(services_operations, "LOGS_DIR", logs_dir)
    monkeypatch.setattr(services_operations, "EXPORTS_DIR", exports_dir)
    monkeypatch.setattr(services_operations, "ROOT_DIR", tmp_path)

    payload = services_operations.list_operations_overview()

    assert payload["scheduledRefreshArtifacts"][0]["name"].endswith(".json")
    assert payload["dailySnapshotArtifacts"][0]["name"].endswith(".json")
    assert payload["databaseBackups"][0]["name"].endswith(".db")

    jobs = {job["key"]: job for job in payload["jobs"]}
    assert jobs["daily_paper_trading"]["status"] == "ok"
    assert jobs["daily_snapshot"]["status"] == "warning"
    assert jobs["scheduled_backtest_refresh"]["status"] == "missing"
    assert jobs["weekly_db_backup"]["status"] == "ok"


class _FakePayload:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def to_payload(self) -> dict[str, object]:
        return dict(self._payload)


class _FakeHistoryEntry:
    def __init__(self) -> None:
        self.review = _FakePayload(
            {
                "id": 1,
                "review_state": "requested",
                "strategy_name": "trend",
            }
        )
        self.events = [_FakePayload({"id": 11, "event_type": "requested"})]


def test_build_promotion_overview_serializes_assessment_and_history(monkeypatch) -> None:
    monkeypatch.setattr(
        services_promotion,
        "fetch_current_promotion_assessment",
        lambda *_args, **_kwargs: _FakePayload(
            {
                "account_name": "acct_ops",
                "strategy_name": "trend",
                "stage": "promotion_review",
                "status": "ready_for_review",
                "ready_for_live": True,
                "live_trading_enabled": False,
                "overall_confidence": 0.9,
                "data_gaps": [],
                "blockers": [],
                "warnings": [],
                "next_action": "Approve review",
                "evaluation_generated_at": "2026-04-17T13:15:00Z",
            }
        ),
    )
    monkeypatch.setattr(
        services_promotion,
        "fetch_promotion_review_history",
        lambda *_args, **_kwargs: [_FakeHistoryEntry()],
    )

    payload = services_promotion.build_promotion_overview(
        sqlite3.connect(":memory:"),
        account_name="acct_ops",
        strategy_name=" trend ",
        limit=3,
    )

    assert payload["assessment"]["account_name"] == "acct_ops"
    assert payload["history"][0]["review"]["review_state"] == "requested"
    assert payload["history"][0]["events"][0]["event_type"] == "requested"
