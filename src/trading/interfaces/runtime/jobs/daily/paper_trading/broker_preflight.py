"""Find the run accounts that cannot trade today, before the daily run changes anything.

Connects every run account through ``get_broker_for_account`` and disconnects. Simulator accounts
connect for free. The broker guard errors propagate untouched (``LiveTradingNotEnabledError``,
``PaperBrokerAccountMismatchError``, ``UnknownBrokerTypeError``): they mean the operator must
investigate, not retry, so they stop the whole run, as does ``IbWebAccountUnavailableError`` (a wrong
``account_id`` is a configuration error, not an outage). A down gateway or TWS/IB Gateway socket is
unavailable, not an error. When no account has a usable session the check raises
``BrokerSessionUnavailableError`` and the run fails before any step runs.

While connected, an account that reports broker cash is also checked against its books. Every account
of one broker type trades through one broker account, so their books draw on one cash balance; when
the books hold more than the broker does, each run account of that type is skipped for the day, and
when that leaves no account the check raises ``BrokerCashShortfallError``.
"""

from __future__ import annotations

import httpx

from infrastructure.brokers.factory import (
    LiveTradingNotEnabledError,
    PaperBrokerAccountMismatchError,
    UnknownBrokerTypeError,
    get_broker_for_account,
)
from infrastructure.brokers.ibkr_web.client import IbWebAccountUnavailableError
from infrastructure.database.connection import db_session
from trading.domain.broker_cash import broker_cash_shortfall
from trading.domain.broker_connection import BrokerConnection
from trading.services.accounts.mutations import get_account
from trading.services.operations.broker_cash import fetch_book_cash_by_broker_type

__all__ = ["BrokerCashShortfallError", "BrokerSessionUnavailableError", "check_broker_sessions"]

# The account-summary key that holds the broker's cash balance.
_CASH_KEY = "TotalCashValue"


class BrokerSessionUnavailableError(RuntimeError):
    """No run account has a usable broker session."""

    def __init__(self, unavailable: dict[str, str]) -> None:
        self.unavailable = unavailable
        super().__init__(
            "Broker session unavailable for every run account, no step ran. "
            + "; ".join(f"{name} ({reason})" for name, reason in unavailable.items())
            + ". Start the IBKR Client Portal gateway and log in, then re-run (a plain re-run works only if no run "
            "completed today). See docs/runbooks/ibkr-paper-trading.md (Gateway session)."
        )


class BrokerCashShortfallError(RuntimeError):
    """Every run account was skipped, and at least one because its books hold more cash than the broker."""

    def __init__(self, skipped: dict[str, str]) -> None:
        self.unavailable = skipped
        super().__init__(
            "No run account can trade today, no step ran. "
            + "; ".join(f"{name} ({reason})" for name, reason in skipped.items())
            + ". Bring the books' cash back in line with the broker's, then re-run (a plain re-run works only if no "
            "run completed today). See docs/runbooks/ibkr-paper-trading.md (Books hold more cash than the broker)."
        )


def _reported_cash(broker: BrokerConnection) -> float | None:
    """The broker's cash balance, or None for a simulator, which keeps its cash in the books."""
    try:
        info = broker.get_account_info()
    except NotImplementedError:
        return None
    cash = info.get(_CASH_KEY)
    if cash is None:
        raise RuntimeError(f"the broker's account summary has no {_CASH_KEY}")
    return cash


def check_broker_sessions(account_names: list[str]) -> dict[str, str]:
    """Map each account that cannot trade today to ``"<broker type>: <reason>"``.

    Raises ``BrokerSessionUnavailableError`` when no account has a usable session, and
    ``BrokerCashShortfallError`` when a cash shortfall leaves no account to trade.
    """
    unavailable: dict[str, str] = {}
    broker_cash: dict[str, float] = {}
    broker_types: dict[str, str] = {}
    with db_session() as conn:
        for name in account_names:
            account = get_account(conn, name)
            broker_types[name] = account.broker_type or ""
            try:
                broker = get_broker_for_account(account)
                try:
                    cash = _reported_cash(broker)
                finally:
                    broker.disconnect()
            except (
                LiveTradingNotEnabledError,
                PaperBrokerAccountMismatchError,
                UnknownBrokerTypeError,
                IbWebAccountUnavailableError,
            ):
                raise
            except (httpx.TransportError, OSError, RuntimeError) as exc:
                unavailable[name] = f"{account.broker_type}: {exc}"
            else:
                if cash is not None:
                    broker_cash.setdefault(broker_types[name], cash)
        book_cash = fetch_book_cash_by_broker_type(conn)
    if set(unavailable) >= set(account_names):
        raise BrokerSessionUnavailableError(unavailable)

    shortfalls: dict[str, str] = {}
    for name in account_names:
        broker_type = broker_types[name]
        if name in unavailable or broker_type not in broker_cash:
            continue
        shortfall = broker_cash_shortfall(book_cash[broker_type], broker_cash[broker_type])
        if shortfall:
            shortfalls[name] = (
                f"{broker_type}: the books hold {book_cash[broker_type]:.2f} cash and the broker holds "
                f"{broker_cash[broker_type]:.2f}"
            )
    skipped = {**unavailable, **shortfalls}
    if shortfalls and set(skipped) >= set(account_names):
        raise BrokerCashShortfallError(skipped)
    return skipped
