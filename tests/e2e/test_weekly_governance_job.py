"""End-to-end test for the W1 weekly governance leaderboard job.

Covers the governance half of the "runtime scheduler jobs" capability from
``docs/overview.md``, which the doc compresses into a single bullet. The daily
paper-trading job proves the daily runtime; this proves the governance runtime.
The W1 job runs through its ``main`` entrypoint against a real database, ranks a
book by its persisted daily metrics, and writes its artifact to disk — real
account resolution, book listing, performance window, and artifact write.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

import trading.interfaces.runtime.jobs.governance.weekly.w1_leaderboard as job
from infrastructure.database.backend import SQLiteBackend, use_backend
from infrastructure.database.connection import ensure_db
from tests.support.books import assign_test_book_strategy, insert_test_book
from tests.support.db_schema import build_db_at_head
from trading.repositories.daily_metrics import DailyMetricsRepository
from trading.services.accounts.mutations import create_account


def _seed_account_with_metrics(db_path: Path) -> None:
    with use_backend(SQLiteBackend(db_path)):
        conn = ensure_db()
        try:
            create_account(conn, "acct_gov", "trend", 10_000.0, "SPY")
            account_id = conn.execute("SELECT id FROM accounts WHERE name = 'acct_gov'").fetchone()[0]
            # The governance leaderboard reports non-default books, so seed one.
            book_id = insert_test_book(conn, account_id=account_id, name="core")
            assign_test_book_strategy(conn, book_id=book_id, strategy_name="trend")
            today = dt.date.today()
            # Two metric rows inside the default 30-day window.
            for offset in (0, 1):
                day = (today - dt.timedelta(days=offset)).isoformat()
                DailyMetricsRepository(conn).upsert(
                    book_id=book_id,
                    metric_date=day,
                    return_pct=0.5,
                    drawdown_pct=-0.7,
                    turnover_pct=2.0,
                    slippage_bps=8.0,
                    hit_rate=0.45,
                    expectancy=0.08,
                    risk_adjusted_score=0.6,
                    trade_count=10,
                    fees_total=3.0,
                    created_at=f"{day}T00:00:00Z",
                    updated_at=f"{day}T00:00:00Z",
                )
            conn.commit()
        finally:
            conn.close()


def test_weekly_leaderboard_job_ranks_a_book_over_real_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = build_db_at_head(tmp_path / "gov.db")
    (tmp_path / "local" / "logs").mkdir(parents=True, exist_ok=True)
    _seed_account_with_metrics(db_path)

    with use_backend(SQLiteBackend(db_path)):
        monkeypatch.setattr(
            sys,
            "argv",
            ["w1_leaderboard", "--accounts", "all", "--repo-root", str(tmp_path), "--force-run"],
        )
        exit_code = job.main()

    assert exit_code == 0

    artifacts = list((tmp_path / "local" / "artifacts").glob("weekly_governance_w1_leaderboard_*.json"))
    assert len(artifacts) == 1
    payload = json.loads(artifacts[0].read_text(encoding="utf-8"))

    accounts = payload["accounts"]
    assert len(accounts) == 1
    assert accounts[0]["account_name"] == "acct_gov"

    books = accounts[0]["books"]
    assert len(books) == 1
    assert books[0]["rank"] == 1
    assert books[0]["strategy_name"] == "trend"
    assert books[0]["data_points"] == 2
    assert books[0]["avg_risk_adjusted_score"] is not None
