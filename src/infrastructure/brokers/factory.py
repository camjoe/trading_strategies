"""Broker factory — resolves the correct :class:`BrokerConnection` for an account.

Called by the interface layer.  New broker types are registered here.

Transport and venue are independent
-----------------------------------
*Transport* is how the runtime reaches IBKR: the Client Portal / Web API
(``_web``) or the socket/TWS API (``_socket``).  *Venue* is whether real money
can move: a live account, or an IBKR paper account.  Nothing about a transport
makes it inherently real-money, so every combination exists:

===============================  =========  ==========================
``broker_type``                  Transport  Guard
===============================  =========  ==========================
``paper``                        none       none — never leaves the process
``interactive_brokers_web``      Web API    ``live_trading_enabled = 1``
``interactive_brokers_web_paper``    Web API    account id must be a paper account
``interactive_brokers_socket``   socket     ``live_trading_enabled = 1``
``interactive_brokers_socket_paper`` socket     account id must be a paper account
===============================  =========  ==========================

The ``_paper`` types are *not* gated on ``live_trading_enabled`` — that flag
guards real money, and an IBKR paper account risks none.  In its place the
factory positively asserts the resolved account is a paper account.  See
``docs/adr/017-ibkr-paper-broker-type.md`` and
``docs/adr/018-broker-transport-venue-matrix.md``.

Where the assertion runs differs by transport: the Web API knows its account id
from settings before connecting, while the socket only learns it from IBKR at
connect time.  A socket paper mismatch therefore connects, fails, and
disconnects — connecting is not trading, so the guard still holds.
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
_BROKER_TYPE_IB_WEB = "interactive_brokers_web"
_BROKER_TYPE_IB_WEB_PAPER = "interactive_brokers_web_paper"
_BROKER_TYPE_IB_SOCKET = "interactive_brokers_socket"
_BROKER_TYPE_IB_SOCKET_PAPER = "interactive_brokers_socket_paper"

_KNOWN_BROKER_TYPES = frozenset(
    {
        _BROKER_TYPE_PAPER,
        _BROKER_TYPE_IB_WEB,
        _BROKER_TYPE_IB_WEB_PAPER,
        _BROKER_TYPE_IB_SOCKET,
        _BROKER_TYPE_IB_SOCKET_PAPER,
    }
)

# IBKR issues paper trading accounts with a "DU" prefix; live individual accounts
# use "U". Only "DU" is accepted so the paper path fails closed — other non-live
# IBKR prefixes exist for advisor/institutional paper accounts and should be added
# here deliberately, when an operator actually has one.
IBKR_PAPER_ACCOUNT_PREFIX = "DU"


def is_ibkr_paper_account_id(account_id: str) -> bool:
    """Whether *account_id* is an IBKR paper account.

    Public so operator tooling can preview the paper-venue guard without
    reimplementing the prefix rule and letting the two drift apart.
    """
    return account_id.strip().upper().startswith(IBKR_PAPER_ACCOUNT_PREFIX)


def get_broker_for_account(account: AccountRecord) -> BrokerConnection:
    """Return the appropriate :class:`BrokerConnection` for *account*.

    Defaults to :class:`PaperBrokerAdapter` when ``broker_type`` is absent or
    set to ``'paper'``.

    Live venues (``'interactive_brokers_web'``, ``'interactive_brokers_socket'``)
    require ``live_trading_enabled = 1`` on the account row or a
    :class:`LiveTradingNotEnabledError` is raised. This guard prevents accidental
    live order submission.

    Paper venues (``'interactive_brokers_web_paper'``,
    ``'interactive_brokers_socket_paper'``) reach the same gateways without that
    flag, because no real money is at risk. They instead require the resolved
    account id to be an IBKR paper account, raising
    :class:`PaperBrokerAccountMismatchError` if it is not.

    .. warning::
        ``live_trading_enabled`` must be set manually via a direct DB update.
        No bot or automated process should ever set this flag — see
        ``docs/architecture/architecture-conventions.md`` § Live Trading Safety Guard.
    """
    broker_type = str(account.broker_type or _BROKER_TYPE_PAPER).strip().lower()

    if broker_type == _BROKER_TYPE_IB_SOCKET:
        _require_live_trading_enabled(account)
        return build_ibkr_socket_broker(account)

    if broker_type == _BROKER_TYPE_IB_SOCKET_PAPER:
        return _connect_ibkr_socket_paper(account)

    if broker_type == _BROKER_TYPE_IB_WEB:
        _require_live_trading_enabled(account)
        return _connect_ibkr_web(load_ib_web_api_settings())

    if broker_type == _BROKER_TYPE_IB_WEB_PAPER:
        # Real IBKR order mechanics against a paper account: no capital at risk, so
        # the real-money guard does not apply. The account assertion replaces it.
        settings = load_ib_web_api_settings()
        _require_ibkr_paper_account(
            account,
            settings.account_id,
            broker_type=_BROKER_TYPE_IB_WEB_PAPER,
            live_broker_type=_BROKER_TYPE_IB_WEB,
        )
        return _connect_ibkr_web(settings)

    if broker_type == _BROKER_TYPE_PAPER:
        return PaperBrokerAdapter()

    # Anything else is a typo or a retired value. Falling through to the
    # simulator would answer a broker request with fabricated fills and no
    # warning, so an unrecognized type has to fail loudly instead.
    raise UnknownBrokerTypeError(
        f"Account {account.name!r} has broker_type {broker_type!r}, which is not a "
        f"known broker. Known values: {', '.join(sorted(_KNOWN_BROKER_TYPES))}."
    )


def _connect_ibkr_socket_paper(account: AccountRecord) -> BrokerConnection:
    """Connect the socket adapter and assert it landed on a paper account.

    The socket only reports its account ids once connected, so the assertion
    cannot run first. On mismatch the adapter is disconnected before raising —
    an open socket is not an order, but it should not be left dangling either.
    """
    adapter = build_ibkr_socket_broker(account)
    try:
        managed_accounts = adapter.managed_accounts()
    except Exception:
        adapter.disconnect()
        raise

    non_paper = [account_id for account_id in managed_accounts if not is_ibkr_paper_account_id(account_id)]
    # Every reachable account must be a paper account: the socket session can
    # trade any of them, so one live account in the list is enough to be unsafe.
    if non_paper or not managed_accounts:
        adapter.disconnect()
        _raise_paper_account_mismatch(
            account,
            ", ".join(managed_accounts) if managed_accounts else "<none reported>",
            broker_type=_BROKER_TYPE_IB_SOCKET_PAPER,
            live_broker_type=_BROKER_TYPE_IB_SOCKET,
        )
    return adapter


def _connect_ibkr_web(settings: IbWebApiSettings) -> InteractiveBrokersWebAdapter:
    """Build and connect a Client Portal / Web API adapter from *settings*."""
    client = InteractiveBrokersWebClient(settings=settings)
    adapter = InteractiveBrokersWebAdapter(client=client)
    adapter.connect()
    return adapter


def _require_ibkr_paper_account(
    account: AccountRecord,
    account_id: str,
    *,
    broker_type: str,
    live_broker_type: str,
) -> None:
    """Raise unless *account_id* is an IBKR paper account.

    This is the ``_paper`` counterpart to the real-money guard: rather than asking
    whether the operator opted in to risk, it asserts that there is no risk to opt
    in to. A live or misconfigured account id fails closed here instead of
    reaching the wire.
    """
    if not is_ibkr_paper_account_id(account_id):
        _raise_paper_account_mismatch(
            account,
            account_id,
            broker_type=broker_type,
            live_broker_type=live_broker_type,
        )


def _raise_paper_account_mismatch(
    account: AccountRecord,
    account_id: str,
    *,
    broker_type: str,
    live_broker_type: str,
) -> None:
    raise PaperBrokerAccountMismatchError(
        f"Account {account.name!r} uses broker_type {broker_type!r}, but the "
        f"resolved IBKR account id {account_id!r} is not an IBKR paper account "
        f"(expected a {IBKR_PAPER_ACCOUNT_PREFIX!r} prefix). Point the broker "
        f"configuration at a paper account, or use {live_broker_type!r} for a "
        "live account."
    )


def _require_live_trading_enabled(account: AccountRecord) -> None:
    """Raise :class:`LiveTradingNotEnabledError` if the account guard is not set.

    The ``live_trading_enabled`` column defaults to 0 and must be explicitly
    set to 1 via a direct DB update before live orders can be submitted.

    This is a hard runtime gate — for either live transport
    (``'interactive_brokers_web'`` or ``'interactive_brokers_socket'``), orders
    will never reach the wire without this flag.
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


class UnknownBrokerTypeError(RuntimeError):
    """Raised when ``accounts.broker_type`` names no known broker.

    Routing an unknown value to the simulator would silently answer a broker
    request with fabricated fills, so a typo or a retired value fails here.

    This error is intentional and must not be silenced by automated processes.
    """


class PaperBrokerAccountMismatchError(RuntimeError):
    """Raised when a ``_paper`` broker type resolves to a non-paper IBKR account.

    The paper broker type skips the real-money guard on the premise that the
    configured account cannot risk capital. If that premise does not hold, the
    connection must fail rather than proceed unguarded.

    This error is intentional and must not be silenced by automated processes.
    """
