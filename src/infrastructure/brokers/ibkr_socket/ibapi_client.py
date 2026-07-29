"""Native ``ibapi`` implementation of the IBKR socket client."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from common.coercion import coerce_float, coerce_int
from infrastructure.brokers.ibkr_socket.contracts import (
    IbkrAccountValue,
    IbkrApiError,
    IbkrFill,
    IbkrOrderRequest,
    IbkrPosition,
    IbkrQuote,
    IbkrTrade,
)

# Maximum time to wait for IBKR's nextValidId connection-readiness callback.
_CONNECTION_READY_TIMEOUT_SECONDS = 10.0

# Maximum time to wait for the native message-loop thread during shutdown.
_MESSAGE_LOOP_JOIN_TIMEOUT_SECONDS = 2.0

# Maximum time to wait for the openOrderEnd callback during an order refresh.
_OPEN_ORDER_REFRESH_TIMEOUT_SECONDS = 5.0

# Native account-summary tags required by the shared broker contract.
_ACCOUNT_SUMMARY_TAGS = "TotalCashValue,BuyingPower,GrossPositionValue,NetLiquidation"

# Native account-summary group that includes every account visible to the session.
_ACCOUNT_SUMMARY_GROUP = "All"

# Native live and delayed tick types for bid, ask, and last prices.
_BID_TICK_TYPES = frozenset({1, 66})
_ASK_TICK_TYPES = frozenset({2, 67})
_LAST_TICK_TYPES = frozenset({4, 68})

# IBKR snapshots can complete without every requested field.
_MISSING_QUOTE_VALUE = float("nan")

# IBKR uses -1 to report that a tick price is unavailable.
_UNAVAILABLE_TICK_PRICE = -1.0


class _NativeIbApp(Protocol):
    def connect(self, host: str, port: int, clientId: int) -> object: ...

    def disconnect(self) -> None: ...

    def isConnected(self) -> bool: ...

    def run(self) -> None: ...

    def place_order(self, order_id: int, order: IbkrOrderRequest) -> None: ...

    def cancel_order(self, order_id: int) -> None: ...

    def request_open_orders(self) -> None: ...

    def request_positions(self) -> None: ...

    def cancel_positions(self) -> None: ...

    def request_account_summary(self, request_id: int, group: str, tags: str) -> None: ...

    def cancel_account_summary(self, request_id: int) -> None: ...

    def request_market_data(self, request_id: int, symbol: str) -> None: ...

    def cancel_market_data(self, request_id: int) -> None: ...


@dataclass
class _NativeFillState:
    shares: float
    price: float
    time: str
    exec_id: str
    commission: float = 0.0


@dataclass
class _NativeTradeState:
    order_id: int
    symbol: str
    action: str
    total_quantity: float
    limit_price: float
    status: str = "PendingSubmit"
    filled: float = 0.0
    avg_fill_price: float | None = None
    fills: dict[str, _NativeFillState] = field(default_factory=dict)
    status_reason: str | None = None


@dataclass
class _NativeQuoteState:
    symbol: str
    complete: threading.Event = field(default_factory=threading.Event)
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    error: RuntimeError | None = None


class _IbApiCallbackState:
    """Thread-safe state shared by native callbacks and synchronous callers."""

    def __init__(self) -> None:
        self.ready = threading.Event()
        self._lock = threading.Lock()
        self._next_order_id: int | None = None
        self._next_request_id = 1
        self._errors: list[IbkrApiError] = []
        self._trades: dict[int, _NativeTradeState] = {}
        self._pending_commissions: dict[str, float] = {}
        self.open_orders_complete = threading.Event()
        self.positions_complete = threading.Event()
        self.account_summary_complete = threading.Event()
        self._positions: dict[str, IbkrPosition] = {}
        self._account_values: dict[tuple[str, str, str], IbkrAccountValue] = {}
        self._account_summary_request_id: int | None = None
        self._quotes: dict[int, _NativeQuoteState] = {}
        self._background_error: RuntimeError | None = None
        self._disconnect_requested = False
        self._managed_accounts: tuple[str, ...] = ()

    def record_next_order_id(self, order_id: int) -> None:
        with self._lock:
            self._next_order_id = order_id
            self.ready.set()

    def record_managed_accounts(self, accounts: str) -> None:
        """Store the comma-separated account list IBKR sends on connect."""
        with self._lock:
            self._managed_accounts = tuple(part.strip() for part in accounts.split(",") if part.strip())

    def managed_accounts(self) -> list[str]:
        with self._lock:
            return list(self._managed_accounts)

    def reserve_order_id(self) -> int:
        with self._lock:
            if self._next_order_id is None:
                raise RuntimeError("IBKR native client has not received nextValidId.")
            order_id = self._next_order_id
            self._next_order_id += 1
            return order_id

    def reserve_request_id(self) -> int:
        with self._lock:
            request_id = self._next_request_id
            self._next_request_id += 1
            return request_id

    def record_error(
        self,
        request_id: int,
        code: int,
        message: str,
        advanced_rejection: str | None,
    ) -> None:
        with self._lock:
            self._errors.append(
                IbkrApiError(
                    request_id=request_id,
                    code=code,
                    message=message,
                    advanced_rejection=advanced_rejection,
                )
            )
            trade = self._trades.get(request_id)
            if trade is not None:
                trade.status_reason = advanced_rejection or f"IBKR {code}: {message}"
            quote = self._quotes.get(request_id)
            if quote is not None:
                quote.error = RuntimeError(f"IBKR quote request failed ({code}): {message}")
                quote.complete.set()

    def errors(self) -> tuple[IbkrApiError, ...]:
        with self._lock:
            return tuple(self._errors)

    def register_order(self, order_id: int, order: IbkrOrderRequest) -> IbkrTrade:
        with self._lock:
            state = _NativeTradeState(
                order_id=order_id,
                symbol=order.symbol,
                action=order.action,
                total_quantity=order.total_quantity,
                limit_price=order.limit_price,
            )
            self._trades[order_id] = state
            return _trade_snapshot(state)

    def record_open_order(
        self,
        order_id: int,
        symbol: str,
        action: str,
        total_quantity: float,
        limit_price: float,
        status: str,
    ) -> None:
        with self._lock:
            state = self._trades.get(order_id)
            if state is None:
                state = _NativeTradeState(
                    order_id=order_id,
                    symbol=symbol,
                    action=action,
                    total_quantity=total_quantity,
                    limit_price=limit_price,
                )
                self._trades[order_id] = state
            state.symbol = symbol
            state.action = action
            state.total_quantity = total_quantity
            state.limit_price = limit_price
            if status:
                state.status = status

    def begin_open_order_refresh(self) -> None:
        self.open_orders_complete.clear()

    def finish_open_order_refresh(self) -> None:
        self.open_orders_complete.set()

    def record_order_status(
        self,
        order_id: int,
        status: str,
        filled: float,
        avg_fill_price: float | None,
    ) -> None:
        with self._lock:
            state = self._trades.get(order_id)
            if state is None:
                return
            state.status = status
            state.filled = filled
            state.avg_fill_price = avg_fill_price

    def record_execution(
        self,
        order_id: int,
        exec_id: str,
        shares: float,
        price: float,
        execution_time: str,
    ) -> None:
        with self._lock:
            state = self._trades.get(order_id)
            if state is None:
                return
            existing = state.fills.get(exec_id)
            commission = existing.commission if existing is not None else self._pending_commissions.pop(exec_id, 0.0)
            state.fills[exec_id] = _NativeFillState(
                shares=shares,
                price=price,
                time=execution_time,
                exec_id=exec_id,
                commission=commission,
            )

    def record_commission(self, exec_id: str, commission: float) -> None:
        with self._lock:
            for trade in self._trades.values():
                fill = trade.fills.get(exec_id)
                if fill is not None:
                    fill.commission = commission
                    return
            self._pending_commissions[exec_id] = commission

    def trade(self, order_id: int) -> IbkrTrade:
        with self._lock:
            state = self._trades.get(order_id)
            if state is None:
                raise KeyError(f"Unknown IBKR native order id {order_id}.")
            return _trade_snapshot(state)

    def trades(self) -> list[IbkrTrade]:
        with self._lock:
            return [_trade_snapshot(state) for _, state in sorted(self._trades.items())]

    def begin_positions(self) -> None:
        with self._lock:
            self._positions.clear()
            self.positions_complete.clear()

    def record_position(self, symbol: str, quantity: float) -> None:
        if not symbol:
            return
        with self._lock:
            self._positions[symbol] = IbkrPosition(symbol=symbol, quantity=quantity)

    def finish_positions(self) -> None:
        self.positions_complete.set()

    def positions(self) -> list[IbkrPosition]:
        with self._lock:
            return [self._positions[symbol] for symbol in sorted(self._positions)]

    def begin_account_summary(self, request_id: int) -> None:
        with self._lock:
            self._account_values.clear()
            self._account_summary_request_id = request_id
            self.account_summary_complete.clear()

    def record_account_value(
        self,
        request_id: int,
        account: str,
        tag: str,
        value: str,
        currency: str,
    ) -> None:
        with self._lock:
            if request_id != self._account_summary_request_id:
                return
            self._account_values[(account, tag, currency)] = IbkrAccountValue(
                tag=tag,
                value=value,
                currency=currency,
            )

    def finish_account_summary(self, request_id: int) -> None:
        with self._lock:
            if request_id == self._account_summary_request_id:
                self.account_summary_complete.set()

    def account_values(self) -> list[IbkrAccountValue]:
        with self._lock:
            return [self._account_values[key] for key in sorted(self._account_values)]

    def begin_quote(self, request_id: int, symbol: str) -> threading.Event:
        with self._lock:
            state = _NativeQuoteState(symbol=symbol)
            self._quotes[request_id] = state
            return state.complete

    def record_tick_price(self, request_id: int, tick_type: int, price: float) -> None:
        with self._lock:
            state = self._quotes.get(request_id)
            if state is None or price == _UNAVAILABLE_TICK_PRICE:
                return
            if tick_type in _BID_TICK_TYPES:
                state.bid = price
            elif tick_type in _ASK_TICK_TYPES:
                state.ask = price
            elif tick_type in _LAST_TICK_TYPES:
                state.last = price

    def finish_quote(self, request_id: int) -> None:
        with self._lock:
            state = self._quotes.get(request_id)
            if state is not None:
                state.complete.set()

    def quote(self, request_id: int) -> IbkrQuote:
        with self._lock:
            state = self._quotes.get(request_id)
            if state is None:
                raise KeyError(f"Unknown IBKR native quote request id {request_id}.")
            if state.error is not None:
                raise state.error
            return IbkrQuote(
                symbol=state.symbol,
                bid=state.bid if state.bid is not None else _MISSING_QUOTE_VALUE,
                ask=state.ask if state.ask is not None else _MISSING_QUOTE_VALUE,
                last=state.last if state.last is not None else _MISSING_QUOTE_VALUE,
            )

    def discard_quote(self, request_id: int) -> None:
        with self._lock:
            self._quotes.pop(request_id, None)

    def record_background_error(self, error: RuntimeError) -> None:
        with self._lock:
            self._background_error = error
            self.ready.set()
            self.open_orders_complete.set()
            self.positions_complete.set()
            self.account_summary_complete.set()
            for quote in self._quotes.values():
                quote.complete.set()

    def raise_if_background_error(self) -> None:
        with self._lock:
            error = self._background_error
        if error is not None:
            raise error

    def request_disconnect(self) -> None:
        with self._lock:
            self._disconnect_requested = True

    def record_connection_closed(self) -> None:
        with self._lock:
            if self._disconnect_requested:
                return
            self._background_error = RuntimeError("IBKR native socket connection closed unexpectedly.")
            self.ready.set()
            self.open_orders_complete.set()
            self.positions_complete.set()
            self.account_summary_complete.set()
            for quote in self._quotes.values():
                quote.complete.set()


_NativeAppFactory = Callable[[_IbApiCallbackState], _NativeIbApp]


class IbApiClient:
    """Native IBKR socket client with synchronous lifecycle semantics."""

    def __init__(
        self,
        app_factory: _NativeAppFactory | None = None,
        connection_timeout_seconds: float = _CONNECTION_READY_TIMEOUT_SECONDS,
        request_timeout_seconds: float = _OPEN_ORDER_REFRESH_TIMEOUT_SECONDS,
    ) -> None:
        self._app_factory = app_factory or _build_native_app
        self._connection_timeout_seconds = connection_timeout_seconds
        self._request_timeout_seconds = request_timeout_seconds
        self._callbacks = _IbApiCallbackState()
        self._app: _NativeIbApp | None = None
        self._message_loop_thread: threading.Thread | None = None
        self._request_lock = threading.Lock()

    def connect(self, host: str, port: int, *, client_id: int) -> None:
        if self.is_connected():
            return

        self._callbacks = _IbApiCallbackState()
        self._app = self._app_factory(self._callbacks)
        self._app.connect(host, port, clientId=client_id)
        self._message_loop_thread = threading.Thread(
            target=self._run_message_loop,
            name="ibkr-native-message-loop",
            daemon=True,
        )
        self._message_loop_thread.start()

        if not self._callbacks.ready.wait(self._connection_timeout_seconds):
            self.disconnect()
            raise TimeoutError("Timed out waiting for IBKR native nextValidId callback.")
        self._callbacks.raise_if_background_error()

    def disconnect(self) -> None:
        app = self._app
        if app is None:
            return
        self._callbacks.request_disconnect()
        app.disconnect()
        thread = self._message_loop_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=_MESSAGE_LOOP_JOIN_TIMEOUT_SECONDS)

    def is_connected(self) -> bool:
        return self._app is not None and self._app.isConnected()

    def managed_accounts(self) -> list[str]:
        """Account ids this session can trade, from the on-connect callback."""
        return self._callbacks.managed_accounts()

    def callback_errors(self) -> tuple[IbkrApiError, ...]:
        """Return an immutable snapshot of errors received from IBKR."""
        return self._callbacks.errors()

    def place_order(self, order: IbkrOrderRequest) -> IbkrTrade:
        app = self._require_connected()
        order_id = self._reserve_order_id()
        trade = self._callbacks.register_order(order_id, order)
        app.place_order(order_id, order)
        return trade

    def cancel_order(self, order_id: int) -> None:
        self._require_connected().cancel_order(order_id)

    def trades(self) -> list[IbkrTrade]:
        app = self._require_connected()
        self._callbacks.begin_open_order_refresh()
        app.request_open_orders()
        if not self._callbacks.open_orders_complete.wait(self._request_timeout_seconds):
            raise TimeoutError("Timed out waiting for IBKR native openOrderEnd callback.")
        self._callbacks.raise_if_background_error()
        return self._callbacks.trades()

    def positions(self) -> list[IbkrPosition]:
        app = self._require_connected()
        with self._request_lock:
            self._callbacks.begin_positions()
            app.request_positions()
            try:
                completed = self._callbacks.positions_complete.wait(self._request_timeout_seconds)
                self._callbacks.raise_if_background_error()
                if not completed:
                    raise TimeoutError("Timed out waiting for IBKR native positionEnd callback.")
                return self._callbacks.positions()
            finally:
                app.cancel_positions()

    def account_summary(self) -> list[IbkrAccountValue]:
        app = self._require_connected()
        with self._request_lock:
            request_id = self._callbacks.reserve_request_id()
            self._callbacks.begin_account_summary(request_id)
            app.request_account_summary(
                request_id,
                _ACCOUNT_SUMMARY_GROUP,
                _ACCOUNT_SUMMARY_TAGS,
            )
            try:
                completed = self._callbacks.account_summary_complete.wait(self._request_timeout_seconds)
                self._callbacks.raise_if_background_error()
                if not completed:
                    raise TimeoutError("Timed out waiting for IBKR native accountSummaryEnd callback.")
                return self._callbacks.account_values()
            finally:
                app.cancel_account_summary(request_id)

    def quotes(self, symbols: list[str]) -> list[IbkrQuote]:
        app = self._require_connected()
        with self._request_lock:
            requests = [(self._callbacks.reserve_request_id(), symbol) for symbol in symbols]
            completions = {
                request_id: self._callbacks.begin_quote(request_id, symbol) for request_id, symbol in requests
            }
            try:
                for request_id, symbol in requests:
                    app.request_market_data(request_id, symbol)
                quotes: list[IbkrQuote] = []
                for request_id, symbol in requests:
                    if not completions[request_id].wait(self._request_timeout_seconds):
                        raise TimeoutError(f"Timed out waiting for IBKR native market-data snapshot for {symbol!r}.")
                    self._callbacks.raise_if_background_error()
                    quotes.append(self._callbacks.quote(request_id))
                return quotes
            finally:
                for request_id, _ in requests:
                    app.cancel_market_data(request_id)
                    self._callbacks.discard_quote(request_id)

    def _reserve_order_id(self) -> int:
        self._callbacks.raise_if_background_error()
        return self._callbacks.reserve_order_id()

    def _require_connected(self) -> _NativeIbApp:
        self._callbacks.raise_if_background_error()
        app = self._app
        if app is None or not app.isConnected():
            raise RuntimeError("IbApiClient is not connected. Call connect() first.")
        return app

    def _run_message_loop(self) -> None:
        app = self._app
        if app is None:
            return
        try:
            app.run()
        except Exception as exc:
            self._callbacks.record_background_error(RuntimeError(f"IBKR native message loop failed: {exc}"))


def _build_native_app(callbacks: _IbApiCallbackState) -> _NativeIbApp:
    """Load the optional official SDK and bind its callbacks."""
    try:
        from ibapi.client import EClient  # type: ignore[import-not-found]
        from ibapi.contract import Contract  # type: ignore[import-not-found]
        from ibapi.order import Order  # type: ignore[import-not-found]
        from ibapi.order_cancel import OrderCancel  # type: ignore[import-not-found]
        from ibapi.wrapper import EWrapper  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("The official IBKR Python API is required for the ibapi socket backend.") from exc

    class _App(EWrapper, EClient):  # type: ignore[misc, valid-type]
        def __init__(self) -> None:
            EWrapper.__init__(self)
            EClient.__init__(self, self)

        def nextValidId(self, orderId: int) -> None:  # noqa: N802
            callbacks.record_next_order_id(int(orderId))

        def managedAccounts(self, accountsList: str) -> None:  # noqa: N802
            callbacks.record_managed_accounts(str(accountsList))

        def connectionClosed(self) -> None:  # noqa: N802
            callbacks.record_connection_closed()

        def error(self, request_id: int, *args: object) -> None:
            code, message, advanced_rejection = _parse_error_callback(args)
            callbacks.record_error(request_id, code, message, advanced_rejection)

        def place_order(self, order_id: int, order: IbkrOrderRequest) -> None:
            contract = Contract()
            contract.symbol = order.symbol
            contract.secType = "STK"
            contract.exchange = "SMART"
            contract.currency = "USD"

            native_order = Order()
            native_order.action = order.action
            native_order.totalQuantity = order.total_quantity
            native_order.orderType = order.order_type
            native_order.lmtPrice = order.limit_price
            native_order.tif = order.time_in_force
            self.placeOrder(order_id, contract, native_order)

        def cancel_order(self, order_id: int) -> None:
            self.cancelOrder(order_id, OrderCancel())

        def request_open_orders(self) -> None:
            self.reqOpenOrders()

        def request_positions(self) -> None:
            self.reqPositions()

        def cancel_positions(self) -> None:
            self.cancelPositions()

        def request_account_summary(self, request_id: int, group: str, tags: str) -> None:
            self.reqAccountSummary(request_id, group, tags)

        def cancel_account_summary(self, request_id: int) -> None:
            self.cancelAccountSummary(request_id)

        def request_market_data(self, request_id: int, symbol: str) -> None:
            contract = Contract()
            contract.symbol = symbol
            contract.secType = "STK"
            contract.exchange = "SMART"
            contract.currency = "USD"
            self.reqMktData(request_id, contract, "", True, False, [])

        def cancel_market_data(self, request_id: int) -> None:
            self.cancelMktData(request_id)

        def openOrder(self, orderId: int, contract: object, order: object, orderState: object) -> None:  # noqa: N802
            callbacks.record_open_order(
                order_id=int(orderId),
                symbol=str(getattr(contract, "symbol", "")),
                action=str(getattr(order, "action", "")),
                total_quantity=_required_float(getattr(order, "totalQuantity", 0.0)),
                limit_price=_required_float(getattr(order, "lmtPrice", 0.0)),
                status=str(getattr(orderState, "status", "")),
            )

        def openOrderEnd(self) -> None:  # noqa: N802
            callbacks.finish_open_order_refresh()

        def orderStatus(  # noqa: N802
            self,
            orderId: int,
            status: str,
            filled: object,
            remaining: object,
            avgFillPrice: float,
            permId: int,
            parentId: int,
            lastFillPrice: float,
            clientId: int,
            whyHeld: str,
            mktCapPrice: float = 0.0,
        ) -> None:
            del remaining, permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice
            callbacks.record_order_status(
                order_id=int(orderId),
                status=status,
                filled=_required_float(filled),
                avg_fill_price=coerce_float(avgFillPrice),
            )

        def execDetails(self, requestId: int, contract: object, execution: object) -> None:  # noqa: N802
            del requestId, contract
            callbacks.record_execution(
                order_id=int(getattr(execution, "orderId")),
                exec_id=str(getattr(execution, "execId")),
                shares=_required_float(getattr(execution, "shares")),
                price=_required_float(getattr(execution, "price")),
                execution_time=str(getattr(execution, "time")),
            )

        def commissionReport(self, commissionReport: object) -> None:  # noqa: N802
            callbacks.record_commission(
                exec_id=str(getattr(commissionReport, "execId")),
                commission=_required_float(getattr(commissionReport, "commission")),
            )

        def position(  # noqa: N802
            self,
            account: str,
            contract: object,
            position: object,
            avgCost: float,
        ) -> None:
            del account, avgCost
            callbacks.record_position(
                symbol=str(getattr(contract, "symbol", "")),
                quantity=_required_float(position),
            )

        def positionEnd(self) -> None:  # noqa: N802
            callbacks.finish_positions()

        def accountSummary(  # noqa: N802
            self,
            requestId: int,
            account: str,
            tag: str,
            value: str,
            currency: str,
        ) -> None:
            callbacks.record_account_value(
                request_id=requestId,
                account=account,
                tag=tag,
                value=value,
                currency=currency,
            )

        def accountSummaryEnd(self, requestId: int) -> None:  # noqa: N802
            callbacks.finish_account_summary(requestId)

        def tickPrice(  # noqa: N802
            self,
            requestId: int,
            tickType: int,
            price: float,
            attrib: object,
        ) -> None:
            del attrib
            callbacks.record_tick_price(requestId, tickType, price)

        def tickSnapshotEnd(self, requestId: int) -> None:  # noqa: N802
            callbacks.finish_quote(requestId)

    return _App()


def _trade_snapshot(state: _NativeTradeState) -> IbkrTrade:
    fills = tuple(
        IbkrFill(
            shares=fill.shares,
            price=fill.price,
            time=fill.time,
            commission=fill.commission,
            exec_id=fill.exec_id,
        )
        for _, fill in sorted(state.fills.items())
    )
    return IbkrTrade(
        order_id=state.order_id,
        symbol=state.symbol,
        action=state.action,
        total_quantity=state.total_quantity,
        limit_price=state.limit_price,
        status=state.status,
        filled=state.filled,
        avg_fill_price=state.avg_fill_price,
        fills=fills,
        status_reason=state.status_reason,
    )


def _required_float(value: object) -> float:
    normalized = coerce_float(value)
    if normalized is None:
        raise RuntimeError(f"IBKR native callback value must be numeric: {value!r}")
    return normalized


def _parse_error_callback(args: tuple[object, ...]) -> tuple[int, str, str | None]:
    """Normalize supported old and current native error callback signatures."""
    if len(args) == 3:
        code, message, advanced_rejection = args
    elif len(args) >= 4:
        _, code, message, advanced_rejection = args[:4]
    elif len(args) == 2:
        code, message = args
        advanced_rejection = None
    else:
        raise RuntimeError(f"Unexpected IBKR native error callback arguments: {args!r}")

    normalized_code = coerce_int(code)
    if normalized_code is None:
        raise RuntimeError(f"Invalid IBKR native error code: {code!r}")
    advanced_text = str(advanced_rejection).strip() if advanced_rejection is not None else ""
    return normalized_code, str(message), advanced_text or None
