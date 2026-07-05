from __future__ import annotations

import pytest

from trading.repositories.daily_metrics import DailyMetricsRepository
from trading.repositories.portfolio_risk_snapshots import PortfolioRiskSnapshotRepository
from trading.repositories.rotation_decisions import RotationDecisionRepository
from trading.repositories.sleeve_risk_decisions import SleeveRiskDecisionRepository
from trading.repositories.sleeves import SleeveRepository
from trading.services.sleeves.daily_report import (
    AccountDailyReport,
    account_daily_report_as_dict,
    build_account_daily_report,
)
from tests.support.repositories import insert_repository_account

REPORT_DATE = "2026-05-07"


def test_build_report_returns_correct_structure(conn, report_env) -> None:
    SleeveRepository(conn).insert_assignment(
        sleeve_id=report_env.sleeve_id,
        strategy_name="Momentum",
        param_set_id=None,
        effective_from="2026-01-01T00:00:00Z",
        effective_to=None,
        is_incumbent=1,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    DailyMetricsRepository(conn).upsert(
        account_id=report_env.account_id,
        sleeve_id=report_env.sleeve_id,
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
    assert len(report.sleeve_performance) == 1
    sp = report.sleeve_performance[0]
    assert sp.sleeve_id == report_env.sleeve_id
    assert sp.strategy_name == "Momentum"
    assert sp.return_pct == pytest.approx(1.5)
    assert sp.drawdown_pct == pytest.approx(-0.3)
    assert sp.hit_rate == pytest.approx(0.6)
    assert sp.trade_count == 4


def test_build_report_no_sleeves_returns_empty_sections(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_no_sleeves")

    report = build_account_daily_report(
        conn, account_id=account_id, account_name="acct_no_sleeves", report_date=REPORT_DATE
    )

    assert report.sleeve_performance == []
    assert report.rotation_decisions == []
    assert report.risk_violations.total_decisions == 0


def test_build_report_sleeve_with_no_metric_returns_none_fields(conn, report_env) -> None:
    report = build_account_daily_report(
        conn, account_id=report_env.account_id, account_name=report_env.account_name, report_date=REPORT_DATE
    )

    assert len(report.sleeve_performance) == 1
    sp = report.sleeve_performance[0]
    assert sp.return_pct is None
    assert sp.trade_count is None
    assert sp.strategy_name is None


def test_build_report_risk_violations_counts(conn, report_env) -> None:
    for action, reason in [
        ("block", "sleeve_notional_cap"),
        ("block", "sleeve_notional_cap"),
        ("rescale", "symbol_concentration_cap"),
        ("allow", "ok"),
    ]:
        SleeveRiskDecisionRepository(conn).insert(
            account_id=report_env.account_id,
            sleeve_id=report_env.sleeve_id,
            decision_time=f"{REPORT_DATE}T10:00:00Z",
            symbol="AAPL",
            side="buy",
            action=action,
            reason_code=reason,
            requested_qty=100,
            approved_qty=80,
            requested_notional=5000.0,
            approved_notional=4000.0,
            execution_mode="sleeve",
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
    assert "sleeve_notional_cap" in rv.top_reason_codes
    assert rv.top_reason_codes[0] == "sleeve_notional_cap"


def test_build_report_risk_violations_excludes_other_dates(conn, report_env) -> None:
    SleeveRiskDecisionRepository(conn).insert(
        account_id=report_env.account_id,
        sleeve_id=report_env.sleeve_id,
        decision_time="2026-05-06T10:00:00Z",  # different date
        symbol="AAPL",
        side="buy",
        action="block",
        reason_code="sleeve_notional_cap",
        requested_qty=100,
        approved_qty=0,
        requested_notional=5000.0,
        approved_notional=0.0,
        execution_mode="sleeve",
        risk_payload_json="{}",
        created_at="2026-05-06T10:00:00Z",
    )

    report = build_account_daily_report(
        conn, account_id=report_env.account_id, account_name=report_env.account_name, report_date=REPORT_DATE
    )

    assert report.risk_violations.total_decisions == 0


def test_build_report_kill_switch_from_snapshot(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_ks")
    PortfolioRiskSnapshotRepository(conn).upsert(
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
    RotationDecisionRepository(conn).insert(
        sleeve_id=report_env.sleeve_id,
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
        param_set_id=None,
        created_at=f"{REPORT_DATE}T09:00:00Z",
    )
    # Decision on a different date — should be excluded
    RotationDecisionRepository(conn).insert(
        sleeve_id=report_env.sleeve_id,
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
        param_set_id=None,
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
    assert "sleeve_performance" in d
    assert "risk_violations" in d
    assert "rotation_decisions" in d
    rv = d["risk_violations"]
    assert "total_decisions" in rv
    assert "kill_switch_triggered" in rv
    assert "top_reason_codes" in rv
