"""Legacy Interactive Brokers socket/TWS factory helpers.

This module isolates backend-selection and adapter construction for the older
socket/TWS-based IBKR integration so the top-level broker factory can stay
focused on the current/default Web API path.
"""

from __future__ import annotations

from trading.domain.broker_connection import BrokerConnection
from src.infrastructure.brokers.legacy.ib_adapter import (
    InteractiveBrokersAdapter,
    _IB_DEFAULT_CLIENT_ID,
    _IB_DEFAULT_HOST,
    _IB_DEFAULT_PORT,
)
from src.infrastructure.brokers.legacy.ib_client import IbApiClient, IbAsyncClient
from trading.models import AccountRecord

# Named backend constants for the legacy socket/TWS IB client path.
_IB_BACKEND_ASYNC = "ib_async"
_IB_BACKEND_NATIVE = "ibapi"

# Switch this to _IB_BACKEND_NATIVE to use the native IBKR API client instead.
IB_CLIENT_BACKEND: str = _IB_BACKEND_ASYNC


def build_legacy_ib_broker(account: AccountRecord) -> BrokerConnection:
    """Build the legacy socket/TWS Interactive Brokers adapter for *account*."""
    if IB_CLIENT_BACKEND == _IB_BACKEND_NATIVE:
        client = IbApiClient()
    elif IB_CLIENT_BACKEND == _IB_BACKEND_ASYNC:
        client = IbAsyncClient()
    else:
        raise ValueError(
            f"Unknown IB_CLIENT_BACKEND value {IB_CLIENT_BACKEND!r}. "
            f"Expected {_IB_BACKEND_ASYNC!r} or {_IB_BACKEND_NATIVE!r}."
        )

    host = account.broker_host or _IB_DEFAULT_HOST
    port = account.broker_port or _IB_DEFAULT_PORT
    client_id = account.broker_client_id or _IB_DEFAULT_CLIENT_ID
    adapter = InteractiveBrokersAdapter(client=client, host=host, port=port, client_id=client_id)
    adapter.connect()
    return adapter
