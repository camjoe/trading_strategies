import pytest

from tests.support.books import ensure_default_book_id, set_test_book_rotation_scheduling
from trading.repositories.rotation_decisions import RotationDecisionRepository
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.services.accounts.mutations import create_account, get_account
from trading.services.books.book_assignments import sync_default_book_assignment
from trading.services.evaluation.queries import fetch_strategy_evaluation


def _enable_rotation(conn, name: str, *, active: str) -> None:
    # Rotation is book-owned (ADR 014): enable it on the default book and make
    # sure the book's open assignment runs the requested active strategy.
    account = get_account(conn, name)
    account_id = int(account["id"])
    book_id = ensure_default_book_id(conn, account_id)
    sync_default_book_assignment(conn, account_id=account_id, strategy_name=active, now_iso="2026-01-01T00:00:00Z")
    set_test_book_rotation_scheduling(conn, book_id=book_id, enabled=1, schedule=["trend_v1", "mean_reversion"])


def _snapshot(conn, account_id: int, *, at: str, equity: float) -> None:
    EquitySnapshotRepository(conn).insert_for_book(
        book_id=ensure_default_book_id(conn, account_id),
        snapshot_time=at,
        cash=equity,
        market_value=0.0,
        equity=equity,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )


def _decision(conn, book_id: int, *, at: str, incumbent: str, selected: str) -> None:
    RotationDecisionRepository(conn).insert_for_book(
        book_id=book_id,
        decision_time=at,
        incumbent_strategy=incumbent,
        challenger_strategy=selected,
        selected_strategy=selected,
        rotation_action="rotate" if selected != incumbent else "hold",
        cooldown_active=0,
        score_components_json="{}",
        gate_results_json="{}",
        decision_reason="test",
        config_version=None,
        created_at=at,
    )


def test_fetch_strategy_evaluation_uses_closed_strategy_window_for_inactive_strategy(conn) -> None:
    create_account(conn, "acct_rotation_eval", "trend_v1", 1000.0, "SPY")
    _enable_rotation(conn, "acct_rotation_eval", active="trend_v1")
    account = get_account(conn, "acct_rotation_eval")
    book_id = ensure_default_book_id(conn, int(account["id"]))

    # mean_reversion held the book from 02-01 (rotated in) until 02-10 (rotated back to trend_v1).
    _snapshot(conn, int(account["id"]), at="2026-02-01T00:00:00Z", equity=1000.0)
    _snapshot(conn, int(account["id"]), at="2026-02-10T00:00:00Z", equity=1040.0)
    _decision(conn, book_id, at="2026-02-01T00:00:00Z", incumbent="trend_v1", selected="mean_reversion")
    _decision(conn, book_id, at="2026-02-10T00:00:00Z", incumbent="mean_reversion", selected="trend_v1")

    artifact = fetch_strategy_evaluation(
        conn,
        account_name="acct_rotation_eval",
        strategy_name="mean_reversion",
    )

    assert artifact.paper_live.available is True
    assert artifact.paper_live.source_level == "book_closed_strategy"
    assert artifact.paper_live.strategy_isolated is True
    assert artifact.paper_live.latest_equity == pytest.approx(1040.0)
    assert artifact.paper_live.return_pct == pytest.approx(4.0)


def test_fetch_strategy_evaluation_uses_active_strategy_window_from_inception(conn) -> None:
    create_account(conn, "acct_rotation_active", "trend_v1", 1000.0, "SPY")
    _enable_rotation(conn, "acct_rotation_active", active="trend_v1")
    account = get_account(conn, "acct_rotation_active")

    # No rotation yet: trend_v1 has run the book since inception (cold start).
    _snapshot(conn, int(account["id"]), at="2026-02-01T00:00:00Z", equity=1000.0)
    _snapshot(conn, int(account["id"]), at="2026-02-15T00:00:00Z", equity=1100.0)

    artifact = fetch_strategy_evaluation(
        conn,
        account_name="acct_rotation_active",
        strategy_name="trend_v1",
    )

    assert artifact.paper_live.available is True
    assert artifact.paper_live.source_level == "book_active_strategy"
    assert artifact.paper_live.strategy_isolated is True
    assert artifact.paper_live.latest_equity == pytest.approx(1100.0)
    assert artifact.paper_live.return_pct == pytest.approx(10.0)


def test_fetch_strategy_evaluation_reports_data_gaps_when_evidence_missing(conn) -> None:
    create_account(conn, "acct_eval_empty", "trend_v1", 1000.0, "SPY")

    artifact = fetch_strategy_evaluation(conn, account_name="acct_eval_empty")

    assert artifact.backtest.available is False
    assert artifact.paper_live.available is False
    assert artifact.walk_forward.available is False
    assert artifact.diagnostics.data_gaps == [
        "missing_backtest_evidence",
        "missing_paper_live_evidence",
        "missing_walk_forward_evidence",
    ]
