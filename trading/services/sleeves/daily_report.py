"""Daily operator report assembly for sleeve-mode accounts.

Assembles three report sections from persisted data for a given account and date:
  - sleeve performance table (from daily_metrics + current sleeve state)
  - risk violations summary (from sleeve_risk_decisions + portfolio_risk_snapshots)
  - rotation decision log (from rotation_decisions)

Consumed by: trading.interfaces.runtime.jobs.daily.paper_trading (step 10)
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import dataclass

from trading.repositories.daily_metrics import DailyMetricsRepository
from trading.repositories.portfolio_risk_snapshots import fetch_latest_portfolio_risk_snapshot
from trading.repositories.rotation_decisions import fetch_rotation_decisions_for_sleeve_date
from trading.repositories.sleeve_risk_decisions import fetch_sleeve_risk_decisions_for_account_date
from trading.repositories.sleeves import (
    fetch_active_sleeve_strategy_assignment,
    fetch_strategy_sleeves_for_account,
)


def _next_date(report_date: str) -> str:
    return (dt.date.fromisoformat(report_date) + dt.timedelta(days=1)).isoformat()


@dataclass(frozen=True, slots=True)
class SleevePerformanceRow:
    sleeve_id: int
    sleeve_name: str
    strategy_name: str | None
    return_pct: float | None
    drawdown_pct: float | None
    hit_rate: float | None
    trade_count: int | None
    fees_total: float | None
    risk_adjusted_score: float | None
    current_equity: float
    start_equity: float


@dataclass(frozen=True, slots=True)
class RiskViolationsSummary:
    total_decisions: int
    block_count: int
    rescale_count: int
    allow_count: int
    kill_switch_triggered: bool
    top_reason_codes: list[str]


@dataclass(frozen=True, slots=True)
class RotationDecisionRow:
    sleeve_id: int
    sleeve_name: str
    incumbent_strategy: str | None
    challenger_strategy: str | None
    rotation_action: str
    decision_reason: str | None


@dataclass(frozen=True, slots=True)
class AccountDailyReport:
    account_id: int
    account_name: str
    report_date: str
    sleeve_performance: list[SleevePerformanceRow]
    risk_violations: RiskViolationsSummary
    rotation_decisions: list[RotationDecisionRow]


def _build_sleeve_performance(
    conn: sqlite3.Connection,
    sleeves: list,
    report_date: str,
) -> list[SleevePerformanceRow]:
    rows = []
    for sleeve in sleeves:
        sleeve_id = int(sleeve["id"])
        metrics = DailyMetricsRepository(conn).fetch_for_sleeve_window(
            sleeve_id=sleeve_id,
            start_date=report_date,
            end_date=report_date,
        )
        metric = metrics[0] if metrics else None
        assignment = fetch_active_sleeve_strategy_assignment(conn, sleeve_id=sleeve_id)
        strategy_name = str(assignment["strategy_name"]) if assignment else None
        rows.append(
            SleevePerformanceRow(
                sleeve_id=sleeve_id,
                sleeve_name=str(sleeve["name"]),
                strategy_name=strategy_name,
                return_pct=metric.return_pct if metric else None,
                drawdown_pct=metric.drawdown_pct if metric else None,
                hit_rate=metric.hit_rate if metric else None,
                trade_count=metric.trade_count if metric else None,
                fees_total=metric.fees_total if metric else None,
                risk_adjusted_score=metric.risk_adjusted_score if metric else None,
                current_equity=float(sleeve["current_equity"]),
                start_equity=float(sleeve["start_equity"]),
            )
        )
    return rows


def _build_risk_violations(
    conn: sqlite3.Connection,
    account_id: int,
    report_date: str,
) -> RiskViolationsSummary:
    decisions = fetch_sleeve_risk_decisions_for_account_date(conn, account_id=account_id, report_date=report_date)
    block_count = sum(1 for d in decisions if d["action"] == "block")
    rescale_count = sum(1 for d in decisions if d["action"] == "rescale")
    allow_count = sum(1 for d in decisions if d["action"] == "allow")

    reason_counts: dict[str, int] = {}
    for d in decisions:
        code = d["reason_code"]
        if code:
            reason_counts[str(code)] = reason_counts.get(str(code), 0) + 1
    top_reason_codes = sorted(reason_counts, key=lambda k: reason_counts[k], reverse=True)[:5]

    snapshot = fetch_latest_portfolio_risk_snapshot(conn, account_id=account_id)
    kill_switch = bool(snapshot and snapshot["kill_switch_triggered"])

    return RiskViolationsSummary(
        total_decisions=len(decisions),
        block_count=block_count,
        rescale_count=rescale_count,
        allow_count=allow_count,
        kill_switch_triggered=kill_switch,
        top_reason_codes=top_reason_codes,
    )


def _build_rotation_summary(
    conn: sqlite3.Connection,
    sleeves: list,
    report_date: str,
) -> list[RotationDecisionRow]:
    rows = []
    for sleeve in sleeves:
        sleeve_id = int(sleeve["id"])
        sleeve_name = str(sleeve["name"])
        decisions = fetch_rotation_decisions_for_sleeve_date(conn, sleeve_id=sleeve_id, report_date=report_date)
        for d in decisions:
            rows.append(
                RotationDecisionRow(
                    sleeve_id=sleeve_id,
                    sleeve_name=sleeve_name,
                    incumbent_strategy=d["incumbent_strategy"],
                    challenger_strategy=d["challenger_strategy"],
                    rotation_action=str(d["rotation_action"]),
                    decision_reason=d["decision_reason"],
                )
            )
    return rows


def build_account_daily_report(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    account_name: str,
    report_date: str,
) -> AccountDailyReport:
    sleeves = fetch_strategy_sleeves_for_account(conn, account_id=account_id)
    return AccountDailyReport(
        account_id=account_id,
        account_name=account_name,
        report_date=report_date,
        sleeve_performance=_build_sleeve_performance(conn, sleeves, report_date),
        risk_violations=_build_risk_violations(conn, account_id, report_date),
        rotation_decisions=_build_rotation_summary(conn, sleeves, report_date),
    )


def account_daily_report_as_dict(report: AccountDailyReport) -> dict[str, object]:
    return {
        "account_id": report.account_id,
        "account_name": report.account_name,
        "report_date": report.report_date,
        "sleeve_performance": [
            {
                "sleeve_id": row.sleeve_id,
                "sleeve_name": row.sleeve_name,
                "strategy_name": row.strategy_name,
                "return_pct": row.return_pct,
                "drawdown_pct": row.drawdown_pct,
                "hit_rate": row.hit_rate,
                "trade_count": row.trade_count,
                "fees_total": row.fees_total,
                "risk_adjusted_score": row.risk_adjusted_score,
                "current_equity": row.current_equity,
                "start_equity": row.start_equity,
            }
            for row in report.sleeve_performance
        ],
        "risk_violations": {
            "total_decisions": report.risk_violations.total_decisions,
            "block_count": report.risk_violations.block_count,
            "rescale_count": report.risk_violations.rescale_count,
            "allow_count": report.risk_violations.allow_count,
            "kill_switch_triggered": report.risk_violations.kill_switch_triggered,
            "top_reason_codes": report.risk_violations.top_reason_codes,
        },
        "rotation_decisions": [
            {
                "sleeve_id": row.sleeve_id,
                "sleeve_name": row.sleeve_name,
                "incumbent_strategy": row.incumbent_strategy,
                "challenger_strategy": row.challenger_strategy,
                "rotation_action": row.rotation_action,
                "decision_reason": row.decision_reason,
            }
            for row in report.rotation_decisions
        ],
    }
