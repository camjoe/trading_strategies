"""Coverage for the daily DAG's step 06 / step 07 summaries.

Both read rows the auto-trading runtime already wrote. The cases that matter are
the ones the paper simulator can never produce: blocked orders and broker
rejections.
"""

from __future__ import annotations

from trading.models.books import RiskDecisionInsert
from trading.models.orders import OrderInsert
from trading.repositories.orders import OrderRepository
from trading.repositories.risk import RiskDecisionRepository
from trading.services.analysis.daily_report import build_risk_gate_summary, build_submission_summary

REPORT_DATE = "2026-05-07"
OTHER_DATE = "2026-05-06"


def _insert_decision(conn, report_env, *, action: str, reason_code: str, date: str = REPORT_DATE) -> None:
    RiskDecisionRepository(conn).insert(
        RiskDecisionInsert(
            account_id=report_env.account_id,
            book_id=report_env.book_id,
            decision_time=f"{date}T14:30:00Z",
            symbol="AAPL",
            side="buy",
            action=action,
            reason_code=reason_code,
            created_at=f"{date}T14:30:00Z",
        )
    )


def _insert_order(conn, report_env, *, status: str, broker_order_id=None, status_reason=None, date=REPORT_DATE) -> int:
    return OrderRepository(conn).insert(
        OrderInsert(
            book_id=report_env.book_id,
            account_id=report_env.account_id,
            broker_order_id=broker_order_id,
            symbol="AAPL",
            side="buy",
            qty=10.0,
            status=status,
            submitted_at=f"{date}T14:31:00Z",
            updated_at=f"{date}T14:31:00Z",
            status_reason=status_reason,
        )
    )


class TestRiskGateSummary:
    def test_counts_decisions_by_action(self, conn, report_env) -> None:
        _insert_decision(conn, report_env, action="block", reason_code="max_notional_exceeded")
        _insert_decision(conn, report_env, action="rescale", reason_code="position_cap")
        _insert_decision(conn, report_env, action="allow", reason_code="ok")

        summary = build_risk_gate_summary(conn, accounts=[report_env.account_name], report_date=REPORT_DATE)

        assert summary["total_decisions"] == 3
        assert summary["blocked"] == 1
        assert summary["rescaled"] == 1
        assert summary["kill_switch_accounts"] == []
        assert summary["accounts"][0]["account"] == report_env.account_name
        assert "max_notional_exceeded" in summary["accounts"][0]["top_reason_codes"]

    def test_ignores_other_dates(self, conn, report_env) -> None:
        _insert_decision(conn, report_env, action="block", reason_code="stale", date=OTHER_DATE)

        summary = build_risk_gate_summary(conn, accounts=[report_env.account_name], report_date=REPORT_DATE)

        assert summary["total_decisions"] == 0

    def test_unknown_account_is_reported_not_dropped(self, conn, report_env) -> None:
        # Not fatal: these summaries run after the trading steps, so raising would
        # fail the run over a reporting problem. But the name has to appear
        # somewhere, or a typo in --accounts yields a clean-looking report covering
        # fewer accounts than the run was asked for.
        summary = build_risk_gate_summary(
            conn, accounts=[report_env.account_name, "does_not_exist"], report_date=REPORT_DATE
        )

        assert [entry["account"] for entry in summary["accounts"]] == [report_env.account_name]
        assert summary["unresolved_accounts"] == ["does_not_exist"]


class TestSubmissionSummary:
    def test_reports_accepted_and_turned_away_orders(self, conn, report_env) -> None:
        _insert_order(conn, report_env, status="filled", broker_order_id="ib-1")
        _insert_order(conn, report_env, status="submitted", broker_order_id="ib-2")
        _insert_order(conn, report_env, status="rejected", status_reason="insufficient buying power")

        summary = build_submission_summary(conn, accounts=[report_env.account_name], report_date=REPORT_DATE)

        assert summary["order_count"] == 3
        assert summary["turned_away_count"] == 1
        entry = summary["accounts"][0]
        assert entry["accepted_count"] == 2
        assert entry["broker_order_ids"] == ["ib-1", "ib-2"]
        assert entry["turned_away"][0]["status"] == "rejected"
        assert entry["turned_away"][0]["status_reason"] == "insufficient buying power"

    def test_cancelled_orders_count_as_turned_away(self, conn, report_env) -> None:
        _insert_order(conn, report_env, status="cancelled", status_reason="cancelled by broker")

        summary = build_submission_summary(conn, accounts=[report_env.account_name], report_date=REPORT_DATE)

        assert summary["turned_away_count"] == 1
        assert summary["accounts"][0]["accepted_count"] == 0

    def test_ignores_other_dates(self, conn, report_env) -> None:
        _insert_order(conn, report_env, status="filled", broker_order_id="ib-old", date=OTHER_DATE)

        summary = build_submission_summary(conn, accounts=[report_env.account_name], report_date=REPORT_DATE)

        assert summary["order_count"] == 0

    def test_no_orders_reports_zero_rather_than_failing(self, conn, report_env) -> None:
        summary = build_submission_summary(conn, accounts=[report_env.account_name], report_date=REPORT_DATE)

        assert summary["order_count"] == 0
        assert summary["accounts"][0]["turned_away"] == []
        assert summary["stale_open_count"] == 0
        assert summary["unresolved_accounts"] == []

    def test_unknown_account_is_reported_not_dropped(self, conn, report_env) -> None:
        summary = build_submission_summary(
            conn, accounts=[report_env.account_name, "does_not_exist"], report_date=REPORT_DATE
        )

        assert [entry["account"] for entry in summary["accounts"]] == [report_env.account_name]
        assert summary["unresolved_accounts"] == ["does_not_exist"]


class TestStaleOpenOrders:
    """Orders left open from an earlier session.

    A `day` order cannot still be live at the broker, so one of these means
    reconciliation never resolved the row — nothing clears them automatically,
    which is exactly why the artifact has to say so.
    """

    def test_open_order_from_an_earlier_session_is_flagged(self, conn, report_env) -> None:
        _insert_order(conn, report_env, status="submitted", broker_order_id="ib-stale", date=OTHER_DATE)

        summary = build_submission_summary(conn, accounts=[report_env.account_name], report_date=REPORT_DATE)

        assert summary["stale_open_count"] == 1
        entry = summary["accounts"][0]
        assert entry["stale_open"][0]["broker_order_id"] == "ib-stale"
        # It is not one of today's orders, so it must not inflate today's counts.
        assert entry["order_count"] == 0

    def test_todays_open_order_is_not_stale(self, conn, report_env) -> None:
        _insert_order(conn, report_env, status="submitted", broker_order_id="ib-today")

        summary = build_submission_summary(conn, accounts=[report_env.account_name], report_date=REPORT_DATE)

        assert summary["stale_open_count"] == 0
        assert summary["accounts"][0]["order_count"] == 1

    def test_settled_order_from_an_earlier_session_is_not_stale(self, conn, report_env) -> None:
        _insert_order(conn, report_env, status="filled", broker_order_id="ib-done", date=OTHER_DATE)

        summary = build_submission_summary(conn, accounts=[report_env.account_name], report_date=REPORT_DATE)

        assert summary["stale_open_count"] == 0
