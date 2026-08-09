"""Paper trading broker adapter — simulates immediate fills at the requested price.

Used by all accounts with ``broker_type = 'paper'`` (the default).  Behaviour
is identical to the previous paper-only path: every order is accepted and
filled in full at the given price with zero commission.
"""

from __future__ import annotations

import uuid

from common.time import utc_now_iso
from trading.domain.broker_connection import BrokerConnection
from trading.models.orders import BrokerOrder, OrderFill, OrderRequest, OrderStatus


class PaperBrokerAdapter(BrokerConnection):
    """Simulated broker that immediately fills every order at the requested price."""

    # Paper trading generates no commissions.
    _PAPER_COMMISSION: float = 0.0

    def connect(self) -> None:
        # No network connection required for paper trading.
        pass

    def disconnect(self) -> None:
        pass

    def place_order(self, order: OrderRequest) -> BrokerOrder:
        """Accept and immediately fill *order* at ``order.price``."""
        fill_time = utc_now_iso()

        fill = OrderFill(
            filled_qty=order.qty,
            fill_price=order.price,
            fill_time=fill_time,
            commission=self._PAPER_COMMISSION,
        )

        placed = BrokerOrder.from_request(order)
        placed.broker_order_id = f"paper-{uuid.uuid4().hex[:12]}"
        placed.status = OrderStatus.FILLED
        placed.filled_qty = order.qty
        placed.avg_fill_price = order.price
        placed.commission = self._PAPER_COMMISSION
        placed.submitted_at = fill_time
        placed.updated_at = fill_time
        placed.fills = [fill]
        return placed

    def cancel_order(self, broker_order_id: str) -> None:
        raise NotImplementedError("Paper orders fill immediately and cannot be cancelled.")

    def get_open_trades(self) -> list[BrokerOrder]:
        return []

    def get_positions(self) -> dict[str, float]:
        raise NotImplementedError(
            "Paper positions are tracked in the DB — use trading.services.execution.ledger instead."
        )

    def get_account_info(self) -> dict[str, float]:
        raise NotImplementedError(
            "Paper account info is tracked in the DB — use trading.services.execution.ledger instead."
        )

    def get_quotes(self, tickers: list[str]) -> dict[str, dict[str, float]]:
        raise NotImplementedError("Paper trading uses yfinance prices — use the MarketDataProvider instead.")
