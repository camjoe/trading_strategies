"""Interactive Brokers socket/TWS factory helpers."""

from __future__ import annotations

import os

from infrastructure.brokers.ibkr_socket.adapter import (
    _IB_DEFAULT_CLIENT_ID,
    _IB_DEFAULT_HOST,
    _IB_DEFAULT_PORT,
    IbkrSocketAdapter,
)
from infrastructure.brokers.ibkr_socket.ib_async_client import IbAsyncClient
from infrastructure.brokers.ibkr_socket.ibapi_client import IbApiClient
from infrastructure.brokers.ibkr_socket.protocol import IbkrSocketClient
from trading.models import AccountRecord

# Named backend constants for the socket/TWS client path.
_SOCKET_BACKEND_IB_ASYNC = "ib_async"
_SOCKET_BACKEND_IBAPI = "ibapi"

# Environment variable controlling the socket/TWS client implementation.
_SOCKET_BACKEND_ENV_NAME = "TRADING_IBKR_SOCKET_CLIENT_BACKEND"


def resolve_ibkr_socket_client_backend() -> str:
    """Resolve and validate the configured IBKR socket client backend."""
    backend = os.getenv(_SOCKET_BACKEND_ENV_NAME, "").strip().lower()
    if not backend:
        return _SOCKET_BACKEND_IB_ASYNC
    if backend not in {_SOCKET_BACKEND_IB_ASYNC, _SOCKET_BACKEND_IBAPI}:
        raise ValueError(
            f"Unknown {_SOCKET_BACKEND_ENV_NAME} value {backend!r}. "
            f"Expected {_SOCKET_BACKEND_IB_ASYNC!r} or {_SOCKET_BACKEND_IBAPI!r}."
        )
    return backend


def build_ibkr_socket_broker(account: AccountRecord) -> IbkrSocketAdapter:
    """Build and connect the socket/TWS Interactive Brokers adapter for *account*."""
    backend = resolve_ibkr_socket_client_backend()
    # Annotated as the protocol, not either concrete class: the adapter depends
    # only on IbkrSocketClient, and binding the name to whichever branch runs
    # first would make the other backend a type error.
    client: IbkrSocketClient
    if backend == _SOCKET_BACKEND_IBAPI:
        client = IbApiClient()
    else:
        client = IbAsyncClient()

    host = account.broker_host or _IB_DEFAULT_HOST
    port = account.broker_port or _IB_DEFAULT_PORT
    client_id = account.broker_client_id or _IB_DEFAULT_CLIENT_ID
    adapter = IbkrSocketAdapter(client=client, host=host, port=port, client_id=client_id)
    adapter.connect()
    return adapter
