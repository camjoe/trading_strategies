"""Seed module for multi-book data used in the shared seeded_conn fixture."""

from __future__ import annotations

import sqlite3

from tests.support.seed.accounts import ACCT_TREND, seed_account_id

BOOK_TREND = "seed_book_core"
BOOK_STRATEGY = "trend_v1"
BOOK_METRIC_DATE = "2026-01-03"


def seed_books(conn: sqlite3.Connection) -> None:
    from trading.repositories.books import BookRepository
    from trading.repositories.daily_metrics import DailyMetricsRepository
    from trading.services.sleeves.book_assignments import assign_book_strategy

    acct_id = seed_account_id(conn, ACCT_TREND)
    ts = "2026-01-01T00:00:00Z"
    book_id = BookRepository(conn).insert(
        account_id=acct_id,
        name=BOOK_TREND,
        is_default=0,
        start_equity=10_000.0,
        current_cash=9_000.0,
        current_equity=10_200.0,
        created_at=ts,
        updated_at=ts,
    )
    assign_book_strategy(conn, book_id=book_id, strategy_name=BOOK_STRATEGY, param_set_id=None, now_iso=ts)
    DailyMetricsRepository(conn).upsert(
        account_id=acct_id,
        book_id=book_id,
        metric_date=BOOK_METRIC_DATE,
        return_pct=1.5,
        drawdown_pct=-2.0,
        turnover_pct=0.1,
        slippage_bps=3.0,
        hit_rate=0.6,
        expectancy=0.8,
        risk_adjusted_score=0.75,
        trade_count=5,
        fees_total=10.0,
        created_at=ts,
        updated_at=ts,
    )


__all__ = [
    "BOOK_METRIC_DATE",
    "BOOK_STRATEGY",
    "BOOK_TREND",
    "seed_books",
]
