"""Open-order reconciliation for runtime auto-trading (clean book schema).

Polls the broker for fills on the account's open clean ``orders`` and applies any
new executions to the book (``order_fills`` + position/ledger/balances via the
shared ``apply_book_fill``). Account-level history derives from those fill rows
(the trades table was retired in revision 0006). Paper brokers fill synchronously
and report no open trades, so this is a no-op for them; it matters for async live
brokers.

**Pending orders.** A row written before its broker send (status ``pending``)
carries a ``client_order_id`` and no ``broker_order_id``. The broker echoes that
id back on its order list, so a pending row the broker is carrying is adopted
here — the confirmation that never reached the database on the original run.
A pending row no live order claims is reported, not resolved: it may have been
rejected before reaching the broker, or filled and already aged off the list.

**Unreported orders.** A broker only reports on orders it still knows about —
IBKR's order endpoint covers the current day, so a ``day`` order that expired at a
previous session's close never appears again. Those persisted rows would otherwise
sit at ``submitted`` forever and be re-polled on every future run. This module
reports them rather than resolving them: an absent order might have expired
unfilled, or might have filled on a day nothing ran, and marking a filled order
cancelled would silently corrupt the book. Deciding between those needs an
operator, so the outcome carries the ids and the caller surfaces them.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from common.coercion import row_expect_int
from common.time import utc_now_iso
from trading.models import AccountRecord
from trading.models.orders import BrokerOrder, OrderFill, OrderRecord, OrderStatus
from trading.persistence.unit_of_work import unit_of_work
from trading.repositories.orders import OrderRepository
from trading.services.execution.submission import apply_book_fill, clean_order_status


@dataclass(frozen=True, slots=True)
class ReconciliationOutcome:
    """What one reconciliation pass resolved, and what it could not.

    ``unreported_broker_order_ids`` are open persisted orders the broker did not
    mention. They are left untouched — see the module docstring for why.

    ``unresolved_pending_client_order_ids`` are the other direction: rows written
    before a send that the broker's order list does not carry. Absence is not
    proof the order never reached the broker — a same-day fill is already gone
    from the list — so these are reported, never cancelled.
    """

    newly_filled: int = 0
    adopted_pending: int = 0
    unreported_broker_order_ids: list[str] = field(default_factory=list)
    unresolved_pending_client_order_ids: list[str] = field(default_factory=list)

    @property
    def has_unreported(self) -> bool:
        return bool(self.unreported_broker_order_ids)

    @property
    def has_unresolved_pending(self) -> bool:
        return bool(self.unresolved_pending_client_order_ids)


def resolve_reconciliation_exec_id(
    *,
    broker_order_id: str,
    fill: OrderFill,
    fill_index: int,
) -> str:
    if fill.exec_id:
        return fill.exec_id
    return f"{broker_order_id}:{fill.fill_time}:{fill.filled_qty}:{fill.fill_price}:{fill_index}"


def reconcile_open_orders_impl(
    conn: sqlite3.Connection,
    account: AccountRecord,
    *,
    get_broker_for_account_fn: Callable[..., Any],
) -> ReconciliationOutcome:
    broker = get_broker_for_account_fn(account)
    account_id = row_expect_int(account, "id")
    order_repo = OrderRepository(conn)

    open_orders = order_repo.fetch_open_for_account(account_id=account_id)
    open_by_broker_id = {order.broker_order_id: order for order in open_orders if order.broker_order_id}
    pending_by_client_id = {
        order.client_order_id: order
        for order in order_repo.fetch_pending_for_account(account_id=account_id)
        if order.client_order_id
    }
    if not open_by_broker_id and not pending_by_client_id:
        broker.disconnect()
        return ReconciliationOutcome()

    try:
        live_orders = broker.get_open_trades()
        now = utc_now_iso()
        newly_filled = 0
        reported_broker_order_ids: set[str] = set()

        # Adopt first: a pending row the broker is carrying becomes an ordinary open
        # order, so the fill/status pass below treats it like any other.
        adopted_client_order_ids = _adopt_pending_orders(
            order_repo,
            live_orders=live_orders,
            pending_by_client_id=pending_by_client_id,
            open_by_broker_id=open_by_broker_id,
            now=now,
        )

        for live in live_orders:
            persisted = open_by_broker_id.get(live.broker_order_id)
            if persisted is None:
                continue
            reported_broker_order_ids.add(live.broker_order_id)

            # One transaction per broker order: every new fill's book effect and
            # the final status update land together, so a crash cannot leave a
            # recorded fill (which exec_id dedup would then skip) unapplied.
            with unit_of_work(conn):
                # Apply only executions we have not already recorded (exec_id dedup), so a
                # repeated poll of the same partial fill does not double-post to the book.
                seen_exec_ids = order_repo.fetch_fill_exec_ids(order_id=persisted.id)
                for fill_index, fill in enumerate(live.fills):
                    exec_id = resolve_reconciliation_exec_id(
                        broker_order_id=live.broker_order_id,
                        fill=fill,
                        fill_index=fill_index,
                    )
                    if exec_id in seen_exec_ids:
                        continue
                    order_repo.insert_fill(
                        order_id=persisted.id,
                        filled_qty=fill.filled_qty,
                        fill_price=fill.fill_price,
                        fill_time=fill.fill_time,
                        commission=fill.commission,
                        exec_id=exec_id,
                    )
                    apply_book_fill(
                        conn,
                        book_id=persisted.book_id,
                        order_id=persisted.id,
                        side=persisted.side,
                        symbol=persisted.symbol,
                        fill_qty=fill.filled_qty,
                        fill_price=fill.fill_price,
                        transaction_cost=fill.commission,
                        fill_time=fill.fill_time,
                    )
                    seen_exec_ids.add(exec_id)

                order_repo.update_status(
                    order_id=persisted.id,
                    status=clean_order_status(live.status),
                    filled_qty=live.filled_qty,
                    avg_fill_price=live.avg_fill_price,
                    updated_at=now,
                    status_reason=live.status_reason,
                )

            if live.status == OrderStatus.FILLED:
                newly_filled += 1

        return ReconciliationOutcome(
            newly_filled=newly_filled,
            adopted_pending=len(adopted_client_order_ids),
            # Sorted so the operator-facing report is stable run to run.
            unreported_broker_order_ids=sorted(set(open_by_broker_id) - reported_broker_order_ids),
            unresolved_pending_client_order_ids=sorted(set(pending_by_client_id) - adopted_client_order_ids),
        )
    finally:
        broker.disconnect()


def _adopt_pending_orders(
    order_repo: OrderRepository,
    *,
    live_orders: list[BrokerOrder],
    pending_by_client_id: dict[str, OrderRecord],
    open_by_broker_id: dict[str, OrderRecord],
    now: str,
) -> set[str]:
    """Complete pending rows the broker is carrying, and return the ids adopted.

    This is what the client order id buys: the broker echoes it back, so an order
    whose confirmation never reached the database is recognized here rather than
    guessed at from symbol and quantity. Adopted rows are added to
    *open_by_broker_id* so the caller's fill pass sees them.
    """
    adopted: set[str] = set()
    for live in live_orders:
        client_order_id = live.client_order_id
        if not client_order_id or not live.broker_order_id:
            continue
        persisted = pending_by_client_id.get(client_order_id)
        if persisted is None:
            continue
        order_repo.record_placement(
            order_id=persisted.id,
            broker_order_id=live.broker_order_id,
            status=clean_order_status(live.status),
            filled_qty=live.filled_qty,
            avg_fill_price=live.avg_fill_price,
            commission=live.commission,
            # The send time the pending row already carries, not this poll's clock.
            submitted_at=persisted.submitted_at,
            updated_at=now,
            status_reason=live.status_reason,
        )
        adopted.add(client_order_id)
        open_by_broker_id[live.broker_order_id] = persisted
    return adopted
