"""Legacy IB socket client abstraction.

This module exists for the older TWS / IB Gateway socket-based integration used
by ``trading.brokers.legacy.ib_adapter``. The current active IBKR integration
path in this repository is the Client Portal / Web API implementation in
``infrastructure.brokers.ib_web``.

The code remains in place so the socket-based path can be revisited later
without rebuilding it from scratch, but it should be treated as legacy support.

Two concrete clients are provided:

  IbAsyncClient   — wraps ``ib_async`` (the actively maintained community fork of ib_insync).
                    This is the default and recommended client.

  IbApiClient     — wraps IBKR's official native ``ibapi`` package (callback-based).
                    Documented stub; implement when you prefer zero third-party dependencies.

The factory decides which client to inject.  To switch backends, change
``IB_CLIENT_BACKEND`` in ``brokers/legacy/factory.py`` — no other code needs to change.

Protocol contract
-----------------
Any custom client must implement :class:`IBClientProtocol`.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from common.coercion import coerce_float
from infrastructure.brokers.legacy.client_models import (
    LegacyAccountValue,
    LegacyFill,
    LegacyOrderRequest,
    LegacyPosition,
    LegacyQuote,
    LegacyTrade,
)


@runtime_checkable
class IBClientProtocol(Protocol):
    """Minimal interface that any IB client backend must satisfy.

    ``InteractiveBrokersAdapter`` depends only on this protocol — not on
    ``ib_async``, ``ibapi``, or any other concrete library.
    """

    def connect(self, host: str, port: int, *, client_id: int) -> None:
        """Establish connection to TWS/IB Gateway."""
        ...

    def disconnect(self) -> None:
        """Close the connection gracefully."""
        ...

    def is_connected(self) -> bool:
        """Return True if currently connected."""
        ...

    def place_order(self, order: LegacyOrderRequest) -> LegacyTrade:
        """Submit an order and return normalized trade state."""
        ...

    def cancel_order(self, order_id: int) -> None:
        """Request cancellation by broker order ID."""
        ...

    def trades(self) -> list[LegacyTrade]:
        """Return all currently tracked normalized trades."""
        ...

    def positions(self) -> list[LegacyPosition]:
        """Return normalized account positions."""
        ...

    def account_summary(self) -> list[LegacyAccountValue]:
        """Return normalized account summary values."""
        ...

    def quotes(self, symbols: list[str]) -> list[LegacyQuote]:
        """Return normalized quote snapshots for symbols."""
        ...


# ---------------------------------------------------------------------------
# IbAsyncClient — wraps ib_async (recommended)
# ---------------------------------------------------------------------------


class IbAsyncClient:
    """Legacy IBClientProtocol implementation backed by ``ib_async``.

    ``ib_async`` is the actively maintained community fork of ``ib_insync``
    (https://github.com/ib-api-reloaded/ib_async).  Install with:
        pip install ib_async

    The API is a near drop-in replacement for ``ib_insync``.
    """

    def __init__(self) -> None:
        import ib_async  # noqa: PLC0415

        self._ib = ib_async.IB()

    def connect(self, host: str, port: int, *, client_id: int) -> None:
        self._ib.connect(host, port, clientId=client_id)

    def disconnect(self) -> None:
        self._ib.disconnect()

    def is_connected(self) -> bool:
        return self._ib.isConnected()

    def place_order(self, order: LegacyOrderRequest) -> LegacyTrade:
        import ib_async  # noqa: PLC0415

        contract = ib_async.Stock(order.symbol, "SMART", "USD")
        ib_order = ib_async.Order(
            action=order.action,
            totalQuantity=order.total_quantity,
            orderType=order.order_type,
            lmtPrice=order.limit_price,
            tif=order.time_in_force,
        )
        return _normalize_ib_async_trade(self._ib.placeOrder(contract, ib_order))

    def cancel_order(self, order_id: int) -> None:
        for trade in self._ib.trades():
            if int(trade.order.orderId) == order_id:
                self._ib.cancelOrder(trade.order)
                return
        raise ValueError(f"No open IB order found with id {order_id!r}")

    def trades(self) -> list[LegacyTrade]:
        return [_normalize_ib_async_trade(trade) for trade in self._ib.trades()]

    def positions(self) -> list[LegacyPosition]:
        return [
            LegacyPosition(symbol=str(position.contract.symbol), quantity=float(position.position))
            for position in self._ib.positions()
        ]

    def account_summary(self) -> list[LegacyAccountValue]:
        return [
            LegacyAccountValue(
                tag=str(value.tag),
                value=str(value.value),
                currency=str(value.currency),
            )
            for value in self._ib.accountSummary()
        ]

    def quotes(self, symbols: list[str]) -> list[LegacyQuote]:
        import ib_async  # noqa: PLC0415

        contracts = [ib_async.Stock(symbol, "SMART", "USD") for symbol in symbols]
        self._ib.qualifyContracts(*contracts)
        return [
            LegacyQuote(
                symbol=str(ticker.contract.symbol),
                bid=float(ticker.bid),
                ask=float(ticker.ask),
                last=float(ticker.last),
            )
            for ticker in self._ib.reqTickers(*contracts)
        ]


def _normalize_ib_async_trade(trade: Any) -> LegacyTrade:
    status = str(trade.orderStatus.status)
    return LegacyTrade(
        order_id=int(trade.order.orderId),
        symbol=str(trade.contract.symbol),
        action=str(trade.order.action),
        total_quantity=float(trade.order.totalQuantity),
        limit_price=float(trade.order.lmtPrice or 0.0),
        status=status,
        filled=float(trade.orderStatus.filled),
        avg_fill_price=_optional_float(trade.orderStatus.avgFillPrice),
        fills=tuple(_normalize_ib_async_fill(fill) for fill in trade.fills),
        status_reason=_ib_async_status_reason(trade, status),
    )


def _normalize_ib_async_fill(fill: Any) -> LegacyFill:
    execution = fill.execution
    fill_time = execution.time
    return LegacyFill(
        shares=float(execution.shares),
        price=float(execution.avgPrice),
        time=fill_time.isoformat() if hasattr(fill_time, "isoformat") else str(fill_time),
        commission=(
            float(fill.commissionReport.commission) if fill.commissionReport is not None else 0.0
        ),
        exec_id=str(execution.execId) if getattr(execution, "execId", None) else None,
    )


def _optional_float(value: object) -> float | None:
    return coerce_float(value)


def _ib_async_status_reason(trade: Any, status: str) -> str | None:
    if status not in {"ApiCancelled", "Cancelled", "Inactive"}:
        return None
    advanced_error = _clean_text(getattr(trade, "advancedError", None))
    if advanced_error is not None:
        return advanced_error
    for entry in reversed(getattr(trade, "log", ())):
        error_code = getattr(entry, "errorCode", 0)
        message = _clean_text(getattr(entry, "message", None))
        if isinstance(error_code, int) and error_code != 0 and message is not None:
            return f"IBKR {error_code}: {message}"
    return None


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None


# ---------------------------------------------------------------------------
# IbApiClient — wraps IBKR native ibapi (stub)
# ---------------------------------------------------------------------------


class IbApiClient:
    """Legacy IBClientProtocol implementation backed by IBKR's official ``ibapi`` package.

    This is a documented stub for teams that prefer zero third-party dependencies
    and are willing to work with ibapi's callback-based architecture directly.

    Install the native API:
        pip install ibapi
      or download from https://interactivebrokers.github.io/

    Implementation notes
    --------------------
    ``ibapi`` is callback-based (EWrapper + EClient).  To implement this client:

    1. Subclass both ``ibapi.wrapper.EWrapper`` and ``ibapi.client.EClient``.
    2. Implement callback methods (``execDetails``, ``orderStatus``, ``position``,
       ``accountSummaryEnd``, etc.) to collect results into threading.Event/Queue.
    3. Wrap each operation in a synchronous helper that fires the request and
       blocks on the corresponding Event/Queue until the callback fires.

    Example skeleton::

        from ibapi.client import EClient
        from ibapi.wrapper import EWrapper
        import threading

        class _IBApp(EWrapper, EClient):
            def __init__(self):
                EWrapper.__init__(self)
                EClient.__init__(self, self)
                self._positions: list = []
                self._pos_event = threading.Event()

            def position(self, account, contract, pos, avg_cost):
                self._positions.append((contract.symbol, pos))

            def positionEnd(self):
                self._pos_event.set()

    Then ``IbApiClient.connect()`` would spin the app in a background thread and
    each public method would trigger the appropriate request + wait on its Event.
    """

    def connect(self, host: str, port: int, *, client_id: int) -> None:
        raise NotImplementedError(
            "IbApiClient is not yet implemented. Use IbAsyncClient (ib_async) as the default backend."
        )

    def disconnect(self) -> None:
        raise NotImplementedError("IbApiClient is not yet implemented.")

    def is_connected(self) -> bool:
        raise NotImplementedError("IbApiClient is not yet implemented.")

    def place_order(self, order: LegacyOrderRequest) -> LegacyTrade:
        raise NotImplementedError("IbApiClient is not yet implemented.")

    def cancel_order(self, order_id: int) -> None:
        raise NotImplementedError("IbApiClient is not yet implemented.")

    def trades(self) -> list[LegacyTrade]:
        raise NotImplementedError("IbApiClient is not yet implemented.")

    def positions(self) -> list[LegacyPosition]:
        raise NotImplementedError("IbApiClient is not yet implemented.")

    def account_summary(self) -> list[LegacyAccountValue]:
        raise NotImplementedError("IbApiClient is not yet implemented.")

    def quotes(self, symbols: list[str]) -> list[LegacyQuote]:
        raise NotImplementedError("IbApiClient is not yet implemented.")
