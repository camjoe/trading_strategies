from __future__ import annotations

import pytest

from trading.repositories.books import BookRepository
from trading.repositories.daily_metrics import DailyMetricsRepository
from trading.repositories.rotation_decisions import RotationDecisionRepository
from trading.repositories.risk import RiskDecisionRepository, RiskSnapshotRepository
from trading.services.books.daily_report import (
    AccountDailyReport,
    account_daily_report_as_dict,
    build_account_daily_report,
)
from tests.support.repositories import insert_repository_account
from tests.support.books import assign_test_book_strategy

REPORT_DATE = "2026-05-07"


def test_build_report_returns_correct_structure(conn, report_env) -> None:
    assign_test_book_strategy(conn, book_id=report_env.book_id, strategy_name="Momentum")
    DailyMetricsRepository(conn).upsert(
        account_id=report_env.account_id,
        book_id=report_env.book_id,
        metric_date=REPORT_DATE,
        return_pct=1.5,
        drawdown_pct=-0.3,
        turnover_pct=10.0,
        slippage_bps=2.0,
        hit_rate=0.6,
        expectancy=0.8,
        risk_adjusted_score=1.2,
        trade_count=4,
        fees_total=3.0,
        created_at="2026-05-07T20:00:00Z",
        updated_at="2026-05-07T20:00:00Z",
    )

    report = build_account_daily_report(
        conn, account_id=report_env.account_id, account_name=report_env.account_name, report_date=REPORT_DATE
    )

    assert isinstance(report, AccountDailyReport)
    assert report.account_id == report_env.account_id
    assert report.account_name == report_env.account_name
    assert report.report_date == REPORT_DATE
    assert len(report.book_performance) == 1
    sp = report.book_performance[0]
    assert sp.book_id == report_env.book_id
    # Labels round-trip through the strategies catalog as canonical lowercase keys (P3).
    assert sp.strategy_name == "momentum"
    assert sp.return_pct == pytest.approx(1.5)
    assert sp.drawdown_pct == pytest.approx(-0.3)
    assert sp.hit_rate == pytest.approx(0.6)
    assert sp.trade_count == 4


def test_book_performance_current_equity_comes_from_book(conn, report_env) -> None:
    # The report reads live equity straight from the book balance.
    BookRepository(conn).update_balances(
        book_id=report_env.book_id,
        current_cash=8_000.0,
        current_equity=12_345.0,
        updated_at="2026-05-07T00:00:00Z",
    )

    report = build_account_daily_report(
        conn, account_id=report_env.account_id, account_name=report_env.account_name, report_date=REPORT_DATE
    )

    assert report.book_performance[0].current_equity == pytest.approx(12_345.0)


