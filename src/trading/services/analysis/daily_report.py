"""Daily operator report assembly for multi-book accounts.

Assembles three report sections from persisted data for a given account and date:
  - book performance table (from daily_metrics + current book state)
  - risk violations summary (from risk_decisions + risk_snapshots)
  - rotation decision log (from rotation_decisions)

Also exposes the two per-step summaries the daily DAG records after the
auto-trader has run: what the risk gate decided (step 06) and what reached the
broker (step 07). Both read the same persisted rows the runtime wrote while
executing — the DAG steps report on that work rather than performing it.

Consumed by: trading.interfaces.runtime.jobs.daily.paper_trading (steps 06, 07, 10)
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, field

from trading.models.books.book_assignment_view import BookAssignmentView
from trading.models.books.book_record import BookRecord
from trading.models.orders.order_record import OrderRecord
from trading.repositories.daily_metrics import DailyMetricsRepository
from trading.repositories.orders import OrderRepository
from trading.repositories.risk import RiskDecisionRepository, RiskSnapshotRepository
from trading.repositories.rotation_decisions import RotationDecisionRepository
from trading.services.accounts.queries import find_account
from trading.services.books.book_assignments import list_report_books

# Order statuses that mean the broker accepted the order onto its book. Anything
# else on a submission pass is either still pending or was turned away.
_ACCEPTED_ORDER_STATUSES = frozenset({"submitted", "accepted", "partially_filled", "filled"})
# Order statuses that mean the order will not fill. These are the ones worth
# surfacing by name — a paper simulator never produces them, a real broker does.
_TURNED_AWAY_ORDER_STATUSES = frozenset({"rejected", "cancelled"})


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
class AccountRiskGateSummary:
    """One account's risk-gate outcome for a step-06 summary."""

    account: str
    violations: RiskViolationsSummary


@dataclass(frozen=True, slots=True)
class AccountSubmissionSummary:
    """One account's broker submission outcome for a step-07 summary."""

    account: str
    order_count: int
    accepted_count: int
    broker_order_ids: list[str]
    turned_away: list[OrderRecord]
    # Orders still open from an earlier session — reconciliation could not resolve
    # them and nothing clears them automatically.
    stale_open: list[OrderRecord] = field(default_factory=list)


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


def _resolve_account_ids(
    conn: sqlite3.Connection,
    accounts: list[str],
) -> tuple[list[tuple[str, int]], list[str]]:
    """Split *accounts* into resolvable ``(name, id)`` pairs and names that are not.

    The unresolved names are returned rather than dropped: these summaries run
    after the trading steps, so raising would fail the run over a reporting
    problem, but staying silent would emit a clean-looking report covering fewer
    accounts than the run was asked for. The caller puts them in the payload.
    """
    resolved: list[tuple[str, int]] = []
    unresolved: list[str] = []
    for account_name in accounts:
        account_row = find_account(conn, account_name)
        if account_row is None:
            unresolved.append(account_name)
            continue
        resolved.append((account_name, int(account_row.id)))
    return resolved, unresolved


def build_risk_gate_summary(
    conn: sqlite3.Connection,
    *,
    accounts: list[str],
    report_date: str,
) -> dict[str, object]:
    """Summarize what the risk gate decided for each account on *report_date*.

    The gate runs inside the auto-trading runtime; this reads the
    ``risk_decisions`` rows it wrote so the DAG step can report on them.
    """
    resolved, unresolved = _resolve_account_ids(conn, accounts)
    per_account = [
        AccountRiskGateSummary(
            account=account_name,
            violations=_build_risk_violations(conn, account_id, report_date),
        )
        for account_name, account_id in resolved
    ]
    return {
        "report_date": report_date,
        "accounts": [{"account": entry.account, **asdict(entry.violations)} for entry in per_account],
        "unresolved_accounts": unresolved,
        "total_decisions": sum(entry.violations.total_decisions for entry in per_account),
        "blocked": sum(entry.violations.block_count for entry in per_account),
        "rescaled": sum(entry.violations.rescale_count for entry in per_account),
        "kill_switch_accounts": [entry.account for entry in per_account if entry.violations.kill_switch_triggered],
    }


def _order_as_summary_row(order: OrderRecord) -> dict[str, object]:
    return {
        "order_id": order.id,
        "book_id": order.book_id,
        "symbol": order.symbol,
        "side": order.side,
        "qty": order.qty,
        "status": order.status,
        "broker_order_id": order.broker_order_id,
        "filled_qty": order.filled_qty,
        "avg_fill_price": order.avg_fill_price,
        "status_reason": order.status_reason,
    }


def build_submission_summary(
    conn: sqlite3.Connection,
    *,
    accounts: list[str],
    report_date: str,
) -> dict[str, object]:
    """Summarize what reached the broker for each account on *report_date*.

    Submission happens inside the auto-trading runtime; this reads the ``orders``
    rows it wrote. Turned-away orders are listed individually with their
    ``status_reason`` — against a real broker those are the rows worth reading,
    and the paper simulator can never produce one.
    """
    resolved, unresolved = _resolve_account_ids(conn, accounts)
    per_account = []
    repo = OrderRepository(conn)
    for account_name, account_id in resolved:
        orders = repo.fetch_for_account_on_date(account_id=account_id, date_str=report_date)
        # Open orders carried over from an earlier session. A `day` order cannot
        # still be live at the broker, so these are rows reconciliation could not
        # resolve — see open_order_reconciliation's module docstring. They are the
        # thing to watch: nothing clears them automatically.
        stale_open = [
            order
            for order in repo.fetch_open_for_account(account_id=account_id)
            if order.submitted_at[:10] < report_date
        ]
        per_account.append(
            AccountSubmissionSummary(
                account=account_name,
                order_count=len(orders),
                accepted_count=sum(1 for order in orders if order.status in _ACCEPTED_ORDER_STATUSES),
                broker_order_ids=[order.broker_order_id for order in orders if order.broker_order_id],
                turned_away=[order for order in orders if order.status in _TURNED_AWAY_ORDER_STATUSES],
                stale_open=stale_open,
            )
        )
    return {
        "report_date": report_date,
        "accounts": [
            {
                "account": entry.account,
                "order_count": entry.order_count,
                "accepted_count": entry.accepted_count,
                "turned_away_count": len(entry.turned_away),
                "broker_order_ids": entry.broker_order_ids,
                "turned_away": [_order_as_summary_row(order) for order in entry.turned_away],
                "stale_open_count": len(entry.stale_open),
                "stale_open": [_order_as_summary_row(order) for order in entry.stale_open],
            }
            for entry in per_account
        ],
        "unresolved_accounts": unresolved,
        "order_count": sum(entry.order_count for entry in per_account),
        "turned_away_count": sum(len(entry.turned_away) for entry in per_account),
        "stale_open_count": sum(len(entry.stale_open) for entry in per_account),
    }
