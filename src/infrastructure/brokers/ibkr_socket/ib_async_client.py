"""IBKR socket client implemented with the ``ib_async`` package."""

from __future__ import annotations

from typing import Any

from common.coercion import coerce_float
from infrastructure.brokers.ibkr_socket.contracts import (
    IbkrAccountValue,
    IbkrFill,
    IbkrOrderRequest,
    IbkrPosition,
    IbkrQuote,
    IbkrTrade,
)

# ib_async defaults to 4 seconds for the whole startup sync, which IB Gateway
# routinely exceeds — especially in the minutes after it starts.
_CONNECT_TIMEOUT_SECONDS = 20.0


class IbAsyncClient:
    """IBKR socket client backed by ``ib_async``.

    ``ib_async`` is the actively maintained community fork of ``ib_insync``
    (https://github.com/ib-api-reloaded/ib_async).  Install with:
        pip install ib_async

    The API is a near drop-in replacement for ``ib_insync``.
    """

    def __init__(self) -> None:
        import ib_async  # noqa: PLC0415

        self._ib = ib_async.IB()

    def connect(self, host: str, port: int, *, client_id: int) -> None:
        import ib_async  # noqa: PLC0415

        # `trades()`, `positions()`, and their fills are all served from caches
        # this startup sync fills — nothing re-requests them later. So a sync
        # timeout is not cosmetic: it leaves `trades()` empty in a way that is
        # indistinguishable from "no open orders", which would strand fills
        # during reconciliation. ib_async logs and continues by default;
        # `raiseSyncErrors` makes that failure loud instead.
        #
        # Only the fields this client actually reads are fetched. Completed
        # orders and per-sub-account updates are never read, and each one is
        # another request that can time out. Positions are always fetched by
        # ib_async regardless of the flags.
        self._ib.connect(
            host,
            port,
            clientId=client_id,
            timeout=_CONNECT_TIMEOUT_SECONDS,
            raiseSyncErrors=True,
            fetchFields=ib_async.StartupFetch.ORDERS_OPEN | ib_async.StartupFetch.EXECUTIONS,
        )

    def disconnect(self) -> None:
        self._ib.disconnect()

    def is_connected(self) -> bool:
        return self._ib.isConnected()

    def managed_accounts(self) -> list[str]:
        """Account ids this session can trade. IB sends these on connect."""
        return [str(account).strip() for account in self._ib.managedAccounts() if str(account).strip()]

    def place_order(self, order: IbkrOrderRequest) -> IbkrTrade:
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

    def trades(self) -> list[IbkrTrade]:
        return [_normalize_ib_async_trade(trade) for trade in self._ib.trades()]

    def positions(self) -> list[IbkrPosition]:
        return [
            IbkrPosition(symbol=str(position.contract.symbol), quantity=float(position.position))
            for position in self._ib.positions()
        ]

    def account_summary(self) -> list[IbkrAccountValue]:
        return [
            IbkrAccountValue(
                tag=str(value.tag),
                value=str(value.value),
                currency=str(value.currency),
            )
            for value in self._ib.accountSummary()
        ]

    def quotes(self, symbols: list[str]) -> list[IbkrQuote]:
        import ib_async  # noqa: PLC0415

        contracts = [ib_async.Stock(symbol, "SMART", "USD") for symbol in symbols]
        self._ib.qualifyContracts(*contracts)
        return [
            IbkrQuote(
                symbol=str(ticker.contract.symbol),
                bid=float(ticker.bid),
                ask=float(ticker.ask),
                last=float(ticker.last),
            )
            for ticker in self._ib.reqTickers(*contracts)
        ]


def _normalize_ib_async_trade(trade: Any) -> IbkrTrade:
    status = str(trade.orderStatus.status)
    return IbkrTrade(
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


def _normalize_ib_async_fill(fill: Any) -> IbkrFill:
    execution = fill.execution
    fill_time = execution.time
    return IbkrFill(
        shares=float(execution.shares),
        price=float(execution.avgPrice),
        time=fill_time.isoformat() if hasattr(fill_time, "isoformat") else str(fill_time),
        commission=(float(fill.commissionReport.commission) if fill.commissionReport is not None else 0.0),
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
