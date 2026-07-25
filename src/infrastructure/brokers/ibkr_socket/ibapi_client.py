"""Native ``ibapi`` implementation of the IBKR socket client."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Protocol

from common.coercion import coerce_int
from infrastructure.brokers.ibkr_socket.contracts import (
    IbkrAccountValue,
    IbkrApiError,
    IbkrOrderRequest,
    IbkrPosition,
    IbkrQuote,
    IbkrTrade,
)

# Maximum time to wait for IBKR's nextValidId connection-readiness callback.
_CONNECTION_READY_TIMEOUT_SECONDS = 10.0

# Maximum time to wait for the native message-loop thread during shutdown.
_MESSAGE_LOOP_JOIN_TIMEOUT_SECONDS = 2.0


class _NativeIbApp(Protocol):
    def connect(self, host: str, port: int, clientId: int) -> object: ...

    def disconnect(self) -> None: ...

    def isConnected(self) -> bool: ...

    def run(self) -> None: ...


class _IbApiCallbackState:
    """Thread-safe state shared by native callbacks and synchronous callers."""

    def __init__(self) -> None:
        self.ready = threading.Event()
        self._lock = threading.Lock()
        self._next_order_id: int | None = None
        self._errors: list[IbkrApiError] = []
        self._background_error: RuntimeError | None = None
        self._disconnect_requested = False

    def record_next_order_id(self, order_id: int) -> None:
        with self._lock:
            self._next_order_id = order_id
            self.ready.set()

    def reserve_order_id(self) -> int:
        with self._lock:
            if self._next_order_id is None:
                raise RuntimeError("IBKR native client has not received nextValidId.")
            order_id = self._next_order_id
            self._next_order_id += 1
            return order_id

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

    def errors(self) -> tuple[IbkrApiError, ...]:
        with self._lock:
            return tuple(self._errors)

    def record_background_error(self, error: RuntimeError) -> None:
        with self._lock:
            self._background_error = error
            self.ready.set()

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


_NativeAppFactory = Callable[[_IbApiCallbackState], _NativeIbApp]


class IbApiClient:
    """Native IBKR socket client with synchronous lifecycle semantics."""

    def __init__(
        self,
        app_factory: _NativeAppFactory | None = None,
        connection_timeout_seconds: float = _CONNECTION_READY_TIMEOUT_SECONDS,
    ) -> None:
        self._app_factory = app_factory or _build_native_app
        self._connection_timeout_seconds = connection_timeout_seconds
        self._callbacks = _IbApiCallbackState()
        self._app: _NativeIbApp | None = None
        self._message_loop_thread: threading.Thread | None = None

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

    def callback_errors(self) -> tuple[IbkrApiError, ...]:
        """Return an immutable snapshot of errors received from IBKR."""
        return self._callbacks.errors()

    def place_order(self, order: IbkrOrderRequest) -> IbkrTrade:
        raise NotImplementedError("Native IBKR order placement is not yet implemented.")

    def cancel_order(self, order_id: int) -> None:
        raise NotImplementedError("Native IBKR order cancellation is not yet implemented.")

    def trades(self) -> list[IbkrTrade]:
        raise NotImplementedError("Native IBKR trade snapshots are not yet implemented.")

    def positions(self) -> list[IbkrPosition]:
        raise NotImplementedError("Native IBKR position requests are not yet implemented.")

    def account_summary(self) -> list[IbkrAccountValue]:
        raise NotImplementedError("Native IBKR account summary requests are not yet implemented.")

    def quotes(self, symbols: list[str]) -> list[IbkrQuote]:
        raise NotImplementedError("Native IBKR quote snapshots are not yet implemented.")

    def _reserve_order_id(self) -> int:
        self._callbacks.raise_if_background_error()
        return self._callbacks.reserve_order_id()

    def _run_message_loop(self) -> None:
        app = self._app
        if app is None:
            return
        try:
            app.run()
        except Exception as exc:
            self._callbacks.record_background_error(
                RuntimeError(f"IBKR native message loop failed: {exc}")
            )


def _build_native_app(callbacks: _IbApiCallbackState) -> _NativeIbApp:
    """Load the optional official SDK and bind its callbacks."""
    try:
        from ibapi.client import EClient  # type: ignore[import-not-found]
        from ibapi.wrapper import EWrapper  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "The official IBKR Python API is required for the ibapi socket backend."
        ) from exc

    class _App(EWrapper, EClient):  # type: ignore[misc, valid-type]
        def __init__(self) -> None:
            EWrapper.__init__(self)
            EClient.__init__(self, self)

        def nextValidId(self, orderId: int) -> None:  # noqa: N802
            callbacks.record_next_order_id(int(orderId))

        def connectionClosed(self) -> None:  # noqa: N802
            callbacks.record_connection_closed()

        def error(self, request_id: int, *args: object) -> None:
            code, message, advanced_rejection = _parse_error_callback(args)
            callbacks.record_error(request_id, code, message, advanced_rejection)

    return _App()


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