def test_build_report_no_books_returns_empty_sections(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_no_books")

    report = build_account_daily_report(
        conn, account_id=account_id, account_name="acct_no_books", report_date=REPORT_DATE
    )

    assert report.book_performance == []
    assert report.rotation_decisions == []
    assert report.risk_violations.total_decisions == 0


def test_build_report_book_with_no_metric_returns_none_fields(conn, report_env) -> None:
    report = build_account_daily_report(
        conn, account_id=report_env.account_id, account_name=report_env.account_name, report_date=REPORT_DATE
    )

    assert len(report.book_performance) == 1
    sp = report.book_performance[0]
    assert sp.return_pct is None
    assert sp.trade_count is None
    assert sp.strategy_name is None


def test_build_report_risk_violations_counts(conn, report_env) -> None:
    for action, reason in [
        ("block", "book_notional_cap"),
        ("block", "book_notional_cap"),
        ("rescale", "symbol_concentration_cap"),
        ("allow", "ok"),
    ]:
        RiskDecisionRepository(conn).insert(
            account_id=report_env.account_id,
            book_id=None,
            decision_time=f"{REPORT_DATE}T10:00:00Z",
            symbol="AAPL",
            side="buy",
            action=action,
            reason_code=reason,
            requested_qty=100,
            approved_qty=80,
            requested_notional=5000.0,
            approved_notional=4000.0,
            risk_payload_json="{}",
            created_at=f"{REPORT_DATE}T10:00:00Z",
        )

    report = build_account_daily_report(
        conn, account_id=report_env.account_id, account_name=report_env.account_name, report_date=REPORT_DATE
    )

    rv = report.risk_violations
    assert rv.total_decisions == 4
    assert rv.block_count == 2
    assert rv.rescale_count == 1
    assert rv.allow_count == 1
    assert "book_notional_cap" in rv.top_reason_codes
    assert rv.top_reason_codes[0] == "book_notional_cap"


def test_build_report_risk_violations_excludes_other_dates(conn, report_env) -> None:
    RiskDecisionRepository(conn).insert(
        account_id=report_env.account_id,
        book_id=None,
        decision_time="2026-05-06T10:00:00Z",  # different date
        symbol="AAPL",
        side="buy",
        action="block",
        reason_code="book_notional_cap",
        requested_qty=100,
        approved_qty=0,
        requested_notional=5000.0,
        approved_notional=0.0,
        risk_payload_json="{}",
        created_at="2026-05-06T10:00:00Z",
    )

    report = build_account_daily_report(
        conn, account_id=report_env.account_id, account_name=report_env.account_name, report_date=REPORT_DATE
    )

    assert report.risk_violations.total_decisions == 0


def test_build_report_kill_switch_from_snapshot(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_ks")
    RiskSnapshotRepository(conn).insert(
        account_id=account_id,
        snapshot_time=f"{REPORT_DATE}T15:00:00Z",
        gross_exposure=50000.0,
        net_exposure=45000.0,
        max_symbol_concentration_pct=10.0,
        max_sector_concentration_pct=20.0,
        drawdown_pct=-2.0,
        leverage_proxy=1.0,
        daily_loss_pct=-0.5,
        kill_switch_triggered=1,
        risk_payload_json="{}",
    )

    report = build_account_daily_report(conn, account_id=account_id, account_name="acct_ks", report_date=REPORT_DATE)

    assert report.risk_violations.kill_switch_triggered is True


def test_build_report_rotation_decisions(conn, report_env) -> None:
    RotationDecisionRepository(conn).insert_for_book(
        book_id=report_env.book_id,
        decision_time=f"{REPORT_DATE}T09:00:00Z",
        incumbent_strategy="Momentum",
        challenger_strategy="MeanRev",
        selected_strategy="MeanRev",
        rotation_action="rotate",
        cooldown_active=0,
        score_components_json="{}",
        gate_results_json="{}",
        decision_reason="challenger outperformed",
        config_version="v1",
        created_at=f"{REPORT_DATE}T09:00:00Z",
    )
    # Decision on a different date — should be excluded
    RotationDecisionRepository(conn).insert_for_book(
        book_id=report_env.book_id,
        decision_time="2026-05-06T09:00:00Z",
        incumbent_strategy="Momentum",
        challenger_strategy="MeanRev",
        selected_strategy="Momentum",
        rotation_action="hold",
        cooldown_active=0,
        score_components_json="{}",
        gate_results_json="{}",
        decision_reason=None,
        config_version="v1",
        created_at="2026-05-06T09:00:00Z",
    )

    report = build_account_daily_report(
        conn, account_id=report_env.account_id, account_name=report_env.account_name, report_date=REPORT_DATE
    )

    assert len(report.rotation_decisions) == 1
    rd = report.rotation_decisions[0]
    assert rd.rotation_action == "rotate"
    # Labels round-trip through the strategies catalog as canonical lowercase keys (P3).
    assert rd.incumbent_strategy == "momentum"
    assert rd.challenger_strategy == "meanrev"
    assert rd.decision_reason == "challenger outperformed"


def test_account_daily_report_as_dict_shape(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_dict")

    report = build_account_daily_report(conn, account_id=account_id, account_name="acct_dict", report_date=REPORT_DATE)
    d = account_daily_report_as_dict(report)

    assert d["account_id"] == account_id
    assert d["account_name"] == "acct_dict"
    assert d["report_date"] == REPORT_DATE
    assert "book_performance" in d
    assert "risk_violations" in d
    assert "rotation_decisions" in d
    rv = d["risk_violations"]
    assert "total_decisions" in rv
    assert "kill_switch_triggered" in rv
    assert "top_reason_codes" in rv
