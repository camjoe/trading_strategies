"""Interactive Brokers adapter.

Requires TWS or IB Gateway to be running with the API enabled.

The adapter itself is backend-agnostic — it depends on :class:`IBClientProtocol`
from ``trading.brokers.ib_client``.  The concrete client (``IbAsyncClient`` or
``IbApiClient``) is injected by the factory.  To switch backends, change
``IB_CLIENT_BACKEND`` in ``trading/brokers/factory.py``.

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
    by calling ``reconcile_open_ib_orders`` in the runtime service.
"""
from __future__ import annotations

from common.time import utc_now_iso
from trading.brokers.base import (
    BrokerConnection,
    BrokerOrder,
    OrderFill,
    OrderStatus,
    OrderType,
)
from trading.brokers.ib_client import IBClientProtocol

# Default IB TWS paper trading port.
_IB_DEFAULT_HOST = "127.0.0.1"
_IB_DEFAULT_PORT = 7497
_IB_DEFAULT_CLIENT_ID = 1

# IB account summary tags used by get_account_info.
_ACCOUNT_TAGS = frozenset(("TotalCashValue", "BuyingPower", "GrossPositionValue", "NetLiquidation"))


class InteractiveBrokersAdapter(BrokerConnection):
    """Live broker adapter for Interactive Brokers.

    Depends on :class:`~trading.brokers.ib_client.IBClientProtocol` — the
    concrete backend (``IbAsyncClient`` or ``IbApiClient``) is injected by
    :func:`trading.brokers.factory.get_broker_for_account`.

    Instantiated only when ``broker_type = 'interactive_brokers'`` and
    ``live_trading_enabled = 1`` on the account row.
    """

    def __init__(
        self,
        client: IBClientProtocol,
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
        contract = self._make_stock(order.ticker)
        ib_order = self._client.make_order(
            action=order.side.upper(),
            totalQuantity=order.qty,
            orderType="MKT" if order.order_type == OrderType.MARKET else "LMT",
            lmtPrice=order.price if order.order_type == OrderType.LIMIT else 0.0,
            tif=order.time_in_force.value.upper(),
        )
        trade = self._client.place_order(contract, ib_order)
        now = utc_now_iso()
        order.broker_order_id = str(trade.order.orderId)
        order.status = OrderStatus.SUBMITTED
        order.submitted_at = now
        order.updated_at = now
        return order

    def cancel_order(self, broker_order_id: str) -> None:
        """Request cancellation of an open order by its IB order ID."""
        self._require_connected()
        target_id = int(broker_order_id)
        for trade in self._client.trades():
            if trade.order.orderId == target_id:
                self._client.cancel_order(trade.order)
                return
        raise ValueError(f"No open IB order found with id {broker_order_id!r}")

    def get_open_trades(self) -> list[BrokerOrder]:
        """Return all currently open IB trades as :class:`BrokerOrder` objects.

        Used by the fill-reconciliation loop to update SUBMITTED orders.
        Each returned order reflects the latest known fill state from IB.
        """
        self._require_connected()
        result: list[BrokerOrder] = []
        for trade in self._client.trades():
            ib_order = trade.order
            ib_status = trade.orderStatus
            fills = [
                OrderFill(
                    filled_qty=f.execution.shares,
                    fill_price=f.execution.avgPrice,
                    fill_time=(
                        f.execution.time.isoformat()
                        if hasattr(f.execution.time, "isoformat")
                        else str(f.execution.time)
                    ),
                    commission=f.commissionReport.commission if f.commissionReport else 0.0,
                    exec_id=getattr(f.execution, "execId", None),
                )
                for f in trade.fills
            ]
            broker_order = BrokerOrder(
                account_id=0,  # caller sets from their account context
                ticker=trade.contract.symbol,
                side=ib_order.action.lower(),
                qty=ib_order.totalQuantity,
                price=ib_order.lmtPrice or 0.0,
                broker_order_id=str(ib_order.orderId),
                status=_map_ib_status(ib_status.status),
                filled_qty=ib_status.filled,
                avg_fill_price=ib_status.avgFillPrice if ib_status.avgFillPrice is not None else None,
                commission=sum(f.commission for f in fills),
                fills=fills,
            )
            result.append(broker_order)
        return result

    # ------------------------------------------------------------------
    # Account and market data
    # ------------------------------------------------------------------

    def get_positions(self) -> dict[str, float]:
        """Return current live positions as ``{ticker: qty}``."""
        self._require_connected()
        return {p.contract.symbol: p.position for p in self._client.positions()}

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
        contracts = [self._make_stock(t) for t in tickers]
        self._client.qualify_contracts(*contracts)
        ticker_data = self._client.req_tickers(*contracts)
        return {
            t.contract.symbol: {"bid": t.bid, "ask": t.ask, "last": t.last}
            for t in ticker_data
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_stock(self, symbol: str):
        """Create an IB Stock contract via the injected client."""
        return self._client.make_stock(symbol)

    def _require_connected(self) -> None:
        if not self._client.is_connected():
            raise RuntimeError(
                "InteractiveBrokersAdapter is not connected. Call connect() first."
            )


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
