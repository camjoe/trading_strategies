"""Broker factory — resolves the correct :class:`BrokerConnection` for an account.

Called by the interface layer.  New broker types are registered here.

Current IBKR path
-----------------
The active local-gateway integration is ``interactive_brokers_web`` via the
Client Portal / Web API.

IBKR paper path
---------------
``interactive_brokers_paper`` reaches the same Client Portal / Web API gateway
but is *not* gated on ``live_trading_enabled`` — that flag guards real money,
and an IBKR paper account risks none.  In its place the factory positively
asserts the configured account is a paper account.  See
``docs/adr/017-ibkr-paper-broker-type.md``.

IBKR socket path
----------------
``interactive_brokers`` remains the persisted compatibility value for the
socket/TWS integration until a later migration renames it.
"""

from __future__ import annotations

from infrastructure.brokers.ibkr_socket.factory import build_ibkr_socket_broker
from infrastructure.brokers.ibkr_web import InteractiveBrokersWebClient, load_ib_web_api_settings
from infrastructure.brokers.ibkr_web.adapter import InteractiveBrokersWebAdapter
from infrastructure.brokers.ibkr_web.settings import IbWebApiSettings
from infrastructure.brokers.paper_adapter import PaperBrokerAdapter
from trading.domain.broker_connection import BrokerConnection
from trading.models import AccountRecord

# Broker type identifiers stored in accounts.broker_type column.
_BROKER_TYPE_PAPER = "paper"
_BROKER_TYPE_INTERACTIVE_BROKERS = "interactive_brokers"
_BROKER_TYPE_INTERACTIVE_BROKERS_WEB = "interactive_brokers_web"
_BROKER_TYPE_INTERACTIVE_BROKERS_PAPER = "interactive_brokers_paper"

# IBKR issues paper trading accounts with a "DU" prefix; live individual accounts
# use "U". Only "DU" is accepted so the paper path fails closed — other non-live
# IBKR prefixes exist for advisor/institutional paper accounts and should be added
# here deliberately, when an operator actually has one.
_IBKR_PAPER_ACCOUNT_PREFIX = "DU"


def get_broker_for_account(account: AccountRecord) -> BrokerConnection:
    """Return the appropriate :class:`BrokerConnection` for *account*.

    Defaults to :class:`PaperBrokerAdapter` when ``broker_type`` is absent or
    set to ``'paper'``.

    For live brokers (current: ``'interactive_brokers_web'``; socket compatibility:
    ``'interactive_brokers'``), the account row must have
    ``live_trading_enabled = 1`` or a :class:`LiveTradingNotEnabledError`
    is raised. This guard prevents accidental live order submission.

    ``'interactive_brokers_paper'`` reaches the same Web API gateway without that
    flag, because no real money is at risk. It instead requires the configured
    account id to be an IBKR paper account, raising
    :class:`PaperBrokerAccountMismatchError` if it is not.

    .. warning::
        ``live_trading_enabled`` must be set manually via a direct DB update.
        No bot or automated process should ever set this flag — see
        ``docs/architecture/architecture-conventions.md`` § Live Trading Safety Guard.
    """
    broker_type = str(account.broker_type or _BROKER_TYPE_PAPER).strip().lower()

    if broker_type == _BROKER_TYPE_INTERACTIVE_BROKERS:
        # Socket/TWS path; broker_type keeps its compatibility value until migration.
        _require_live_trading_enabled(account)
        return build_ibkr_socket_broker(account)

    if broker_type == _BROKER_TYPE_INTERACTIVE_BROKERS_PAPER:
        # Real IBKR order mechanics against a paper account: no capital at risk, so
        # the real-money guard does not apply. The account assertion replaces it.
        settings = load_ib_web_api_settings()
        _require_ibkr_paper_account(account, settings.account_id)
        return _connect_ibkr_web(settings)

    if broker_type == _BROKER_TYPE_INTERACTIVE_BROKERS_WEB:
        # Current IBKR integration path: Client Portal / Web API.
        _require_live_trading_enabled(account)
        return _connect_ibkr_web(load_ib_web_api_settings())

    return PaperBrokerAdapter()


def _connect_ibkr_web(settings: IbWebApiSettings) -> InteractiveBrokersWebAdapter:
    """Build and connect a Client Portal / Web API adapter from *settings*."""
    client = InteractiveBrokersWebClient(settings=settings)
    adapter = InteractiveBrokersWebAdapter(client=client)
    adapter.connect()
    return adapter


def _require_ibkr_paper_account(account: AccountRecord, account_id: str) -> None:
    """Raise unless *account_id* is an IBKR paper account.

    This is the ``interactive_brokers_paper`` counterpart to the real-money guard:
    rather than asking whether the operator opted in to risk, it asserts that there
    is no risk to opt in to. A live or misconfigured account id fails closed here
    instead of reaching the wire.
    """
    if not account_id.strip().upper().startswith(_IBKR_PAPER_ACCOUNT_PREFIX):
        raise PaperBrokerAccountMismatchError(
            f"Account {account.name!r} uses broker_type "
            f"{_BROKER_TYPE_INTERACTIVE_BROKERS_PAPER!r}, but the configured IBKR "
            f"account id {account_id!r} is not an IBKR paper account "
            f"(expected a {_IBKR_PAPER_ACCOUNT_PREFIX!r} prefix). Point the Web API "
            f"settings at a paper account, or use {_BROKER_TYPE_INTERACTIVE_BROKERS_WEB!r} "
            "for a live account."
        )


def _require_live_trading_enabled(account: AccountRecord) -> None:
    """Raise :class:`LiveTradingNotEnabledError` if the account guard is not set.

    The ``live_trading_enabled`` column defaults to 0 and must be explicitly
    set to 1 via a direct DB update before live orders can be submitted.

    This is a hard runtime gate — even if the broker_type is
    ``'interactive_brokers_web'`` or socket-compatible ``'interactive_brokers'``,
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


class PaperBrokerAccountMismatchError(RuntimeError):
    """Raised when ``interactive_brokers_paper`` resolves to a non-paper IBKR account.

    The paper broker type skips the real-money guard on the premise that the
    configured account cannot risk capital. If that premise does not hold, the
    connection must fail rather than proceed unguarded.

    This error is intentional and must not be silenced by automated processes.
    """
