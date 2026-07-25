"""Interactive Brokers socket/TWS adapter.

This module supports TWS and IB Gateway through either ``ib_async`` or native
``ibapi``. The Client Portal / Web API implementation lives in
``infrastructure.brokers.ibkr_web``.

Requires TWS or IB Gateway to be running with the API enabled.

The adapter itself is backend-agnostic — it depends on :class:`IbkrSocketClient`
from ``brokers.ibkr_socket.protocol``. The concrete client
(``IbAsyncClient`` or ``IbApiClient``) is injected by the factory. To switch
backends, set ``TRADING_IBKR_SOCKET_CLIENT_BACKEND`` to ``ib_async`` or ``ibapi``.

Prerequisites:
    1. Install the chosen client backend:
       - ``ib_async``:  pip install ib_async        (recommended, actively maintained)
       - ``ibapi``:     pip install ibapi            (IBKR native, requires IbApiClient impl)
    2. TWS or IB Gateway is running with API access enabled (Edit → Global Config
       → API → Settings → Enable ActiveX and Socket Clients).
    3. The account row must have ``live_trading_enabled = 1``.
       This flag is set manually via a direct DB update — bots must never set it.

Connection port defaults:
    - TWS paper trading:   7497
    - TWS live trading:    7496
    - IB Gateway paper:    4002
    - IB Gateway live:     4001

Async fill note:
    IB order placement is asynchronous.  ``place_order`` returns the order with
    ``status = SUBMITTED``.  Fills arrive via IB callbacks and are reconciled
    by calling ``reconcile_open_broker_orders`` in the runtime service.
"""

from __future__ import annotations

from common.time import utc_now_iso
from infrastructure.brokers.ibkr_socket.contracts import IbkrOrderRequest
from infrastructure.brokers.ibkr_socket.protocol import IbkrSocketClient
from trading.domain.broker_connection import BrokerConnection
from trading.models.orders.broker_order import (
    BrokerOrder,
    OrderFill,
    OrderStatus,
    OrderType,
)

# Default IB TWS paper trading port.
_IB_DEFAULT_HOST = "127.0.0.1"
_IB_DEFAULT_PORT = 7497
_IB_DEFAULT_CLIENT_ID = 1

# IB account summary tags used by get_account_info.
_ACCOUNT_TAGS = frozenset(("TotalCashValue", "BuyingPower", "GrossPositionValue", "NetLiquidation"))


