from __future__ import annotations

import pytest

from tests.support.books import insert_test_book
from tests.support.repositories import insert_repository_account
from trading.repositories.daily_metrics import DailyMetricsRepository
from trading.repositories.orders import OrderRepository
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.services.accounts import get_account
from trading.services.analysis.daily_metrics import write_daily_metrics_for_account

METRIC_DATE = "2026-07-24"


def _seed_book(conn, *, name: str) -> tuple[object, int]:
    account_id = insert_repository_account(conn, name=name)
    book_id = insert_test_book(conn, account_id=account_id, name=f"{name}_book")
    return get_account(conn, name), book_id


def _snapshot(conn, *, book_id: int, time_iso: str, equity: float) -> None:
    EquitySnapshotRepository(conn).insert_for_book(
        book_id=book_id,
        snapshot_time=time_iso,
        cash=equity,
        market_value=0.0,
        equity=equity,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )


def _filled_order(
    conn, *, book_id: int, account_id: int, side: str, qty: float, requested: float, fill: float, realized=None
) -> None:
    repo = OrderRepository(conn)
    order_id = repo.insert(
        book_id=book_id,
        account_id=account_id,
        symbol="AAPL",
        side=side,
        qty=qty,
        requested_price=requested,
        status="filled",
        filled_qty=qty,
        avg_fill_price=fill,
        commission=1.0,
        submitted_at=f"{METRIC_DATE}T15:00:00Z",
        updated_at=f"{METRIC_DATE}T15:00:00Z",
    )
    if realized is not None:
        repo.add_realized_pnl_delta(order_id=order_id, realized_pnl_delta=realized)


def test_writer_persists_computed_metrics_for_a_trading_day(conn) -> None:
    account, book_id = _seed_book(conn, name="dm_acct")
    _snapshot(conn, book_id=book_id, time_iso="2026-07-23T16:00:00Z", equity=1000.0)
    _snapshot(conn, book_id=book_id, time_iso=f"{METRIC_DATE}T16:00:00Z", equity=1020.0)
    _filled_order(conn, book_id=book_id, account_id=account.id, side="buy", qty=10.0, requested=100.0, fill=101.0)

    written = write_daily_metrics_for_account(conn, account, metric_date=METRIC_DATE)
    assert written == 1

    rows = DailyMetricsRepository(conn).fetch_for_book(book_id=book_id, limit=1)
    assert len(rows) == 1
    row = rows[0]
    assert row.return_pct == pytest.approx(2.0)  # 1020 / 1000 - 1
    assert row.trade_count == 1
    assert row.fees_total == pytest.approx(1.0)
    assert row.turnover_pct == pytest.approx(10 * 101.0 / 1020.0 * 100.0)
    assert row.slippage_bps == pytest.approx(100.0)  # bought 101 vs requested 100
    # A buy realizes nothing, so no closing trade → hit_rate/expectancy None here.
    assert row.hit_rate is None
    # Unavailable at this grain regardless:
    assert row.drawdown_pct is None
    assert row.risk_adjusted_score is None


def test_writer_derives_hit_rate_and_expectancy_from_closing_orders(conn) -> None:
    account, book_id = _seed_book(conn, name="dm_closes")
    _snapshot(conn, book_id=book_id, time_iso=f"{METRIC_DATE}T16:00:00Z", equity=1000.0)
    # Two closing sells: one winner (+40), one loser (-10).
    _filled_order(
        conn, book_id=book_id, account_id=account.id, side="sell", qty=5, requested=100, fill=100, realized=40.0
    )
    _filled_order(
        conn, book_id=book_id, account_id=account.id, side="sell", qty=5, requested=100, fill=100, realized=-10.0
    )

    write_daily_metrics_for_account(conn, account, metric_date=METRIC_DATE)

    row = DailyMetricsRepository(conn).fetch_for_book(book_id=book_id, limit=1)[0]
    assert row.hit_rate == pytest.approx(0.5)
    assert row.expectancy == pytest.approx(15.0)  # (40 + -10) / 2


def test_writer_skips_books_without_a_snapshot(conn) -> None:
    account, _ = _seed_book(conn, name="dm_empty")
    written = write_daily_metrics_for_account(conn, account, metric_date=METRIC_DATE)
    assert written == 0


def test_writer_is_idempotent_on_reruns(conn) -> None:
    account, book_id = _seed_book(conn, name="dm_rerun")
    _snapshot(conn, book_id=book_id, time_iso=f"{METRIC_DATE}T16:00:00Z", equity=1000.0)

    write_daily_metrics_for_account(conn, account, metric_date=METRIC_DATE)
    write_daily_metrics_for_account(conn, account, metric_date=METRIC_DATE)

    rows = DailyMetricsRepository(conn).fetch_for_book(book_id=book_id, limit=10)
    assert len(rows) == 1  # upsert on (book_id, metric_date), not a duplicate insert
