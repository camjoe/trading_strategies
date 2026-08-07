"""Write per-book daily performance metrics from a day's stored activity.

The one production writer for `daily_metrics`. For each book in an account it
gathers the day's equity boundaries and filled orders, derives the honestly
computable metrics (``domain/daily_metrics``), and upserts one row per book on
``(book_id, metric_date)``. Runs after the equity snapshot is written for the
day, so the return derivation has an end-of-day equity to read.
"""

from __future__ import annotations

import sqlite3

from common.time import utc_now_iso
from trading.domain.daily_metrics import (
    RISK_ADJUSTED_WINDOW_SESSIONS,
    DailyTrade,
    compute_daily_book_metrics,
)
from trading.models import AccountRecord
from trading.persistence.unit_of_work import unit_of_work
from trading.repositories.books import BookRepository
from trading.repositories.daily_metrics import DailyMetricsRepository
from trading.repositories.orders import OrderRepository
from trading.repositories.snapshots import EquitySnapshotRepository


def write_daily_metrics_for_account(
    conn: sqlite3.Connection,
    account: AccountRecord,
    *,
    metric_date: str,
    now_iso: str | None = None,
) -> int:
    """Compute and upsert one `daily_metrics` row per book for ``metric_date``.

    ``metric_date`` is a ``YYYY-MM-DD`` calendar day. Returns the number of book
    rows written. Books with no snapshot on or before the day are skipped (there
    is no equity to summarize). All writes land in one transaction.
    """
    resolved_now = now_iso or utc_now_iso()
    snapshots = EquitySnapshotRepository(conn)
    orders = OrderRepository(conn)
    metrics = DailyMetricsRepository(conn)

    written = 0
    with unit_of_work(conn):
        for book in BookRepository(conn).fetch_for_account(account_id=account.id):
            end_snapshot = snapshots.fetch_last_for_book_on_or_before_date(book_id=book.id, date_str=metric_date)
            if end_snapshot is None:
                continue
            prev_snapshot = snapshots.fetch_last_for_book_before_date(book_id=book.id, date_str=metric_date)
            trades = [
                DailyTrade(
                    side=order.side,
                    filled_qty=order.filled_qty,
                    avg_fill_price=order.avg_fill_price if order.avg_fill_price is not None else 0.0,
                    requested_price=order.requested_price,
                    commission=order.commission,
                    realized_pnl_delta=order.realized_pnl_delta,
                )
                for order in orders.fetch_filled_for_book_on_date(book_id=book.id, date_str=metric_date)
            ]
            # The current day plus its trailing sessions form the risk-adjusted
            # score's window; fetch the priors that come before it (limit leaves
            # one slot for the day being written).
            prior_returns = metrics.fetch_recent_returns_for_book(
                book_id=book.id,
                before_date=metric_date,
                limit=RISK_ADJUSTED_WINDOW_SESSIONS - 1,
            )
            computed = compute_daily_book_metrics(
                prev_equity=prev_snapshot.equity if prev_snapshot is not None else None,
                end_equity=end_snapshot.equity,
                trades=trades,
                prior_returns=prior_returns,
            )
            metrics.upsert(
                account_id=account.id,
                book_id=book.id,
                metric_date=metric_date,
                return_pct=computed.return_pct,
                drawdown_pct=computed.drawdown_pct,
                turnover_pct=computed.turnover_pct,
                slippage_bps=computed.slippage_bps,
                hit_rate=computed.hit_rate,
                expectancy=computed.expectancy,
                risk_adjusted_score=computed.risk_adjusted_score,
                trade_count=computed.trade_count,
                fees_total=computed.fees_total,
                created_at=resolved_now,
                updated_at=resolved_now,
            )
            written += 1
    return written
