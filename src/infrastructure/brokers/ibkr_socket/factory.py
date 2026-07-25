"""Interactive Brokers socket/TWS factory helpers."""

from __future__ import annotations

from infrastructure.brokers.ibkr_socket.adapter import (
    _IB_DEFAULT_CLIENT_ID,
    _IB_DEFAULT_HOST,
    _IB_DEFAULT_PORT,
    IbkrSocketAdapter,
)
from infrastructure.brokers.ibkr_socket.ib_async_client import IbAsyncClient
from infrastructure.brokers.ibkr_socket.ibapi_client import IbApiClient
from trading.domain.broker_connection import BrokerConnection
from trading.models import AccountRecord

# Named backend constants for the socket/TWS client path.
_SOCKET_BACKEND_IB_ASYNC = "ib_async"
_SOCKET_BACKEND_IBAPI = "ibapi"

# Switch this to _SOCKET_BACKEND_IBAPI to use the native IBKR API client.
IBKR_SOCKET_CLIENT_BACKEND: str = _SOCKET_BACKEND_IB_ASYNC


def build_ibkr_socket_broker(account: AccountRecord) -> BrokerConnection:
    """Build the socket/TWS Interactive Brokers adapter for *account*."""
    if IBKR_SOCKET_CLIENT_BACKEND == _SOCKET_BACKEND_IBAPI:
        client = IbApiClient()
    elif IBKR_SOCKET_CLIENT_BACKEND == _SOCKET_BACKEND_IB_ASYNC:
        client = IbAsyncClient()
    else:
        raise ValueError(
            f"Unknown IBKR_SOCKET_CLIENT_BACKEND value {IBKR_SOCKET_CLIENT_BACKEND!r}. "
            f"Expected {_SOCKET_BACKEND_IB_ASYNC!r} or {_SOCKET_BACKEND_IBAPI!r}."
        )

    host = account.broker_host or _IB_DEFAULT_HOST
    port = account.broker_port or _IB_DEFAULT_PORT
    client_id = account.broker_client_id or _IB_DEFAULT_CLIENT_ID
    adapter = IbkrSocketAdapter(client=client, host=host, port=port, client_id=client_id)
    adapter.connect()
    return adapter
