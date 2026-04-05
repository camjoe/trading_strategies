"""Broker factory — resolves the correct :class:`BrokerConnection` for an account.

Called by the runtime service layer.  New broker types are registered here.

IB backend selection
--------------------
Set ``IB_CLIENT_BACKEND`` to switch between client implementations:

  ``_IB_BACKEND_ASYNC``   — IbAsyncClient (default, uses ib_async library)
  ``_IB_BACKEND_NATIVE``  — IbApiClient   (stub; implement IbApiClient before using)

No other code needs to change when switching backends.
"""
from __future__ import annotations

import sqlite3

from trading.brokers.base import BrokerConnection
from trading.brokers.paper_adapter import PaperBrokerAdapter
from trading.brokers.ib_client import IbAsyncClient, IbApiClient

# Broker type identifiers stored in accounts.broker_type column.
_BROKER_TYPE_PAPER = "paper"
_BROKER_TYPE_INTERACTIVE_BROKERS = "interactive_brokers"

# Named backend constants for IB_CLIENT_BACKEND.
_IB_BACKEND_ASYNC = "ib_async"
_IB_BACKEND_NATIVE = "ibapi"

# Switch this to _IB_BACKEND_NATIVE to use the native IBKR API client instead.
IB_CLIENT_BACKEND: str = _IB_BACKEND_ASYNC


def get_broker_for_account(account: sqlite3.Row) -> BrokerConnection:
    """Return the appropriate :class:`BrokerConnection` for *account*.

    Defaults to :class:`PaperBrokerAdapter` when ``broker_type`` is absent or
    set to ``'paper'``.

    For live brokers (e.g. ``'interactive_brokers'``), the account row must
    have ``live_trading_enabled = 1`` or a :class:`LiveTradingNotEnabledError`
    is raised.  This guard prevents accidental live order submission.

    .. warning::
        ``live_trading_enabled`` must be set manually via a direct DB update.
        No bot or automated process should ever set this flag — see
        ``BOT_ARCHITECTURE_CONVENTIONS.md`` § Live Trading Safety Guard.
    """
    try:
        raw = account["broker_type"]
    except (KeyError, IndexError):
        raw = None
    broker_type = str(raw or _BROKER_TYPE_PAPER).strip().lower()

    if broker_type == _BROKER_TYPE_INTERACTIVE_BROKERS:
        _require_live_trading_enabled(account)
        from trading.brokers.ib_adapter import (
            InteractiveBrokersAdapter,
            _IB_DEFAULT_HOST,
            _IB_DEFAULT_PORT,
            _IB_DEFAULT_CLIENT_ID,
        )

        if IB_CLIENT_BACKEND == _IB_BACKEND_NATIVE:
            client = IbApiClient()
        elif IB_CLIENT_BACKEND == _IB_BACKEND_ASYNC:
            client = IbAsyncClient()
        else:
            raise ValueError(
                f"Unknown IB_CLIENT_BACKEND value {IB_CLIENT_BACKEND!r}. "
                f"Expected {_IB_BACKEND_ASYNC!r} or {_IB_BACKEND_NATIVE!r}."
            )

        host = str(account["broker_host"] or _IB_DEFAULT_HOST)
        port = int(account["broker_port"] or _IB_DEFAULT_PORT)
        client_id = int(account["broker_client_id"] or _IB_DEFAULT_CLIENT_ID)
        adapter = InteractiveBrokersAdapter(client=client, host=host, port=port, client_id=client_id)
        adapter.connect()
        return adapter

    return PaperBrokerAdapter()


def _require_live_trading_enabled(account: sqlite3.Row) -> None:
    """Raise :class:`LiveTradingNotEnabledError` if the account guard is not set.

    The ``live_trading_enabled`` column defaults to 0 and must be explicitly
    set to 1 via a direct DB update before live orders can be submitted.

    This is a hard runtime gate — even if the broker_type is 'interactive_brokers',
    orders will never reach the wire without this flag.
    """
    try:
        enabled = int(account["live_trading_enabled"] or 0)
    except (KeyError, IndexError, TypeError, ValueError):
        enabled = 0
    if not enabled:
        try:
            name = account["name"]
        except (KeyError, IndexError):
            name = "<unknown>"
        raise LiveTradingNotEnabledError(
            f"Account {name!r} has live_trading_enabled = 0. "
            "Set live_trading_enabled = 1 on the account row to allow live orders. "
            "This must be done manually — bots must never set this flag."
        )


class LiveTradingNotEnabledError(RuntimeError):
    """Raised when a live broker is requested for an account that has not
    explicitly opted in to live trading via ``live_trading_enabled = 1``.

    This error is intentional and must not be silenced by automated processes.
    """
