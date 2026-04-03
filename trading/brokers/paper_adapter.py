"""Paper trading broker adapter — simulates immediate fills at the requested price.

Used by all accounts with ``broker_type = 'paper'`` (the default).  Behaviour
is identical to the previous paper-only path: every order is accepted and
filled in full at the given price with zero commission.
"""
from __future__ import annotations

import uuid

from common.time import utc_now_iso
from trading.brokers.base import BrokerConnection, BrokerOrder, OrderFill, OrderStatus


class PaperBrokerAdapter(BrokerConnection):
    """Simulated broker that immediately fills every order at the requested price."""

    # Paper trading generates no commissions.
    _PAPER_COMMISSION: float = 0.0

    def connect(self) -> None:
        # No network connection required for paper trading.
        pass

    def disconnect(self) -> None:
        pass

    def place_order(self, order: BrokerOrder) -> BrokerOrder:
        """Accept and immediately fill *order* at ``order.price``."""
        fill_time = utc_now_iso()
        broker_order_id = f"paper-{uuid.uuid4().hex[:12]}"

        fill = OrderFill(
            filled_qty=order.qty,
            fill_price=order.price,
            fill_time=fill_time,
            commission=self._PAPER_COMMISSION,
        )

        order.broker_order_id = broker_order_id
        order.status = OrderStatus.FILLED
        order.filled_qty = order.qty
        order.avg_fill_price = order.price
        order.commission = self._PAPER_COMMISSION
        order.submitted_at = fill_time
        order.updated_at = fill_time
        order.fills = [fill]
        return order

    def cancel_order(self, broker_order_id: str) -> None:
        raise NotImplementedError("Paper orders fill immediately and cannot be cancelled.")

    def get_positions(self) -> dict[str, float]:
        raise NotImplementedError(
            "Paper positions are tracked in the DB — use accounting_service instead."
        )

    def get_account_info(self) -> dict[str, float]:
        raise NotImplementedError(
            "Paper account info is tracked in the DB — use accounting_service instead."
        )

    def get_quotes(self, tickers: list[str]) -> dict[str, dict[str, float]]:
        raise NotImplementedError(
            "Paper trading uses yfinance prices — use the MarketDataProvider instead."
        )
