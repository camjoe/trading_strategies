"""End-to-end test for the daily order-reconciliation job.

Covers the async-broker fill path of the "runtime scheduler jobs" capability:
paper accounts fill synchronously, but the IBKR async paths leave orders
``submitted`` with fills arriving later, so ``reconcile_orders`` polls the
broker and writes those fills into the book before equity is snapshotted. The
test drives the job through its ``main`` entrypoint against a real database with
a broker that reports a fill for a persisted open order, and confirms the fill
reached the order, the position, and the fill ledger.

The broker factory is patched to a fake that reports the fill — the one
controlled seam, since a real async broker is out of scope. Order resolution,
fill application, persistence, and the job's reporting are real.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import trading.interfaces.runtime.jobs.daily.paper_trading.reconcile_orders as job
from infrastructure.database.backend import SQLiteBackend, use_backend
from infrastructure.database.connection import ensure_db
from tests.support.books import ensure_default_book_id
from tests.support.db_schema import build_db_at_head
from trading.models.orders import BrokerOrder, OrderFill, OrderInsert, OrderStatus
from trading.repositories.orders import OrderRepository
from trading.repositories.positions import PositionRepository
from trading.services.accounts.mutations import create_account

BROKER_ORDER_ID = "B-1"
SYMBOL = "AAPL"


def _seed_open_order(db_path: Path) -> int:
    with use_backend(SQLiteBackend(db_path)):
        conn = ensure_db()
        try:
            create_account(conn, "acct_recon", "trend", 10_000.0, "SPY")
            account_id = conn.execute("SELECT id FROM accounts WHERE name = 'acct_recon'").fetchone()[0]
            book_id = ensure_default_book_id(conn, account_id)
            OrderRepository(conn).insert(
                OrderInsert(
                    book_id=book_id,
                    account_id=account_id,
                    broker_order_id=BROKER_ORDER_ID,
                    symbol=SYMBOL,
                    side="buy",
                    qty=10.0,
                    requested_price=150.0,
                    status="submitted",
                    submitted_at="2026-05-01T00:00:00Z",
                    updated_at="2026-05-01T00:00:00Z",
                )
            )
            conn.commit()
            return book_id
        finally:
            conn.close()


class _FillReportingBroker:
    """Reports the persisted open order as filled, the way an async broker would."""

    def get_open_trades(self) -> list[BrokerOrder]:
        return [
            BrokerOrder(
                account_id=1,
                ticker=SYMBOL,
                side="buy",
                qty=10.0,
                price=150.0,
                broker_order_id=BROKER_ORDER_ID,
                status=OrderStatus.FILLED,
                filled_qty=10.0,
                avg_fill_price=150.5,
                commission=0.25,
                fills=[
                    OrderFill(
                        filled_qty=10.0,
                        fill_price=150.5,
                        fill_time="2026-05-02T10:00:00Z",
                        commission=0.25,
                        exec_id="exec-recon-1",
                    )
                ],
            )
        ]

    def disconnect(self) -> None:
        return None


def test_reconcile_orders_job_applies_a_broker_fill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = build_db_at_head(tmp_path / "recon.db")
    book_id = _seed_open_order(db_path)

    monkeypatch.setattr(job, "get_broker_for_account", lambda _account: _FillReportingBroker())

    with use_backend(SQLiteBackend(db_path)):
        monkeypatch.setattr(sys, "argv", ["reconcile_orders", "--accounts", "acct_recon"])
        job.main()

        verify = ensure_db()
        try:
            orders = OrderRepository(verify).fetch_for_book(book_id=book_id)
            position = PositionRepository(verify).fetch(book_id=book_id, symbol=SYMBOL)
            fill_count = verify.execute(
                "SELECT COUNT(*) FROM order_fills f JOIN orders o ON o.id = f.order_id WHERE o.broker_order_id = ?",
                (BROKER_ORDER_ID,),
            ).fetchone()[0]
        finally:
            verify.close()

    assert "acct_recon: reconciled 1 newly filled order(s)" in capsys.readouterr().out

    assert len(orders) == 1
    assert orders[0].status == "filled"
    assert position is not None
    assert position.qty == 10.0
    assert fill_count == 1
