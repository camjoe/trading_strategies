"""Broker factory — resolves the correct :class:`BrokerConnection` for an account.

Called by the interface layer.  New broker types are registered here.

Current IBKR path
-----------------
The active local-gateway integration is ``interactive_brokers_web`` via the
Client Portal / Web API.

Legacy IB path
--------------
``interactive_brokers`` remains wired as a legacy socket/TWS alternative. It is
kept available, but it is not the primary IBKR path for current development.
"""

from __future__ import annotations

from trading.domain.broker_connection import BrokerConnection
from brokers.paper_adapter import PaperBrokerAdapter
from brokers.ib_web_adapter import InteractiveBrokersWebAdapter
from brokers.ib_web_client import InteractiveBrokersWebClient, load_ib_web_api_settings
from brokers.legacy.factory import build_legacy_ib_broker
from trading.models import AccountRecord

# Broker type identifiers stored in accounts.broker_type column.
_BROKER_TYPE_PAPER = "paper"
_BROKER_TYPE_INTERACTIVE_BROKERS = "interactive_brokers"
_BROKER_TYPE_INTERACTIVE_BROKERS_WEB = "interactive_brokers_web"


def get_broker_for_account(account: AccountRecord) -> BrokerConnection:
    """Return the appropriate :class:`BrokerConnection` for *account*.

    Defaults to :class:`PaperBrokerAdapter` when ``broker_type`` is absent or
    set to ``'paper'``.

    For live brokers (current: ``'interactive_brokers_web'``; legacy:
    ``'interactive_brokers'``), the account row must have
    ``live_trading_enabled = 1`` or a :class:`LiveTradingNotEnabledError`
    is raised. This guard prevents accidental live order submission.

    .. warning::
        ``live_trading_enabled`` must be set manually via a direct DB update.
        No bot or automated process should ever set this flag — see
        ``docs/architecture/architecture-conventions.md`` § Live Trading Safety Guard.
    """
    broker_type = str(account.broker_type or _BROKER_TYPE_PAPER).strip().lower()

    if broker_type == _BROKER_TYPE_INTERACTIVE_BROKERS:
        # Legacy socket/TWS IBKR path retained for possible future reuse.
        _require_live_trading_enabled(account)
        return build_legacy_ib_broker(account)

    if broker_type == _BROKER_TYPE_INTERACTIVE_BROKERS_WEB:
        # Current IBKR integration path: Client Portal / Web API.
        _require_live_trading_enabled(account)
        settings = load_ib_web_api_settings()
        client = InteractiveBrokersWebClient(settings=settings)
        adapter = InteractiveBrokersWebAdapter(client=client)
        adapter.connect()
        return adapter

    return PaperBrokerAdapter()


def _require_live_trading_enabled(account: AccountRecord) -> None:
    """Raise :class:`LiveTradingNotEnabledError` if the account guard is not set.

    The ``live_trading_enabled`` column defaults to 0 and must be explicitly
    set to 1 via a direct DB update before live orders can be submitted.

    This is a hard runtime gate — even if the broker_type is
    ``'interactive_brokers_web'`` or legacy ``'interactive_brokers'``,
    orders will never reach the wire without this flag.
    """
    if not account.live_trading_enabled:
        raise LiveTradingNotEnabledError(
            f"Account {account.name!r} has live_trading_enabled = 0. "
            "Set live_trading_enabled = 1 on the account row to allow live orders. "
            "This must be done manually — bots must never set this flag."
        )


class LiveTradingNotEnabledError(RuntimeError):
    """Raised when a live broker is requested for an account that has not
    explicitly opted in to live trading via ``live_trading_enabled = 1``.

    This error is intentional and must not be silenced by automated processes.
    """