class IbkrSocketAdapter(BrokerConnection):
    """Broker adapter for Interactive Brokers socket/TWS flows.

    Depends on :class:`~brokers.ibkr_socket.protocol.IbkrSocketClient` — the
    concrete backend (``IbAsyncClient`` or ``IbApiClient``) is injected by
    :func:`brokers.factory.get_broker_for_account`.

    Instantiated only when ``broker_type = 'interactive_brokers'`` and
    ``live_trading_enabled = 1`` on the account row.

    The persisted ``interactive_brokers`` value remains a compatibility name
    until a later migration introduces ``interactive_brokers_socket``.
    """

    def __init__(
        self,
        client: IbkrSocketClient,
        host: str = _IB_DEFAULT_HOST,
        port: int = _IB_DEFAULT_PORT,
        client_id: int = _IB_DEFAULT_CLIENT_ID,
    ) -> None:
        self._client = client
        self.host = host
        self.port = port
        self.client_id = client_id

    def connect(self) -> None:
        """Connect to TWS/IB Gateway."""
        self._client.connect(self.host, self.port, client_id=self.client_id)

    def disconnect(self) -> None:
        """Disconnect from TWS/IB Gateway."""
        if self._client.is_connected():
            self._client.disconnect()

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------

    def place_order(self, order: BrokerOrder) -> BrokerOrder:
        """Submit *order* to IB and return it with ``status = SUBMITTED``.

        Fills arrive asynchronously.  The caller must persist the returned
        SUBMITTED order and later reconcile fills via ``get_open_trades``.
        """
        self._require_connected()
        request = IbkrOrderRequest(
            symbol=order.ticker,
            action=order.side.upper(),
            total_quantity=order.qty,
            order_type="MKT" if order.order_type == OrderType.MARKET else "LMT",
            limit_price=order.price if order.order_type == OrderType.LIMIT else 0.0,
            time_in_force=order.time_in_force.value.upper(),
        )
        trade = self._client.place_order(request)
        now = utc_now_iso()
        order.broker_order_id = str(trade.order_id)
        order.status = OrderStatus.SUBMITTED
        order.submitted_at = now
        order.updated_at = now
        return order

    def cancel_order(self, broker_order_id: str) -> None:
        """Request cancellation of an open order by its IB order ID."""
        self._require_connected()
        self._client.cancel_order(int(broker_order_id))

    def get_open_trades(self) -> list[BrokerOrder]:
        """Return all currently open IB trades as :class:`BrokerOrder` objects.

        Used by the fill-reconciliation loop to update SUBMITTED orders.
        Each returned order reflects the latest known fill state from IB.
        """
        self._require_connected()
        result: list[BrokerOrder] = []
        for trade in self._client.trades():
            fills = [
                OrderFill(
                    filled_qty=fill.shares,
                    fill_price=fill.price,
                    fill_time=fill.time,
                    commission=fill.commission,
                    exec_id=fill.exec_id,
                )
                for fill in trade.fills
            ]
            broker_order = BrokerOrder(
                account_id=0,  # caller sets from their account context
                ticker=trade.symbol,
                side=trade.action.lower(),
                qty=trade.total_quantity,
                price=trade.limit_price,
                broker_order_id=str(trade.order_id),
                status=_map_ib_status(trade.status),
                filled_qty=trade.filled,
                avg_fill_price=trade.avg_fill_price,
                commission=sum(f.commission for f in fills),
                fills=fills,
                status_reason=trade.status_reason,
            )
            result.append(broker_order)
        return result

    # ------------------------------------------------------------------
    # Account and market data
    # ------------------------------------------------------------------

    def get_positions(self) -> dict[str, float]:
        """Return current live positions as ``{ticker: qty}``."""
        self._require_connected()
        return {position.symbol: position.quantity for position in self._client.positions()}

    def get_account_info(self) -> dict[str, float]:
        """Return account summary: ``TotalCashValue``, ``BuyingPower``,
        ``GrossPositionValue``, ``NetLiquidation`` (USD values only).
        """
        self._require_connected()
        return {
            v.tag: float(v.value)
            for v in self._client.account_summary()
            if v.tag in _ACCOUNT_TAGS and v.currency == "USD"
        }

    def get_quotes(self, tickers: list[str]) -> dict[str, dict[str, float]]:
        """Return real-time bid/ask/last quotes for *tickers*."""
        self._require_connected()
        return {
            quote.symbol: {"bid": quote.bid, "ask": quote.ask, "last": quote.last}
            for quote in self._client.quotes(tickers)
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_connected(self) -> None:
        if not self._client.is_connected():
            raise RuntimeError("IbkrSocketAdapter is not connected. Call connect() first.")


# IB order status strings → our OrderStatus enum.
_IB_STATUS_MAP: dict[str, OrderStatus] = {
    "PendingSubmit": OrderStatus.PENDING,
    "PendingCancel": OrderStatus.PENDING,
    "PreSubmitted": OrderStatus.SUBMITTED,
    "Submitted": OrderStatus.SUBMITTED,
    "ApiPending": OrderStatus.SUBMITTED,
    "ApiCancelled": OrderStatus.CANCELLED,
    "Cancelled": OrderStatus.CANCELLED,
    "PartiallyFilled": OrderStatus.PARTIALLY_FILLED,
    "Filled": OrderStatus.FILLED,
    "Inactive": OrderStatus.REJECTED,
}


def _map_ib_status(ib_status: str) -> OrderStatus:
    return _IB_STATUS_MAP.get(ib_status, OrderStatus.SUBMITTED)
