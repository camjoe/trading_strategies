"""Daily operator report assembly for multi-book accounts.

Assembles three report sections from persisted data for a given account and date:
  - book performance table (from daily_metrics + current book state)
  - risk violations summary (from risk_decisions + risk_snapshots)
  - rotation decision log (from rotation_decisions)

Consumed by: trading.interfaces.runtime.jobs.daily.paper_trading (step 10)
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass

from trading.models.books.book_assignment_view import BookAssignmentView
from trading.models.books.book_record import BookRecord
from trading.repositories.daily_metrics import DailyMetricsRepository
from trading.repositories.risk import RiskDecisionRepository, RiskSnapshotRepository
from trading.repositories.rotation_decisions import RotationDecisionRepository
from trading.services.books.book_assignments import list_report_books


@dataclass(frozen=True, slots=True)
class BookPerformanceRow:
    book_id: int
    book_name: str
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
    book_id: int
    book_name: str
    incumbent_strategy: str | None
    challenger_strategy: str | None
    rotation_action: str
    decision_reason: str | None


@dataclass(frozen=True, slots=True)
class AccountDailyReport:
    account_id: int
    account_name: str
    report_date: str
    book_performance: list[BookPerformanceRow]
    risk_violations: RiskViolationsSummary
    rotation_decisions: list[RotationDecisionRow]


def _build_book_performance(
    conn: sqlite3.Connection,
    books: list[tuple[BookRecord, BookAssignmentView | None]],
    report_date: str,
) -> list[BookPerformanceRow]:
    rows = []
    for book, assignment in books:
        metrics = DailyMetricsRepository(conn).fetch_for_book_window(
            book_id=book.id,
            start_date=report_date,
            end_date=report_date,
        )
        metric = metrics[0] if metrics else None
        rows.append(
            BookPerformanceRow(
                book_id=book.id,
                book_name=book.name,
                strategy_name=assignment.strategy_name if assignment is not None else None,
                return_pct=metric.return_pct if metric else None,
                drawdown_pct=metric.drawdown_pct if metric else None,
                hit_rate=metric.hit_rate if metric else None,
                trade_count=metric.trade_count if metric else None,
                fees_total=metric.fees_total if metric else None,
                risk_adjusted_score=metric.risk_adjusted_score if metric else None,
                current_equity=book.current_equity,
                start_equity=book.start_equity,
            )
        )
    return rows


def _build_risk_violations(
    conn: sqlite3.Connection,
    account_id: int,
    report_date: str,
) -> RiskViolationsSummary:
    decisions = RiskDecisionRepository(conn).fetch_for_account_date(
        account_id=account_id,
        report_date=report_date,
    )
    block_count = sum(1 for d in decisions if d.action == "block")
    rescale_count = sum(1 for d in decisions if d.action == "rescale")
    allow_count = sum(1 for d in decisions if d.action == "allow")

    reason_counts: dict[str, int] = {}
    for d in decisions:
        if d.reason_code:
            reason_counts[d.reason_code] = reason_counts.get(d.reason_code, 0) + 1
    top_reason_codes = sorted(reason_counts, key=lambda k: reason_counts[k], reverse=True)[:5]

    snapshot = RiskSnapshotRepository(conn).fetch_latest_as_of(account_id=account_id, report_date=report_date)
    kill_switch = snapshot is not None and bool(snapshot.kill_switch_triggered)

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
    books: list[tuple[BookRecord, BookAssignmentView | None]],
    report_date: str,
) -> list[RotationDecisionRow]:
    rows = []
    for book, _assignment in books:
        decisions = RotationDecisionRepository(conn).fetch_for_book_on_date(
            book_id=book.id,
            report_date=report_date,
        )
        for d in decisions:
            rows.append(
                RotationDecisionRow(
                    book_id=book.id,
                    book_name=book.name,
                    incumbent_strategy=d.incumbent_strategy,
                    challenger_strategy=d.challenger_strategy,
                    rotation_action=d.rotation_action,
                    decision_reason=d.decision_reason,
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
    books = list_report_books(conn, account_id=account_id)
    return AccountDailyReport(
        account_id=account_id,
        account_name=account_name,
        report_date=report_date,
        book_performance=_build_book_performance(conn, books, report_date),
        risk_violations=_build_risk_violations(conn, account_id, report_date),
        rotation_decisions=_build_rotation_summary(conn, books, report_date),
    )


def account_daily_report_as_dict(report: AccountDailyReport) -> dict[str, object]:
    # The dataclasses' field names are the JSON artifact's keys, so asdict()
    # recurses into the nested row/summary dataclasses to build the payload.
    return asdict(report)
